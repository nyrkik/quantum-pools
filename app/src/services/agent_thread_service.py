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


def _serialize_action(a: AgentAction, include_comments: bool = False) -> dict:
    d = {
        "id": a.id,
        "agent_message_id": a.agent_message_id,
        "action_type": a.action_type,
        "description": a.description,
        "assigned_to": a.assigned_to,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "status": a.status,
        "notes": a.notes,
        "customer_name": a.customer_name,
        "property_address": a.property_address,
        "created_by": a.created_by,
        "invoice_id": a.invoice_id,
        "parent_action_id": a.parent_action_id,
        "task_count": a.task_count or 0,
        "tasks_completed": a.tasks_completed or 0,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "is_suggested": a.is_suggested if hasattr(a, "is_suggested") else False,
        "suggestion_confidence": a.suggestion_confidence if hasattr(a, "suggestion_confidence") else None,
    }
    if include_comments and hasattr(a, "comments") and a.comments:
        d["comments"] = [
            {"id": c.id, "author": c.author, "text": c.text, "created_at": c.created_at.isoformat()}
            for c in a.comments
        ]
    return d


class AgentThreadService:
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

        # Look up read status for current user
        read_map: dict[str, datetime] = {}
        if current_user_id and threads:
            from sqlalchemy import text
            read_result = await self.db.execute(
                text("SELECT thread_id, last_read_at FROM thread_reads WHERE user_id = :uid AND thread_id = ANY(:tids)"),
                {"uid": current_user_id, "tids": [t.id for t in threads]},
            )
            read_map = {row[0]: row[1] for row in read_result.all()}

        return {
            "items": [
                {
                    "id": t.id,
                    "contact_email": t.contact_email,
                    "subject": t.subject,
                    "customer_name": t.customer_name,
                    "matched_customer_id": t.matched_customer_id,
                    "status": t.status,
                    "urgency": t.urgency,
                    "category": t.category,
                    "message_count": t.message_count,
                    "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
                    "last_direction": t.last_direction,
                    "last_snippet": t.last_snippet,
                    "has_pending": t.has_pending,
                    "has_open_actions": t.has_open_actions,
                    "assigned_to_user_id": t.assigned_to_user_id,
                    "assigned_to_name": t.assigned_to_name,
                    "assigned_at": t.assigned_at.isoformat() if t.assigned_at else None,
                    "is_unread": (
                        t.last_message_at > read_map[t.id] if t.id in read_map and t.last_message_at
                        else t.last_message_at is not None  # Never read = unread
                    ),
                    "visibility_permission": t.visibility_permission,
                    "delivered_to": t.delivered_to,
                }
                for t in threads
            ],
            "total": total,
        }

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
        actions = [_serialize_action(a, include_comments=True) for a in actions_result.scalars().all()]

        return {
            "id": thread.id,
            "contact_email": thread.contact_email,
            "subject": thread.subject,
            "customer_name": thread.customer_name,
            "matched_customer_id": thread.matched_customer_id,
            "property_address": thread.property_address,
            "status": thread.status,
            "urgency": thread.urgency,
            "category": thread.category,
            "message_count": thread.message_count,
            "has_pending": thread.has_pending,
            "has_open_actions": thread.has_open_actions,
            "assigned_to_user_id": thread.assigned_to_user_id,
            "assigned_to_name": thread.assigned_to_name,
            "assigned_at": thread.assigned_at.isoformat() if thread.assigned_at else None,
            "visibility_permission": thread.visibility_permission,
            "delivered_to": thread.delivered_to,
            "routing_rule_id": thread.routing_rule_id,
            "timeline": timeline,
            "actions": actions,
        }

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
        send_result = await email_svc.send_agent_reply(org_id, msg.from_email, msg.subject or "", final_text, from_address=from_addr)
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
        for msg in result.scalars().all():
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
        await self.db.execute(text("DELETE FROM thread_reads WHERE thread_id = :tid"), {"tid": thread_id})
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
        """Mark a thread as read by the current user."""
        from sqlalchemy import text
        await self.db.execute(
            text("""
                INSERT INTO thread_reads (user_id, thread_id, last_read_at)
                VALUES (:uid, :tid, now())
                ON CONFLICT (user_id, thread_id) DO UPDATE SET last_read_at = now()
            """),
            {"uid": user_id, "tid": thread_id},
        )
        await self.db.commit()

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
        send_result = await email_svc.send_agent_reply(org_id, thread.contact_email, thread.subject or "", text, from_address=from_addr)
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
- End with: Best,\\nThe {AGENT_FROM_NAME} Team\\n{AGENT_FROM_EMAIL}

Return ONLY the email body text."""

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
