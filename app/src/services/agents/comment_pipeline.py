"""Comment pipeline orchestrator — routes comments through focused agents.

Classifies each comment, then delegates to the appropriate agent:
  question     -> DeepBlueResponder (answer from DB)
  command      -> CommandExecutor (draft email, assign, etc.)
  status_update -> ResolutionEvaluator (check if job is done)
  completion   -> ResolutionEvaluator (mark done)
  info_only    -> no action
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction

from .comment_classifier import classify_comment
from .command_executor import CommandExecutor
from .deepblue_responder import DeepBlueResponder
from .resolution_evaluator import ResolutionEvaluator

logger = logging.getLogger(__name__)


class CommentPipeline:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_comment(
        self,
        org_id: str,
        action: AgentAction,
        comment_text: str,
        user_id: str,
        user_name: str,
        build_customer_context_fn,
        find_org_user_fn,
    ) -> dict:
        """Run the comment through classify -> route -> execute pipeline.

        Returns:
            {
                "auto_comment": dict|None,  -- DeepBlue auto-reply
                "action_resolved": bool,
                "updated_description": str|None,
            }
        """
        result = {
            "auto_comment": None,
            "action_resolved": False,
            "updated_description": None,
        }

        # Only process open/in-progress jobs
        if action.status not in ("open", "in_progress"):
            return result

        try:
            # 1. Classify
            intent = await classify_comment(
                comment_text=comment_text,
                job_description=action.description,
                job_type=action.action_type,
                job_status=action.status,
                assigned_to=action.assigned_to,
                author=user_name,
                org_id=org_id,
            )

            intent_type = intent.get("intent", "info_only")
            logger.info(f"Comment classified: {intent_type} (sub={intent.get('sub_intent')})")

            # 2. Route
            if intent_type == "question":
                customer_id, customer_context = await build_customer_context_fn(org_id, action)
                responder = DeepBlueResponder(self.db)
                auto = await responder.respond(
                    org_id=org_id,
                    action=action,
                    comment_text=comment_text,
                    customer_context=customer_context,
                    user_id=user_id,
                    find_org_user_fn=find_org_user_fn,
                )
                result["auto_comment"] = auto

            elif intent_type == "command":
                customer_id, customer_context = await build_customer_context_fn(org_id, action)
                executor = CommandExecutor(self.db)
                cmd_result = await executor.execute(
                    org_id=org_id,
                    action=action,
                    intent=intent,
                    user_id=user_id,
                    user_name=user_name,
                    customer_context=customer_context,
                    customer_id=customer_id,
                    find_org_user_fn=find_org_user_fn,
                )
                result["auto_comment"] = cmd_result
                if cmd_result and cmd_result.get("action_resolved"):
                    result["action_resolved"] = True

            elif intent_type in ("status_update", "completion"):
                evaluator = ResolutionEvaluator(self.db)
                eval_result = await evaluator.evaluate(
                    org_id=org_id,
                    action=action,
                    comment_text=comment_text,
                    intent=intent,
                    author=user_name,
                )
                result["action_resolved"] = eval_result.get("resolved", False)
                result["updated_description"] = eval_result.get("updated_description")

            # info_only: no action needed

        except Exception as e:
            # Graceful failure — comment was already saved
            logger.error(f"Comment pipeline error: {e}", exc_info=True)

        return result
