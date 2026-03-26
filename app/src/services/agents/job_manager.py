"""Job lifecycle: creation, evaluation, next steps."""
from src.core.ai_models import get_model

import os
import re
import json
import logging

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.core.database import get_db_context
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction
from src.models.customer import Customer

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


async def evaluate_next_action(action_id: str) -> dict | None:
    """When an action is completed, use Claude to evaluate if a follow-up is needed.
    Returns a recommended action dict or None."""
    async with get_db_context() as db:
        # Load the completed action + parent message + all sibling actions
        action_result = await db.execute(
            select(AgentAction).where(AgentAction.id == action_id)
        )
        action = action_result.scalar_one_or_none()
        if not action:
            return None

        # Standalone jobs (no email) can't be auto-evaluated
        if not action.agent_message_id:
            return None

        msg_result = await db.execute(
            select(AgentMessage).where(AgentMessage.id == action.agent_message_id)
        )
        msg = msg_result.scalar_one_or_none()
        if not msg:
            return None

        # Get all actions for this message with comments
        siblings_result = await db.execute(
            select(AgentAction)
            .options(selectinload(AgentAction.comments))
            .where(AgentAction.agent_message_id == msg.id)
        )
        all_actions = siblings_result.scalars().all()

        # Build context for Claude
        actions_summary = []
        for a in all_actions:
            status_label = a.status
            if a.id == action_id:
                status_label = "JUST COMPLETED"
            line = f"- [{status_label}] {a.action_type}: {a.description}"
            if a.notes:
                line += f"\n  Notes: {a.notes}"
            if a.comments:
                for c in a.comments:
                    line += f"\n  Comment ({c.author}): {c.text}"
            actions_summary.append(line)

        # Get customer context if matched
        customer_info = ""
        if msg.matched_customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == msg.matched_customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            if customer:
                customer_info = f"\nCustomer: {customer.display_name} ({customer.customer_type})"
                if customer.company_name:
                    customer_info += f" — {customer.company_name}"

    # Check if a follow-up was recently sent
    followup_note = ""
    if msg.notes and "Follow-up sent" in msg.notes:
        followup_note = f"\n\nIMPORTANT: A follow-up email was already sent to the client. Notes: {msg.notes}"

    prompt = f"""An action item was just completed for a pool service company. Based on the context, determine if there is a logical next step.

Original email from {msg.from_email}:
Subject: {msg.subject}
{msg.body[:500] if msg.body else 'No body'}
{customer_info}

Our response: {msg.final_response[:300] if msg.final_response else msg.draft_response[:300] if msg.draft_response else 'Not yet responded'}{followup_note}

Action items for this event:
{chr(10).join(actions_summary)}

Based on the completed action and the overall situation, is there a natural next step?

Respond with JSON:
{{
  "has_next": true/false,
  "action_type": "follow_up|bid|schedule_change|site_visit|callback|repair|equipment|invoice|other",
  "description": "detailed description including ALL specifics from the conversation — part numbers, model names, prices, client approvals, addresses. Never be vague when details exist in the comments.",
  "due_days": 3,
  "reasoning": "why this is the logical next step"
}}

Rules:
- CRITICAL: The description must include every relevant detail from the comments and conversation. If a filter model (SM7), part number, price ($500), or client name (Ashley) was mentioned, include it. "Replace filter" is BAD. "Order and install SM7 spa filter at Coventry Park (751 Central Park Dr) — approved by Ashley Overton" is GOOD.
- Only recommend a next step if it's genuinely needed — don't create busywork
- If all necessary work is covered by existing open actions, return has_next: false
- If a follow-up email was already sent to the client about this issue, do NOT suggest calling or emailing them again about the same thing
- Common patterns:
  - site_visit done → report findings to client or schedule repair
  - repair/equipment done → send invoice for the work (action_type: "invoice")
  - bid sent → follow up if no response in a few days
  - invoice sent → follow up on payment if overdue
- When physical work is completed (repair, equipment replacement, site_visit with billable work), ALWAYS suggest sending an invoice as the next step unless one was already mentioned
- action_type "invoice" means "create and send invoice for this work"
- Keep description concise — one task, not multiple steps"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model=await get_model("fast"),
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if result.get("has_next"):
                return {
                    "agent_message_id": msg.id,
                    "action_type": result.get("action_type", "follow_up"),
                    "description": result.get("description", ""),
                    "due_days": result.get("due_days", 3),
                    "reasoning": result.get("reasoning", ""),
                }
    except Exception as e:
        logger.error(f"Failed to evaluate next action: {e}")

    return None
