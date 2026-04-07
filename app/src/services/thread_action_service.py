"""Thread action service — email sending, approval, dismissal, follow-up.

Split from AgentThreadService to isolate email-sending operations
from thread CRUD/query operations.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from anthropic import AsyncAnthropic
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.ai_models import get_model
from src.models.agent_action import AgentAction
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.message_attachment import MessageAttachment
from src.models.notification import Notification

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AGENT_FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")

UPLOAD_ROOT = Path(os.environ.get("UPLOAD_DIR", "./uploads"))


class ThreadActionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_email_attachments(self, org_id: str, attachment_ids: list[str]) -> tuple[list[dict], list[MessageAttachment]]:
        """Load attachment files from disk for email sending. Returns (email_dicts, db_rows)."""
        rows = (await self.db.execute(
            select(MessageAttachment).where(
                MessageAttachment.id.in_(attachment_ids[:5]),
                MessageAttachment.organization_id == org_id,
                MessageAttachment.source_type == "agent_message",
                MessageAttachment.source_id.is_(None),
            )
        )).scalars().all()
        email_atts = []
        for a in rows:
            fpath = UPLOAD_ROOT / "attachments" / a.organization_id / a.stored_filename
            if fpath.exists():
                email_atts.append({
                    "filename": a.filename,
                    "content_bytes": fpath.read_bytes(),
                    "mime_type": a.mime_type,
                })
        return email_atts, list(rows)

    async def _find_assignee_user(self, org_id: str, assigned_to_name: str) -> str | None:
        """Find user_id from assigned_to name string."""
        from src.models.organization_user import OrganizationUser
        from src.models.user import User
        first_name = assigned_to_name.split()[0]
        result = await self.db.execute(
            select(OrganizationUser.user_id)
            .join(User, User.id == OrganizationUser.user_id)
            .where(OrganizationUser.organization_id == org_id, User.first_name == first_name)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def approve_thread(self, org_id: str, thread_id: str, response_text: str | None, user_name: str, attachment_ids: list[str] | None = None) -> dict:
        """Approve the latest pending message in a thread — send email and update status."""
        from src.services.agents.thread_manager import update_thread_status
        from src.services.agents.orchestrator import save_discovered_contact
        from src.services.email_service import EmailService

        result = await self.db.execute(
            select(AgentMessage)
            .where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == org_id, AgentMessage.status == "pending", AgentMessage.direction == "inbound")
            .order_by(desc(AgentMessage.received_at))
            .limit(1)
        )
        msg = result.scalar_one_or_none()
        if not msg:
            return {"error": "no_pending", "detail": "No pending message in this thread"}

        final_text = response_text or msg.draft_response
        if not final_text:
            return {"error": "no_text", "detail": "No response text provided"}

        # Determine FROM address: use thread's delivered_to if available
        thread_obj = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id))).scalar_one_or_none()
        from_addr = (thread_obj.delivered_to if thread_obj and thread_obj.delivered_to else None)

        # Load attachments for email
        email_atts, att_rows = None, []
        if attachment_ids:
            email_atts, att_rows = await self._load_email_attachments(org_id, attachment_ids)

        email_svc = EmailService(self.db)
        send_result = await email_svc.send_agent_reply(
            org_id, msg.from_email, msg.subject or "", final_text,
            from_address=from_addr, sender_name=user_name,
            attachments=email_atts or None,
        )
        if not send_result.success:
            return {"error": "send_failed", "detail": "Failed to send email"}

        now = datetime.now(timezone.utc)
        msg.status = "sent"
        msg.final_response = final_text
        msg.approved_by = user_name
        msg.approved_at = now
        msg.sent_at = now

        # Create outbound message row
        outbound = AgentMessage(
            organization_id=org_id,
            direction="outbound",
            from_email=from_addr or AGENT_FROM_EMAIL,
            to_email=msg.from_email,
            subject=f"Re: {msg.subject}" if msg.subject and not msg.subject.startswith("Re:") else msg.subject,
            body=final_text,
            status="sent",
            thread_id=thread_id,
            matched_customer_id=msg.matched_customer_id,
            customer_name=msg.customer_name,
            sent_at=now,
            received_at=now,
        )
        self.db.add(outbound)
        await self.db.flush()

        # Claim attachments against outbound message
        for a in att_rows:
            a.source_id = outbound.id

        # Record correction for agent learning
        from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_CLASSIFIER
        learner = AgentLearningService(self.db)
        draft = msg.draft_response
        if draft and final_text != draft:
            await learner.record_correction(
                org_id, AGENT_EMAIL_CLASSIFIER, "edit",
                original_output=draft, corrected_output=final_text,
                input_context=f"Subject: {msg.subject}\nFrom: {msg.from_email}",
                category=msg.category, customer_id=msg.matched_customer_id,
                source_id=msg.id, source_type="agent_message",
            )
        elif draft and final_text == draft:
            await learner.record_correction(
                org_id, AGENT_EMAIL_CLASSIFIER, "acceptance",
                original_output=draft,
                category=msg.category, customer_id=msg.matched_customer_id,
                source_id=msg.id, source_type="agent_message",
            )

        await self.db.commit()

        await update_thread_status(thread_id)
        await save_discovered_contact(msg.id)

        return {"sent": True, "to": msg.from_email}

    async def dismiss_thread(self, org_id: str, thread_id: str, user_name: str) -> dict:
        """Dismiss all pending messages in a thread."""
        from src.services.agents.thread_manager import update_thread_status

        result = await self.db.execute(
            select(AgentMessage).where(
                AgentMessage.thread_id == thread_id,
                AgentMessage.organization_id == org_id,
                AgentMessage.status == "pending",
            )
        )
        from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_CLASSIFIER
        learner = AgentLearningService(self.db)
        for msg in result.scalars().all():
            # Record rejection for learning
            if msg.draft_response:
                await learner.record_correction(
                    msg.organization_id, AGENT_EMAIL_CLASSIFIER, "rejection",
                    original_output=msg.draft_response,
                    input_context=f"Subject: {msg.subject}\nFrom: {msg.from_email}",
                    category=msg.category, customer_id=msg.matched_customer_id,
                    source_id=msg.id, source_type="agent_message",
                )
            msg.status = "ignored"
            msg.notes = (msg.notes or "") + f"\nDismissed by {user_name}"
            msg.notes = msg.notes.strip()
        await self.db.commit()
        await update_thread_status(thread_id)
        return {"dismissed": True}

    async def send_followup(self, org_id: str, thread_id: str, text: str, user_name: str, attachment_ids: list[str] | None = None) -> dict:
        """Send a follow-up in a thread and evaluate if open jobs should close."""
        from src.services.agents.thread_manager import update_thread_status
        from src.services.email_service import EmailService

        thread = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        if not text:
            return {"error": "no_text", "detail": "No response text"}

        # Load attachments for email
        email_atts, att_rows = None, []
        if attachment_ids:
            email_atts, att_rows = await self._load_email_attachments(org_id, attachment_ids)

        from_addr = thread.delivered_to if thread.delivered_to else None
        email_svc = EmailService(self.db)
        send_result = await email_svc.send_agent_reply(
            org_id, thread.contact_email, thread.subject or "", text,
            from_address=from_addr, sender_name=user_name,
            attachments=email_atts or None,
        )
        if not send_result.success:
            return {"error": "send_failed", "detail": "Failed to send"}

        now = datetime.now(timezone.utc)
        outbound = AgentMessage(
            organization_id=org_id,
            direction="outbound",
            from_email=from_addr or AGENT_FROM_EMAIL,
            to_email=thread.contact_email,
            subject=f"Re: {thread.subject}" if thread.subject and not thread.subject.startswith("Re:") else thread.subject,
            body=text,
            status="sent",
            thread_id=thread_id,
            matched_customer_id=thread.matched_customer_id,
            customer_name=thread.customer_name,
            sent_at=now,
            received_at=now,
        )
        self.db.add(outbound)
        await self.db.flush()

        # Claim attachments against outbound message
        for a in att_rows:
            a.source_id = outbound.id

        await self.db.commit()
        await update_thread_status(thread_id)

        # Evaluate if open jobs for this thread should be closed
        closed_actions = await self._evaluate_followup_actions(org_id, thread_id, text, now)

        return {"sent": True, "to": thread.contact_email, "closed_actions": closed_actions}

    async def _evaluate_followup_actions(self, org_id: str, thread_id: str, response_text: str, now: datetime) -> list[dict]:
        """Use Claude to evaluate if open jobs should be closed after a follow-up."""
        closed_actions = []
        try:
            actions_result = await self.db.execute(
                select(AgentAction)
                .options(selectinload(AgentAction.comments))
                .where(
                    AgentAction.thread_id == thread_id,
                    AgentAction.organization_id == org_id,
                    AgentAction.status.in_(("open", "in_progress")),
                )
            )
            open_actions = actions_result.scalars().all()

            if open_actions:
                actions_list = []
                for a in open_actions:
                    comments_text = ""
                    if a.comments:
                        comments_text = " | Comments: " + "; ".join(c.text for c in a.comments)
                    actions_list.append(f"- ID:{a.id[:8]} [{a.action_type}] {a.description}{comments_text}")

                eval_prompt = f"""A follow-up email was just sent in a conversation thread. Based on its content, determine which open jobs are now complete.

