"""Comment classifier agent — determines intent of job comments.

Single responsibility: classify a comment into an intent type + sub-intent.
Does NOT take any action.
"""

import json
import logging
import os
import re

import anthropic

from .observability import AgentTimer, log_agent_call

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"

# Priority order for mixed intents (most actionable first)
INTENT_PRIORITY = ["command", "completion", "status_update", "question", "info_only"]

CLASSIFY_PROMPT = """Classify this comment on a pool service job into exactly one intent.

Job context:
{job_context}

Comment by {author}: "{comment}"

Intents:
- question: asking for information ("what's the gate code?", "do we have their email?", "need the address")
- command: requesting an action ("draft email to let them know", "create estimate", "assign to Shane", "schedule for Thursday", "notify the customer", "mark as done", "send email")
- status_update: reporting progress ("visited today, pump is overheating", "installed the filter", "parts on order")
- completion: explicitly marking work done ("completed", "all done", "finished the repair", "job's done")
- info_only: general note, no action needed ("FYI the gate code changed", "spoke with manager")

For MIXED comments (e.g. "installed filter, draft email to let them know"):
Pick the MOST ACTIONABLE: command > completion > status_update > question > info_only

For command intent, also identify the sub_intent:
- draft_email: draft an email to customer
- send_email: send email immediately
- create_estimate: generate estimate/invoice
- assign: reassign the job (details = who)
- update_status: change job status (details = new status)
- schedule: schedule work (details = when)
- notify: notify someone (details = who)
- mark_done: close the job

Respond with ONLY this JSON:
{{"intent": "...", "sub_intent": "..." or null, "details": "..." or null}}"""


async def classify_comment(
    comment_text: str,
    job_description: str,
    job_type: str,
    job_status: str,
    assigned_to: str | None,
    author: str,
    org_id: str = "",
) -> dict:
    """Classify a comment's intent. Returns {intent, sub_intent, details}."""
    if not ANTHROPIC_KEY:
        return {"intent": "info_only", "sub_intent": None, "details": None}

    job_context = (
        f"Type: {job_type}\n"
        f"Description: {job_description}\n"
        f"Status: {job_status}\n"
        f"Assigned to: {assigned_to or 'unassigned'}"
    )

    prompt = CLASSIFY_PROMPT.format(
        job_context=job_context,
        author=author,
        comment=comment_text.strip(),
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        with AgentTimer() as timer:
            response = client.messages.create(
                model=MODEL,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )

        text = response.content[0].text
        usage = response.usage

        await log_agent_call(
            organization_id=org_id,
            agent_name="comment_classifier",
            action="classify",
            input_summary=f"{author}: {comment_text[:100]}",
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
            intent = data.get("intent", "info_only")
            if intent not in INTENT_PRIORITY:
                intent = "info_only"
            return {
                "intent": intent,
                "sub_intent": data.get("sub_intent"),
                "details": data.get("details"),
            }

    except Exception as e:
        logger.error(f"Comment classification failed: {e}")
        await log_agent_call(
            organization_id=org_id,
            agent_name="comment_classifier",
            action="classify",
            input_summary=f"{author}: {comment_text[:100]}",
            success=False,
            error=str(e),
            model=MODEL,
        )

    return {"intent": "info_only", "sub_intent": None, "details": None}
