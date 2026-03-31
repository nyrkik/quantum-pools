"""DeepBlue responder agent — answers questions using customer/job context.

Single responsibility: when a comment asks a question, look up the answer
in the database and post an auto-reply. If the info doesn't exist, post
what's missing and notify the relevant person.
"""

import json
import logging
import os
import re

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction, AgentActionComment
from src.models.notification import Notification

from .observability import AgentTimer, log_agent_call
from src.core.ai_models import get_model

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


ANSWER_PROMPT = """A team member is asking a question on a pool service job. Answer using ONLY the data provided.

Job: {job_description}
Question: "{comment}"

Available data:
{customer_context}

If the data above contains the answer, respond:
{{"type": "answer", "answer": "the answer, formatted naturally and concisely"}}

If the data does NOT contain the answer, respond:
{{"type": "escalate", "needs_info": "what specific info is missing"}}

IMPORTANT: Only answer from the data above. Never guess or fabricate."""


class DeepBlueResponder:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def respond(
        self,
        org_id: str,
        action: AgentAction,
        comment_text: str,
        customer_context: str,
        user_id: str,
        find_org_user_fn,
    ) -> dict | None:
        """Try to answer a question. Returns auto-comment dict or None."""
        if not ANTHROPIC_KEY or not customer_context:
            return None

        prompt = ANSWER_PROMPT.format(
            job_description=action.description,
            comment=comment_text.strip(),
            customer_context=customer_context,
        )

        # Inject lessons from past corrections
        try:
            from src.services.agent_learning_service import AgentLearningService, AGENT_DEEPBLUE
            learner = AgentLearningService(self.db)
            lessons = await learner.build_lessons_prompt(
                org_id, AGENT_DEEPBLUE,
                customer_id=action.customer_id,
            )
            if lessons:
                prompt += "\n\n" + lessons
        except Exception:
            pass

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            with AgentTimer() as timer:
                response = client.messages.create(
                    model=await get_model("fast"),
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )

            text = response.content[0].text
            usage = response.usage

            await log_agent_call(
                organization_id=org_id,
                agent_name="deepblue_responder",
                action="respond",
                input_summary=f"Q: {comment_text[:100]}",
                output_summary=text[:200],
                success=True,
                model=await get_model("fast"),
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                duration_ms=timer.duration_ms,
            )

            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            comment_type = data.get("type", "none")

            if comment_type == "answer" and data.get("answer"):
                auto_reply = AgentActionComment(
                    organization_id=org_id,
                    action_id=action.id,
                    author="DeepBlue",
                    text=data["answer"],
                )
                self.db.add(auto_reply)
                await self.db.commit()
                await self.db.refresh(auto_reply)
                return {"author": "DeepBlue", "text": data["answer"]}

            elif comment_type == "escalate" and data.get("needs_info"):
                missing_info = data["needs_info"]
                gap_text = f"I don't have this info on file: {missing_info}. Can someone provide it?"
                gap_comment = AgentActionComment(
                    organization_id=org_id,
                    action_id=action.id,
                    author="DeepBlue",
                    text=gap_text,
                )
                self.db.add(gap_comment)

                # Notify creator or assignee
                notify_target = action.created_by or action.assigned_to
                if notify_target and notify_target != "DeepBlue":
                    target = await find_org_user_fn(
                        org_id, notify_target.split()[0], exclude_user_id=user_id
                    )
                    if target:
                        self.db.add(Notification(
                            organization_id=org_id,
                            user_id=target.user_id,
                            type="info_needed",
                            title=f"Info needed: {action.description[:50]}",
                            body=f"Missing: {missing_info}",
                            link=f"/jobs?action={action.id}",
                        ))

                await self.db.commit()
                return {"author": "DeepBlue", "text": gap_text}

        except Exception as e:
            logger.error(f"DeepBlue responder failed: {e}")
            await log_agent_call(
                organization_id=org_id,
                agent_name="deepblue_responder",
                action="respond",
                input_summary=f"Q: {comment_text[:100]}",
                success=False,
                error=str(e),
                model=await get_model("fast"),
            )

        return None