Follow-up email sent:
{response_text}

Open jobs:
{chr(10).join(actions_list)}

For each job, respond with JSON array:
[{{"id": "first8chars", "status": "done|open", "reason": "why"}}]

Rules:
- "done" = the follow-up clearly addresses/completes this job
- "open" = still needs work
- Be conservative — only mark done if clearly covered"""

                client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
                eval_response = await client.messages.create(
                    model=await get_model("fast"),
                    max_tokens=300,
                    messages=[{"role": "user", "content": eval_prompt}],
                )
                json_match = re.search(r"\[.*\]", eval_response.content[0].text, re.DOTALL)
                if json_match:
                    evaluations = json.loads(json_match.group())
                    for ev in evaluations:
                        if ev.get("status") == "done":
                            for a in open_actions:
                                if a.id.startswith(ev.get("id", "")):
                                    a.status = "done"
                                    a.completed_at = now
                                    closed_actions.append({"description": a.description})
                                    # Notify assignee
                                    if a.assigned_to:
                                        target = await self._find_assignee_user(org_id, a.assigned_to)
                                        if target:
                                            self.db.add(Notification(
                                                organization_id=org_id,
                                                user_id=target,
                                                type="job_completed",
                                                title=f"Job auto-completed: {(a.description or '')[:50]}",
                                                body="Closed after follow-up email resolved the issue",
                                                link=f"/jobs?action={a.id}",
                                            ))
                    await self.db.commit()
        except Exception as e:
            logger.error(f"Thread follow-up job eval failed: {e}")

        return closed_actions
