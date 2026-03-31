"""Command executor agent — handles actionable commands from job comments.

Single responsibility: execute commands identified by the classifier.
Each sub_intent has its own handler method.
"""

import json
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_action_task import AgentActionTask
from src.models.agent_message import AgentMessage
from src.models.customer import Customer
from src.models.notification import Notification
from src.models.user import User
from src.models.organization_user import OrganizationUser

from .observability import log_agent_call

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


class CommandExecutor:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._ctx: dict = {}

    async def execute(self, org_id, action, intent, user_id, user_name, customer_context, customer_id, find_org_user_fn) -> dict | None:
        """Route to the appropriate handler based on sub_intent."""
        self._ctx = dict(org_id=org_id, action=action, details=intent.get("details", ""),
                         user_id=user_id, user_name=user_name, customer_context=customer_context,
                         customer_id=customer_id, find_org_user_fn=find_org_user_fn)

        handlers = {
            "draft_email": self._draft_email, "send_email": self._draft_email,
            "create_estimate": self._create_estimate, "assign": self._assign,
            "update_status": self._update_status, "mark_done": self._mark_done,
            "schedule": self._schedule, "notify": self._notify,
        }
        handler = handlers.get(intent.get("sub_intent", ""))
        if not handler:
            return None
        try:
            return await handler()
        except Exception as e:
            logger.error(f"Command executor failed ({intent.get('sub_intent')}): {e}")
            await log_agent_call(organization_id=org_id, agent_name="command_executor",
                                 action=f"execute_{intent.get('sub_intent')}", success=False, error=str(e))
            return None

    async def _post(self, text: str) -> dict:
        """Post a DeepBlue comment and return the auto_comment dict."""
        c = self._ctx
        reply = AgentActionComment(organization_id=c["org_id"], action_id=c["action"].id, author="DeepBlue", text=text)
        self.db.add(reply)
        await self.db.commit()
        return {"author": "DeepBlue", "text": text}

    async def _resolve_name(self, text: str) -> str | None:
        """Match text against team members, return full name or None."""
        if not text.strip():
            return None
        result = await self.db.execute(
            select(User.first_name, User.last_name)
            .join(OrganizationUser, OrganizationUser.user_id == User.id)
            .where(OrganizationUser.organization_id == self._ctx["org_id"])
        )
        text_lower = text.lower().strip()
        for first, last in result.all():
            if first and first.lower() in text_lower:
                return f"{first} {last}" if last else first
            if last and last.lower() in text_lower:
                return f"{first} {last}" if first else last
        cleaned = text.strip().title()
        return cleaned if len(cleaned) < 50 else None

    async def _draft_email(self) -> dict | None:
        c = self._ctx
        action = c["action"]
        from src.services.email_compose_service import EmailComposeService
        svc = EmailComposeService(self.db)

        # Find customer email and thread subject
        to_email = ""
        thread_subject = ""
        if action.agent_message_id:
            orig_msg = (await self.db.execute(
                select(AgentMessage).where(AgentMessage.id == action.agent_message_id)
            )).scalar_one_or_none()
            if orig_msg:
                to_email = orig_msg.from_email or ""
        if action.thread_id:
            from src.models.agent_thread import AgentThread
            thread = (await self.db.execute(
                select(AgentThread).where(AgentThread.id == action.thread_id)
            )).scalar_one_or_none()
            if thread:
                thread_subject = thread.subject or ""
        if not to_email and c.get("customer_id"):
            cust = (await self.db.execute(
                select(Customer).where(Customer.id == c["customer_id"])
            )).scalar_one_or_none()
            if cust:
                to_email = cust.email or ""

        # Build rich context: thread conversation + job details + customer info
        thread_context = ""
        if action.agent_message_id:
            # select, desc imported at module level
            # Get the thread messages for conversation context
            if action.thread_id:
                msgs = await self.db.execute(
                    select(AgentMessage)
                    .where(AgentMessage.thread_id == action.thread_id)
                    .order_by(desc(AgentMessage.received_at))
                    .limit(5)
                )
                for m in msgs.scalars().all():
                    direction = "Customer" if m.direction == "inbound" else "Us"
                    body_preview = (m.body or "")[:300]
                    thread_context += f"\n[{direction}] {m.subject or ''}: {body_preview}\n"

        # Get all comments on this job for context
        comments_context = ""
        comments = await self.db.execute(
            select(AgentActionComment)
            .where(AgentActionComment.action_id == action.id)
            .order_by(AgentActionComment.created_at)
        )
        for cm in comments.scalars().all():
            comments_context += f"\n{cm.author}: {cm.text}"

        # Job status context for accurate drafting
        job_status_ctx = f"\nJob status: {action.status}"
        if action.job_path == "customer":
            job_status_ctx += f" (customer-facing job, path: {action.job_path})"
        from src.services.job_invoice_service import get_invoices_for_job
        linked_invoices = await get_invoices_for_job(self.db, action.id)
        if linked_invoices:
            job_status_ctx += " — has linked estimate/invoice"
        else:
            job_status_ctx += " — NO estimate sent yet"
        if action.status in ("open", "in_progress"):
            job_status_ctx += " — work NOT yet scheduled or approved by customer"
        elif action.status == "pending_approval":
            job_status_ctx += " — estimate sent, waiting for customer approval"
        elif action.status == "approved":
            job_status_ctx += " — customer approved, ready to schedule"

        instruction = (
            f"Job: {action.description}\n"
            f"Request: {c['details'] or 'Draft email to customer about this job'}\n"
            f"{job_status_ctx}\n"
            f"\nEmail thread (DO NOT repeat information already communicated):{thread_context or ' (no prior emails)'}\n"
            f"\nJob comments (latest status/plans):{comments_context or ' (none)'}\n"
            f"\nCustomer info: {(c['customer_context'] or '')[:500]}\n"
            f"\nIMPORTANT: Be concise and ACCURATE about job status. "
            f"Start with 'Hi,' or 'Hello,' — do NOT use customer name or property name in greeting. "
            f"Do NOT say work is scheduled unless the job is approved and assigned. "
            f"If no estimate has been sent, say you'll follow up with an estimate/plan. "
            f"Only cover what's NEW since the last email. 3-5 sentences max."
        )
        draft = await svc.generate_draft(org_id=c["org_id"], instruction=instruction, customer_id=c["customer_id"])
        if draft.get("error"):
            return await self._post(f"Could not generate email draft: {draft['error']}")
        body = draft.get("body", "")
        # Use thread subject as reply, not AI-generated subject
        if thread_subject:
            subject = f"Re: {thread_subject}" if not thread_subject.startswith("Re:") else thread_subject
        else:
            subject = draft.get("subject", "")
        # Post as structured draft comment (frontend detects [DRAFT_EMAIL] prefix)
        text = f"[DRAFT_EMAIL]\nTo: {to_email}\nSubject: {subject}\n---\n{body}"
        await log_agent_call(organization_id=c["org_id"], agent_name="command_executor",
                             action="execute_draft_email", input_summary=f"Job: {c['action'].description[:80]}",
                             output_summary=f"Draft generated, {len(text)} chars", success=True)
        return await self._post(text)

    async def _create_estimate(self) -> dict | None:
        c = self._ctx
        from src.services.agent_action_service import AgentActionService
        draft = await AgentActionService(self.db).draft_invoice(c["org_id"], c["action"].id)
        if not draft:
            return None
        lines = [f"  - {i['description']} (x{i.get('quantity',1)}) ${i.get('unit_price',0):.2f}"
                 for i in draft.get("line_items", [])]
        text = (f"Estimate draft for {draft.get('customer_name', 'customer')}:\n"
                f"Subject: {draft.get('subject', '')}\n\nLine items:\n"
                f"{chr(10).join(lines) or '  No line items generated'}\n\n"
                f"{draft.get('notes', '')}\n\nFinalize at /invoices/new?job={c['action'].id}")
        await log_agent_call(organization_id=c["org_id"], agent_name="command_executor",
                             action="execute_create_estimate", output_summary=f"{len(lines)} line items", success=True)
        return await self._post(text)

    async def _assign(self) -> dict | None:
        c = self._ctx
        name = await self._resolve_name(c["details"] or "")
        if not name:
            return None
        c["action"].assigned_to = name
        target = await c["find_org_user_fn"](c["org_id"], name.split()[0], exclude_user_id=c["user_id"])
        if target:
            self.db.add(Notification(organization_id=c["org_id"], user_id=target.user_id,
                                     type="job_assigned", title=f"Job assigned to you: {c['action'].description[:50]}",
                                     body=f"Assigned by {c['user_name']}", link=f"/jobs?action={c['action'].id}"))
        return await self._post(f"Job reassigned to {name}.")

    async def _update_status(self) -> dict | None:
        c = self._ctx
        mapping = {"open": "open", "reopen": "open", "re-open": "open", "in_progress": "in_progress",
                   "in progress": "in_progress", "started": "in_progress", "done": "done",
                   "complete": "done", "completed": "done", "closed": "done",
                   "cancelled": "cancelled", "canceled": "cancelled"}
        new = mapping.get((c["details"] or "").lower().strip())
        if not new:
            return None
        c["action"].status = new
        c["action"].completed_at = datetime.now(timezone.utc) if new == "done" else None
        return await self._post(f"Job status updated to {new}.")

    async def _mark_done(self) -> dict | None:
        c = self._ctx
        c["action"].status = "done"
        c["action"].completed_at = datetime.now(timezone.utc)
        # Update task counts
        aid = c["action"].id
        total = (await self.db.execute(select(func.count(AgentActionTask.id)).where(
            AgentActionTask.action_id == aid, AgentActionTask.status != "cancelled"))).scalar() or 0
        done = (await self.db.execute(select(func.count(AgentActionTask.id)).where(
            AgentActionTask.action_id == aid, AgentActionTask.status == "done"))).scalar() or 0
        c["action"].task_count = total
        c["action"].tasks_completed = done
        result = await self._post("Job marked as done.")
        result["action_resolved"] = True
        return result

    async def _schedule(self) -> dict | None:
        return await self._post(f"Scheduled: {self._ctx['details'] or 'time TBD'}. (Calendar integration coming soon.)")

    async def _notify(self) -> dict | None:
        c = self._ctx
        name = await self._resolve_name(c["details"] or "")
        if not name:
            return await self._post(f"Could not identify who to notify from: {c['details']}")
        target = await c["find_org_user_fn"](c["org_id"], name.split()[0], exclude_user_id=c["user_id"])
        if target:
            self.db.add(Notification(organization_id=c["org_id"], user_id=target.user_id,
                                     type="job_update", title=f"Update on: {c['action'].description[:50]}",
                                     body=f"{c['user_name']} requested you be notified",
                                     link=f"/jobs?action={c['action'].id}"))
            return await self._post(f"Notification sent to {name}.")
        return await self._post(f"Could not find team member: {name}")
