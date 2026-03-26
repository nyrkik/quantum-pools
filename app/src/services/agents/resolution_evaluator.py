"""Resolution evaluator agent — determines if a comment resolves a job.

Single responsibility: evaluate whether a status_update or completion
comment means the job is done. Updates job status accordingly.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.agent_action import AgentAction

from .observability import AgentTimer, log_agent_call

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"

EVAL_PROMPT = """A pool service job just received a new comment. Does this resolve the job?

Action: [{action_type}] {description}
Assigned to: {assigned_to}

Comments:
{comments}

Latest comment by {author}: "{latest_comment}"

Respond with JSON:
{{
  "resolved": true/false,
  "update_description": "new description if scope changed, or null",
  "update_type": "new action_type if changed, or null",
  "reason": "brief explanation"
}}

Rules:
- resolved=true if: work is completed, answer was provided, task is no longer needed
- resolved=false if: just a progress update, partial work, needs more steps
- update_description: ONLY if the comment changes what needs to be done
- update_type: ONLY if action type should change (e.g., site_visit -> equipment)"""


class ResolutionEvaluator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(
        self,
        org_id: str,
        action: AgentAction,
        comment_text: str,
        intent: dict,
        author: str,
    ) -> dict:
        """Evaluate if a comment resolves the job.

        Returns {"resolved": bool, "updated_description": str|None}.
        """
        resolved = False
        updated_desc = None

        # Explicit completion intent — almost always resolves
        if intent.get("intent") == "completion":
            action.status = "done"
            action.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            return {"resolved": True, "updated_description": None}

        # Status update — needs AI evaluation
        if not ANTHROPIC_KEY:
            return {"resolved": False, "updated_description": None}

        try:
            # Reload with comments
            action_result = await self.db.execute(
                select(AgentAction)
                .options(selectinload(AgentAction.comments))
                .where(AgentAction.id == action.id, AgentAction.organization_id == org_id)
            )
            action_full = action_result.scalar_one()

            comments_text = "\n".join(
                f"- {c.author}: {c.text}" for c in action_full.comments
            )

            prompt = EVAL_PROMPT.format(
                action_type=action_full.action_type,
                description=action_full.description,
                assigned_to=action_full.assigned_to or "unassigned",
                comments=comments_text,
                author=author,
                latest_comment=comment_text.strip(),
            )

            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            with AgentTimer() as timer:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )

            text = response.content[0].text
            usage = response.usage

            await log_agent_call(
                organization_id=org_id,
                agent_name="resolution_evaluator",
                action="evaluate",
                input_summary=f"Job: {action.description[:60]} | Comment: {comment_text[:60]}",
                output_summary=text[:200],
                success=True,
                model=MODEL,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                duration_ms=timer.duration_ms,
            )

            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                if data.get("update_description"):
                    action.description = data["update_description"]
                    updated_desc = action.description
                if data.get("update_type"):
                    action.action_type = data["update_type"]

                if data.get("resolved"):
                    action.status = "done"
                    action.completed_at = datetime.now(timezone.utc)
                    resolved = True

                await self.db.commit()

        except Exception as e:
            logger.error(f"Resolution evaluation failed: {e}")
            await log_agent_call(
                organization_id=org_id,
                agent_name="resolution_evaluator",
                action="evaluate",
                input_summary=f"Job: {action.description[:60]}",
                success=False,
                error=str(e),
                model=MODEL,
            )

        return {"resolved": resolved, "updated_description": updated_desc}
