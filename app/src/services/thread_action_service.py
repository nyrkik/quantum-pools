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

    async def _record_send_failure(self, **kwargs) -> None:
        """Thin wrapper around the shared helper so callers in this service
        don't have to thread `self.db` explicitly. See
        `services/agents/send_failure.py` for the contract."""
        from src.services.agents.send_failure import record_outbound_send_failure
        await record_outbound_send_failure(self.db, **kwargs)

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

        # Wrap the entire send + bookkeeping in try/except — same pattern as
        # compose_and_send (FB-24). Without it, any exception (including the
        # send call itself) leaves the inbound msg stuck in 'pending' with no
        # record that the user attempted a reply.
        email_svc = EmailService(self.db)
        outbound_subject = f"Re: {msg.subject}" if msg.subject and not msg.subject.startswith("Re:") else msg.subject
        try:
            send_result = await email_svc.send_agent_reply(
                org_id, msg.from_email, msg.subject or "", final_text,
                from_address=from_addr, sender_name=user_name,
                attachments=email_atts or None,
            )
            if not send_result.success:
                await self._record_send_failure(
                    org_id=org_id, thread_id=thread_id,
                    from_email=from_addr or AGENT_FROM_EMAIL, to_email=msg.from_email,
                    subject=outbound_subject, body=final_text,
                    matched_customer_id=msg.matched_customer_id,
                    customer_name=msg.customer_name,
                    error=send_result.error or "send returned success=False",
                )
                return {"error": "send_failed", "detail": send_result.error or "Failed to send email"}

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
                subject=outbound_subject,
                body=final_text,
                status="sent",
                thread_id=thread_id,
                matched_customer_id=msg.matched_customer_id,
                customer_name=msg.customer_name,
                approved_by=user_name,
                approved_at=now,
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
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"approve_thread crashed for thread {thread_id}: {exc}")
            await self._record_send_failure(
                org_id=org_id, thread_id=thread_id,
                from_email=from_addr or AGENT_FROM_EMAIL, to_email=msg.from_email,
                subject=outbound_subject, body=final_text,
                matched_customer_id=msg.matched_customer_id,
                customer_name=msg.customer_name,
                error=f"{type(exc).__name__}: {exc}",
            )
            return {"error": "send_failed", "detail": f"{type(exc).__name__}: {exc}"}

    async def _find_latest_stuck_outbound(self, org_id: str, thread_id: str) -> AgentMessage | None:
        """Return the most-recent outbound message in a thread IF it's in a
        stuck state (queued/failed/bounced/delivery_error). Mirrors the
        Outbox folder's filter so retry/discard operate on the same row the
        folder surfaces."""
        latest = (await self.db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.thread_id == thread_id,
                AgentMessage.organization_id == org_id,
                AgentMessage.direction == "outbound",
            )
            .order_by(desc(AgentMessage.received_at))
            .limit(1)
        )).scalar_one_or_none()
        if not latest:
            return None
        is_stuck = (
            latest.status in ("failed", "queued")
            or latest.delivery_status in ("bounced", "spam_complaint")
            or bool(latest.delivery_error)
        )
        return latest if is_stuck else None

    async def retry_outbound(self, org_id: str, thread_id: str, user_name: str) -> dict:
        """Retry sending the latest stuck outbound message.

        Uses the original to/subject/body. On success, inserts a NEW outbound
        row with status='sent'. The stuck row stays in the timeline as an
        audit record (status/error unchanged) so failed attempts remain
        visible. Thread drops out of Outbox because the new outbound is now
        the most-recent one.
        """
        from src.services.agents.thread_manager import update_thread_status
        from src.services.email_service import EmailService

        stuck = await self._find_latest_stuck_outbound(org_id, thread_id)
        if not stuck:
            return {"error": "not_stuck", "detail": "No stuck outbound message in this thread"}

        thread_obj = (await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id)
        )).scalar_one_or_none()
        from_addr = thread_obj.delivered_to if thread_obj and thread_obj.delivered_to else None

        email_svc = EmailService(self.db)
        try:
            send_result = await email_svc.send_agent_reply(
                org_id, stuck.to_email, stuck.subject or "", stuck.body or "",
                from_address=from_addr, sender_name=user_name,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("retry_outbound send failed")
            return {"error": "send_failed", "detail": str(e)}

        if not send_result.success:
            return {"error": "send_failed", "detail": send_result.error or "Retry did not succeed"}

        now = datetime.now(timezone.utc)
        outbound = AgentMessage(
            organization_id=org_id,
            direction="outbound",
            from_email=from_addr or stuck.from_email or AGENT_FROM_EMAIL,
            to_email=stuck.to_email,
            subject=stuck.subject,
            body=stuck.body,
            status="sent",
            thread_id=thread_id,
            matched_customer_id=stuck.matched_customer_id,
            customer_name=stuck.customer_name,
            approved_by=user_name,
            approved_at=now,
            sent_at=now,
            received_at=now,
            notes=f"Retry of message {stuck.id} ({stuck.received_at.isoformat()})",
        )
        self.db.add(outbound)
        await self.db.commit()
        await update_thread_status(thread_id)
        return {"retried": True, "outbound_message_id": outbound.id}

    async def discard_outbound(self, org_id: str, thread_id: str, user_name: str) -> dict:
        """Discard the latest stuck outbound message.

        User has decided not to retry — flips status to 'rejected' so the
        Outbox filter no longer matches (filter checks `status IN
        ('failed','queued')`, delivery_status, and delivery_error). The
        message row stays for audit; reason gets noted.
        """
        from src.services.agents.thread_manager import update_thread_status

        stuck = await self._find_latest_stuck_outbound(org_id, thread_id)
        if not stuck:
            return {"error": "not_stuck", "detail": "No stuck outbound message in this thread"}

        stuck.status = "rejected"
        stuck.delivery_error = None  # clear so it doesn't keep matching the Outbox filter via delivery_error
        stuck.notes = ((stuck.notes or "") + f"\nDiscarded by {user_name}").strip()

        await self.db.commit()
        await update_thread_status(thread_id)
        return {"discarded": True, "message_id": stuck.id}

    async def dismiss_thread(self, org_id: str, thread_id: str, user_name: str, actor=None) -> dict:
        """Dismiss all pending messages in a thread."""
        from src.services.agents.thread_manager import update_thread_status
        from src.services.events.platform_event_service import PlatformEventService
        from src.services.events.actor_factory import actor_system

        # Load the thread to capture prior status for the event payload.
        prior_status_row = await self.db.execute(
            select(AgentThread.status).where(
                AgentThread.id == thread_id,
                AgentThread.organization_id == org_id,
            )
        )
        prior_status = prior_status_row.scalar_one_or_none()

        result = await self.db.execute(
            select(AgentMessage).where(
                AgentMessage.thread_id == thread_id,
                AgentMessage.organization_id == org_id,
                AgentMessage.status == "pending",
            )
        )
        from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_CLASSIFIER
        learner = AgentLearningService(self.db)
        dismissed_count = 0
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
            dismissed_count += 1

        await PlatformEventService.emit(
            db=self.db,
            event_type="thread.status_changed",
            level="user_action" if actor and actor.actor_type == "user" else "system_action",
            actor=actor or actor_system(),
            organization_id=org_id,
            entity_refs={"thread_id": thread_id},
            payload={
                "from": prior_status,
                "to": "ignored",
                "reason": "dismissed",
                "messages_dismissed": dismissed_count,
            },
        )

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
        outbound_subject = f"Re: {thread.subject}" if thread.subject and not thread.subject.startswith("Re:") else thread.subject
        email_svc = EmailService(self.db)
        try:
            send_result = await email_svc.send_agent_reply(
                org_id, thread.contact_email, thread.subject or "", text,
                from_address=from_addr, sender_name=user_name,
                attachments=email_atts or None,
            )
            if not send_result.success:
                await self._record_send_failure(
                    org_id=org_id, thread_id=thread_id,
                    from_email=from_addr or AGENT_FROM_EMAIL, to_email=thread.contact_email,
                    subject=outbound_subject, body=text,
                    matched_customer_id=thread.matched_customer_id,
                    customer_name=thread.customer_name,
                    error=send_result.error or "send returned success=False",
                )
                return {"error": "send_failed", "detail": send_result.error or "Failed to send"}

            now = datetime.now(timezone.utc)
            outbound = AgentMessage(
                organization_id=org_id,
                direction="outbound",
                from_email=from_addr or AGENT_FROM_EMAIL,
                to_email=thread.contact_email,
                subject=outbound_subject,
                body=text,
                status="sent",
                thread_id=thread_id,
                matched_customer_id=thread.matched_customer_id,
                customer_name=thread.customer_name,
                approved_by=user_name,
                approved_at=now,
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
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"send_followup crashed for thread {thread_id}: {exc}")
            await self._record_send_failure(
                org_id=org_id, thread_id=thread_id,
                from_email=from_addr or AGENT_FROM_EMAIL, to_email=thread.contact_email,
                subject=outbound_subject, body=text,
                matched_customer_id=thread.matched_customer_id,
                customer_name=thread.customer_name,
                error=f"{type(exc).__name__}: {exc}",
            )
            return {"error": "send_failed", "detail": f"{type(exc).__name__}: {exc}"}

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
