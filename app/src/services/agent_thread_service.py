"""Service layer for agent thread (conversation) business logic."""

from src.core.ai_models import get_model
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import anthropic
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.notification import Notification
from src.models.property import Property
from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AGENT_FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")
AGENT_FROM_NAME = os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")


from src.presenters.action_presenter import ActionPresenter
from src.presenters.thread_presenter import ThreadPresenter


class AgentThreadService:
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

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_clients(self, org_id: str, q: str) -> list[dict]:
        """Search customers + properties for autocomplete."""
        search = f"%{q}%"
        result = await self.db.execute(
            select(Customer, Property)
            .join(Property, Customer.id == Property.customer_id)
            .where(
                Property.organization_id == org_id,
                Customer.is_active == True,
            )
            .where(
                Customer.first_name.ilike(search)
                | Customer.last_name.ilike(search)
                | Customer.company_name.ilike(search)
                | Customer.display_name_col.ilike(search)
                | Property.address.ilike(search)
                | Property.name.ilike(search)
            )
            .order_by(Customer.first_name)
            .limit(10)
        )
        return [
            {
                "customer_name": cust.display_name,
                "property_address": prop.full_address,
                "property_name": prop.name,
            }
            for cust, prop in result.all()
        ]

    async def list_threads(
        self,
        org_id: str,
        status: str | None,
        search: str | None,
        exclude_spam: bool,
        exclude_ignored: bool,
        limit: int,
        offset: int,
        assigned_to: str | None = None,
        customer_id: str | None = None,
        current_user_id: str | None = None,
        user_permission_slugs: set[str] | None = None,
    ) -> dict:
        """List conversation threads with filtering."""
        base = select(AgentThread).where(AgentThread.organization_id == org_id)
        if status == "pending":
            base = base.where(AgentThread.has_pending == True)
        elif status == "handled":
            base = base.where(AgentThread.status == "handled")
        elif status == "ignored":
            base = base.where(AgentThread.status == "ignored")
        elif status == "archived":
            base = base.where(AgentThread.status == "archived")
        else:
            # Default: exclude archived
            base = base.where(AgentThread.status != "archived")
        if exclude_spam:
            base = base.where(AgentThread.category.notin_(["spam", "auto_reply"]) | AgentThread.category.is_(None))
        if exclude_ignored:
            base = base.where(AgentThread.status != "ignored")
        if assigned_to:
            base = base.where(AgentThread.assigned_to_user_id == assigned_to)
        if customer_id:
            base = base.where(AgentThread.matched_customer_id == customer_id)
        # Visibility filtering: only show threads the user has permission to see
        if user_permission_slugs is not None:
            from sqlalchemy import or_
            base = base.where(
                or_(
                    AgentThread.visibility_permission.is_(None),
                    AgentThread.visibility_permission.in_(user_permission_slugs),
                )
            )
        if search:
            q = f"%{search}%"
            base = base.where(
                AgentThread.contact_email.ilike(q)
                | AgentThread.subject.ilike(q)
                | AgentThread.customer_name.ilike(q)
            )
        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
        result = await self.db.execute(
            base.order_by(
                desc(AgentThread.has_pending),
                desc(AgentThread.last_message_at),
            ).offset(offset).limit(limit)
        )
        threads = result.scalars().all()

        presenter = ThreadPresenter(self.db)
        items = await presenter.many(threads)

        return {"items": items, "total": total}

    async def get_thread_stats(self, org_id: str, user_permission_slugs: set[str] | None = None) -> dict:
        """Thread-level stats. If user_permission_slugs provided, counts only visible threads."""
        from sqlalchemy import or_
        thread_org = AgentThread.organization_id == org_id

        def _vis_filter(q):
            """Apply visibility filter if permissions are scoped."""
            if user_permission_slugs is not None:
                return q.where(or_(
                    AgentThread.visibility_permission.is_(None),
                    AgentThread.visibility_permission.in_(user_permission_slugs),
                ))
            return q

        total = (await self.db.execute(
            _vis_filter(select(func.count(AgentThread.id)).where(thread_org))
        )).scalar() or 0
        pending = (await self.db.execute(
            _vis_filter(select(func.count(AgentThread.id)).where(thread_org, AgentThread.has_pending == True))
        )).scalar() or 0

        # Stale: pending threads where last_message_at > 30 min ago
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        stale = (await self.db.execute(
            _vis_filter(select(func.count(AgentThread.id)).where(
                thread_org,
                AgentThread.has_pending == True,
                AgentThread.last_message_at < stale_cutoff,
            ))
        )).scalar() or 0

        open_actions = (await self.db.execute(
            select(func.count(AgentAction.id)).where(
                AgentAction.organization_id == org_id,
                AgentAction.status.in_(("open", "in_progress")),
                AgentAction.is_suggested == False,
            )
        )).scalar() or 0

        return {
            "total": total,
            "pending": pending,
            "stale_pending": stale,
            "open_actions": open_actions,
        }

    async def get_thread_detail(self, org_id: str, thread_id: str, user_permission_slugs: set[str] | None = None) -> dict | None:
        """Get thread with full conversation timeline.

        Returns None if thread doesn't exist or user lacks required visibility permission.
        """
        result = await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))
        thread = result.scalar_one_or_none()
        if not thread:
            return None

        # Visibility check
        if user_permission_slugs is not None and thread.visibility_permission:
            if thread.visibility_permission not in user_permission_slugs:
                return None

        # Get all messages in thread
        msgs_result = await self.db.execute(
            select(AgentMessage)
            .where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == org_id)
            .order_by(AgentMessage.received_at)
        )
        messages = msgs_result.scalars().all()

        # Build conversation timeline
        timeline = []
        for m in messages:
            timeline.append({
                "id": m.id,
                "direction": m.direction,
                "from_email": m.from_email,
                "to_email": m.to_email,
                "subject": m.subject,
                "body": strip_email_signature(strip_quoted_reply(m.body)) if m.body else None,
                "body_full": m.body,
                "category": m.category,
                "urgency": m.urgency,
                "status": m.status,
                "draft_response": m.draft_response if m.status == "pending" else None,
                "received_at": m.received_at.isoformat() if m.received_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "approved_by": m.approved_by,
            })
            # If inbound message was sent and has final_response, add outbound bubble
            # (for historical messages before we started creating outbound rows)
            if m.direction == "inbound" and m.final_response and m.status in ("sent", "auto_sent"):
                has_outbound = any(
                    om.direction == "outbound" and om.sent_at and m.sent_at
                    and abs((om.sent_at - m.sent_at).total_seconds()) < 60
                    for om in messages
                )
                if not has_outbound:
                    timeline.append({
                        "id": f"{m.id}-reply",
                        "direction": "outbound",
                        "from_email": AGENT_FROM_EMAIL,
                        "to_email": m.from_email,
                        "subject": f"Re: {m.subject}" if m.subject else None,
                        "body": m.final_response,
                        "category": None,
                        "urgency": None,
                        "status": "sent",
                        "draft_response": None,
                        "received_at": m.sent_at.isoformat() if m.sent_at else m.received_at.isoformat(),
                        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                        "approved_by": m.approved_by,
                    })

        # Get actions for this thread
        actions_result = await self.db.execute(
            select(AgentAction)
            .options(selectinload(AgentAction.comments))
            .where(AgentAction.thread_id == thread_id, AgentAction.organization_id == org_id)
            .order_by(AgentAction.created_at)
        )
        actions = await ActionPresenter(self.db).many(list(actions_result.scalars().all()))

        presenter = ThreadPresenter(self.db)
        d = await presenter.one(thread)
        d["routing_rule_id"] = thread.routing_rule_id
        d["timeline"] = timeline
        d["actions"] = actions
        return d

    async def approve_thread(self, org_id: str, thread_id: str, response_text: str | None, user_name: str) -> dict:
        """Approve the latest pending message in a thread — send email and update status."""
        from src.services.customer_agent import update_thread_status, save_discovered_contact
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

        email_svc = EmailService(self.db)
        send_result = await email_svc.send_agent_reply(
            org_id, msg.from_email, msg.subject or "", final_text,
            from_address=from_addr, sender_name=user_name,
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
        from src.services.customer_agent import update_thread_status

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

    async def archive_thread(self, org_id: str, thread_id: str) -> dict:
        """Archive a thread — hidden from inbox but preserved for records."""
        result = await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            raise Exception("Thread not found")
        thread.status = "archived"
        thread.has_pending = False
        await self.db.commit()
        return {"archived": True}

    async def delete_thread(self, org_id: str, thread_id: str) -> dict:
        """Permanently delete a thread and all its messages."""
        from sqlalchemy import delete, update, text

        # Get message IDs in this thread
        msg_result = await self.db.execute(
            select(AgentMessage.id).where(
                AgentMessage.thread_id == thread_id,
                AgentMessage.organization_id == org_id,
            )
        )
        msg_ids = [r[0] for r in msg_result.all()]

        if msg_ids:
            # Unlink actions referencing these messages
            await self.db.execute(
                update(AgentAction)
                .where(AgentAction.agent_message_id.in_(msg_ids))
                .values(agent_message_id=None, thread_id=None)
            )
            # Delete action comments referencing these actions' messages
            # Delete the messages
            await self.db.execute(
                delete(AgentMessage).where(AgentMessage.id.in_(msg_ids))
            )

        # Unlink any actions referencing this thread directly
        await self.db.execute(
            update(AgentAction)
            .where(AgentAction.thread_id == thread_id)
            .values(thread_id=None)
        )
        # Delete thread reads
        # Delete thread
        await self.db.execute(
            delete(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )
        await self.db.commit()
        return {"deleted": True}

    async def assign_thread(self, org_id: str, thread_id: str, user_id: str | None, user_name: str | None) -> dict:
        """Assign/unassign a thread to a team member. Creates notification on assign.

        Rejects assignment if thread requires a visibility permission the target user lacks.
        """
        result = await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        now = datetime.now(timezone.utc)
        if user_id:
            # Check target user has visibility permission for this thread
            if thread.visibility_permission:
                from src.models.organization_user import OrganizationUser
                from src.services.permission_service import PermissionService
                target_ou = (await self.db.execute(
                    select(OrganizationUser).where(
                        OrganizationUser.user_id == user_id,
                        OrganizationUser.organization_id == org_id,
                        OrganizationUser.is_active == True,
                    )
                )).scalar_one_or_none()
                if target_ou:
                    perm_svc = PermissionService(self.db)
                    target_perms = await perm_svc.resolve_permissions(target_ou)
                    if thread.visibility_permission not in target_perms:
                        return {"error": "forbidden", "detail": f"User lacks required permission: {thread.visibility_permission}"}

            thread.assigned_to_user_id = user_id
            thread.assigned_to_name = user_name
            thread.assigned_at = now

            # Create notification for the assignee
            notif = Notification(
                organization_id=org_id,
                user_id=user_id,
                type="thread_assigned",
                title=f"Thread assigned to you",
                body=f"{thread.customer_name or thread.contact_email}: {thread.subject or 'No subject'}",
                link="/inbox",
            )
            self.db.add(notif)
        else:
            thread.assigned_to_user_id = None
            thread.assigned_to_name = None
            thread.assigned_at = None

        await self.db.commit()
        return {
            "assigned_to_user_id": thread.assigned_to_user_id,
            "assigned_to_name": thread.assigned_to_name,
            "assigned_at": thread.assigned_at.isoformat() if thread.assigned_at else None,
        }

    async def mark_thread_read(self, thread_id: str, user_id: str) -> None:
        """Mark a thread as read by the current user (no-op, thread_reads removed)."""
        pass

    async def send_followup(self, org_id: str, thread_id: str, text: str, user_name: str) -> dict:
        """Send a follow-up in a thread and evaluate if open jobs should close."""
        from src.services.customer_agent import update_thread_status
        from src.services.email_service import EmailService

        thread = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        if not text:
            return {"error": "no_text", "detail": "No response text"}

        from_addr = thread.delivered_to if thread.delivered_to else None
        email_svc = EmailService(self.db)
        send_result = await email_svc.send_agent_reply(
            org_id, thread.contact_email, thread.subject or "", text,
            from_address=from_addr, sender_name=user_name,
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

                ai_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                eval_response = ai_client.messages.create(
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
                                        from src.models.notification import Notification
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

    async def revise_draft(self, org_id: str, thread_id: str, draft: str, instruction: str) -> dict:
        """Revise a draft response using Claude."""
        thread = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        prompt = f"""Revise this email draft based on the instruction below.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}

Current draft:
{draft}

Instruction: {instruction}

Rules:
- Apply the instruction to the draft
- Keep the same general structure and signature
- Never admit fault or accept blame
- Return ONLY the revised email text, nothing else"""

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model=await get_model("fast"),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"draft": response.content[0].text.strip()}
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

    async def draft_followup(self, org_id: str, thread_id: str) -> dict:
        """Draft a follow-up for a thread using full conversation context."""
        thread = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Get conversation
        msgs = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == org_id).order_by(AgentMessage.received_at)
        )).scalars().all()

        convo = ""
        for m in msgs:
            who = "Client" if m.direction == "inbound" else "Us"
            convo += f"\n[{who}]: {(m.body or m.final_response or '')[:300]}"

        # Get actions + comments
        actions_result = await self.db.execute(
            select(AgentAction).options(selectinload(AgentAction.comments)).where(AgentAction.thread_id == thread_id, AgentAction.organization_id == org_id)
        )
        actions_ctx = ""
        for a in actions_result.scalars().all():
            actions_ctx += f"\n- [{a.status}] {a.action_type}: {a.description}"
            if a.comments:
                for c in a.comments:
                    actions_ctx += f"\n  {c.author}: {c.text}"

        prompt = f"""Draft a follow-up email for a pool service company.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Jobs and comments:{actions_ctx or ' None'}

Draft a follow-up email continuing this conversation. Reference what's been discussed and any work done.

Rules:
- Professional, friendly tone
- Never admit fault
- Keep it concise — 2-4 sentences
- NEVER include the property address in the email. The client knows where they live. Use property name if it has one, otherwise skip.
- Do NOT include a signature — the system appends it automatically
- End with a brief closing like "Best," on its own line

Return ONLY the email body text (no signature)."""

        # Inject lessons from past corrections
        try:
            from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_DRAFTER
            learner = AgentLearningService(self.db)
            lessons = await learner.build_lessons_prompt(
                org_id, AGENT_EMAIL_DRAFTER,
                category=thread.category, customer_id=thread.matched_customer_id,
            )
            if lessons:
                prompt += "\n\n" + lessons
        except Exception:
            pass

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model=await get_model("fast"),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"draft": response.content[0].text.strip(), "to": thread.contact_email, "subject": thread.subject}
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

    async def update_visibility(self, org_id: str, thread_id: str, visibility_permission: str | None) -> dict:
        """Admin override: change a thread's visibility permission."""
        result = await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        thread.visibility_permission = visibility_permission
        await self.db.commit()
        return {
            "thread_id": thread.id,
            "visibility_permission": thread.visibility_permission,
        }

    async def create_job_from_thread(self, org_id: str, thread_id: str, created_by: str) -> dict:
        """AI reads conversation and creates a job with description extracted from context."""
        thread = (await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Check if job already exists for this thread
        existing = (await self.db.execute(
            select(AgentAction).where(AgentAction.thread_id == thread_id, AgentAction.organization_id == org_id)
        )).scalar_one_or_none()
        if existing:
            return {"error": "exists", "detail": "Job already exists for this thread", "action_id": existing.id}

        # Build conversation context
        msgs = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id).order_by(AgentMessage.received_at)
        )).scalars().all()

        convo = ""
        for m in msgs:
            who = "Client" if m.direction == "inbound" else "Us"
            convo += f"\n[{who}]: {(m.body or '')[:300]}"

        # AI extracts job details
        prompt = f"""Extract a job/work item from this pool service email conversation.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Respond with JSON:
{{"action_type": "repair|follow_up|bid|site_visit|callback|schedule_change|equipment|other", "description": "short one-line summary, max 60 chars — action verb + what. Do NOT include addresses."}}

Keep the description concise and actionable."""

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model=await get_model("fast"),
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
            if not json_match:
                return {"error": "ai_failed", "detail": "Failed to parse AI response"}

            data = json.loads(json_match.group())
        except Exception as e:
            # Fallback to thread subject
            data = {"action_type": "follow_up", "description": (thread.subject or "Follow up")[:60]}

        action = AgentAction(
            organization_id=org_id,
            thread_id=thread_id,
            customer_id=thread.matched_customer_id,
            customer_name=thread.customer_name,
            action_type=data.get("action_type", "follow_up"),
            description=data.get("description", thread.subject or "Follow up")[:60],
            status="open",
            job_path="customer",
            created_by=created_by,
        )
        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)

        return {"action_id": action.id, "description": action.description, "action_type": action.action_type}

    async def draft_estimate_from_thread(self, org_id: str, thread_id: str, created_by: str) -> dict:
        """AI reads conversation and drafts an estimate with line items."""
        thread = (await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Check for existing estimate linked to this thread via a job
        from src.models.invoice import Invoice
        existing = (await self.db.execute(
            select(Invoice).join(AgentAction, AgentAction.invoice_id == Invoice.id).where(
                AgentAction.thread_id == thread_id,
                Invoice.document_type == "estimate",
            )
        )).scalar_one_or_none()
        if existing:
            return {
                "invoice_id": existing.id,
                "invoice_number": existing.invoice_number,
                "subject": existing.subject,
                "total": float(existing.total or 0),
                "line_items": [],
                "existing": True,
            }

        msgs = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id).order_by(AgentMessage.received_at)
        )).scalars().all()

        convo = ""
        for m in msgs:
            who = "Client" if m.direction == "inbound" else "Us"
            convo += f"\n[{who}]: {(m.body or '')[:300]}"

        prompt = f"""You are a pool service estimator. Read this conversation and create estimate line items.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Create line items for an estimate. Include labor, parts, and materials as separate line items.
Use realistic pool service pricing.

Respond with JSON:
{{"subject": "short estimate title", "line_items": [{{"description": "what", "quantity": 1, "unit_price": 100.00}}]}}

Keep descriptions professional — no addresses, no customer names in line items."""

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model=await get_model("fast"),
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
            if not json_match:
                return {"error": "ai_failed", "detail": "Failed to parse AI response"}

            data = json.loads(json_match.group())
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

        # Create the estimate via InvoiceService
        from src.services.invoice_service import InvoiceService
        from datetime import date as date_type

        line_items = data.get("line_items", [])
        if not line_items:
            return {"error": "no_items", "detail": "AI could not extract line items from conversation"}

        inv_svc = InvoiceService(self.db)
        invoice = await inv_svc.create(
            org_id,
            customer_id=thread.matched_customer_id,
            line_items_data=[{
                "description": li.get("description", "Service"),
                "quantity": li.get("quantity", 1),
                "unit_price": li.get("unit_price", 0),
            } for li in line_items],
            document_type="estimate",
            subject=data.get("subject", thread.subject or "Service Estimate"),
            issue_date=date_type.today(),
            status="draft",
        )

        # Create or link job
        existing_job = (await self.db.execute(
            select(AgentAction).where(AgentAction.thread_id == thread_id, AgentAction.organization_id == org_id)
        )).scalar_one_or_none()

        if existing_job:
            existing_job.invoice_id = invoice.id
        else:
            job = AgentAction(
                organization_id=org_id,
                thread_id=thread_id,
                invoice_id=invoice.id,
                customer_id=thread.matched_customer_id,
                customer_name=thread.customer_name,
                action_type="bid",
                description=data.get("subject", thread.subject or "Service Estimate")[:60],
                status="open",
                job_path="customer",
                created_by=created_by,
            )
            self.db.add(job)

        await self.db.commit()

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subject": invoice.subject,
            "total": float(invoice.total or 0),
            "line_items": [{
                "description": li.get("description"),
                "quantity": li.get("quantity"),
                "unit_price": li.get("unit_price"),
            } for li in line_items],
        }
