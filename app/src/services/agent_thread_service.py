"""Service layer for agent thread (conversation) queries and management.

Thread CRUD, search, stats, assignment, visibility, read tracking.
Email-sending operations: see thread_action_service.py
AI-powered drafting/extraction: see thread_ai_service.py
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.agent_action import AgentAction
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.message_attachment import MessageAttachment
from src.models.notification import Notification
from src.models.property import Property
from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature

logger = logging.getLogger(__name__)

AGENT_FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")

from src.presenters.action_presenter import ActionPresenter
from src.presenters.thread_presenter import ThreadPresenter


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
                "customer_id": cust.id,
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
        folder_id: str | None = None,
        folder_key: str | None = None,
    ) -> dict:
        """List conversation threads with filtering."""
        base = select(AgentThread).where(AgentThread.organization_id == org_id)

        # "All Mail" folder: show literally every thread — no folder, status, or
        # category filtering. Use this when the user thinks an email is missing.
        if folder_key == "all":
            # Skip every other filter except visibility + search + assigned_to.
            if assigned_to:
                base = base.where(AgentThread.assigned_to_user_id == assigned_to)
            if customer_id:
                base = base.where(AgentThread.matched_customer_id == customer_id)
            if user_permission_slugs is not None:
                base = base.where(
                    or_(
                        AgentThread.visibility_permission.is_(None),
                        AgentThread.visibility_permission.in_(user_permission_slugs),
                    )
                )
            if search:
                q = f"%{search}%"
                body_match = select(AgentMessage.thread_id).where(AgentMessage.body.ilike(q))
                base = base.where(
                    AgentThread.contact_email.ilike(q)
                    | AgentThread.subject.ilike(q)
                    | AgentThread.customer_name.ilike(q)
                    | AgentThread.property_address.ilike(q)
                    | AgentThread.last_snippet.ilike(q)
                    | AgentThread.id.in_(body_match)
                )
            total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
            result = await self.db.execute(
                base.order_by(desc(AgentThread.last_message_at)).offset(offset).limit(limit)
            )
            threads = result.scalars().all()

            read_map = {}
            if current_user_id and threads:
                from src.models.thread_read import ThreadRead
                thread_ids = [t.id for t in threads]
                reads = (await self.db.execute(
                    select(ThreadRead.thread_id, ThreadRead.read_at).where(
                        ThreadRead.user_id == current_user_id,
                        ThreadRead.thread_id.in_(thread_ids),
                    )
                )).all()
                read_map = {r.thread_id: r.read_at for r in reads}

            presenter = ThreadPresenter(self.db)
            items = await presenter.many(threads, read_map=read_map if current_user_id else None)
            return {"items": items, "total": total}

        # Non-inbox folders (sent, spam, custom) show ALL threads in
        # that folder without status/direction filtering — the folder IS the filter.
        is_non_inbox_folder = (folder_key and folder_key != "inbox") or (folder_id and not folder_key)

        if not is_non_inbox_folder:
            if status in ("stale", "pending"):
                base = base.where(AgentThread.has_pending == True)
            elif status == "auto_sent":
                base = base.where(
                    AgentThread.id.in_(
                        select(AgentMessage.thread_id).where(AgentMessage.status == "auto_sent")
                    )
                )
            elif status == "auto_handled":
                # AI hid the email without sending a reply. Most-recent first.
                base = base.where(
                    AgentThread.last_direction == "inbound",
                    AgentThread.status.in_(("ignored", "handled")),
                    AgentThread.has_pending == False,  # noqa: E712
                    AgentThread.id.notin_(
                        select(AgentMessage.thread_id).where(AgentMessage.status == "auto_sent")
                    ),
                )
            elif status == "failed":
                # A thread is "failed" only if its MOST RECENT outbound attempt
                # is in a failure state. If the user retried and a later send
                # succeeded, the thread is resolved and should NOT appear here.
                # (Counting any-failed-ever made this filter useless — a 4-fail
                # 4-success retry storm showed the same as 4 actual losses.)
                latest_outbound = (
                    select(
                        AgentMessage.thread_id.label("tid"),
                        AgentMessage.status.label("st"),
                        AgentMessage.delivery_status.label("ds"),
                        AgentMessage.delivery_error.label("de"),
                    )
                    .where(AgentMessage.direction == "outbound")
                    .order_by(AgentMessage.thread_id, AgentMessage.received_at.desc())
                    .distinct(AgentMessage.thread_id)
                    .subquery()
                )
                base = base.where(
                    AgentThread.id.in_(
                        select(latest_outbound.c.tid).where(
                            latest_outbound.c.ds.in_(("bounced", "spam_complaint"))
                            | latest_outbound.c.de.isnot(None)
                            | latest_outbound.c.st.in_(("failed", "queued"))
                        )
                    )
                )
            elif status == "handled":
                base = base.where(AgentThread.status == "handled")
            elif status == "ignored":
                base = base.where(AgentThread.status == "ignored")
            elif status == "archived":
                base = base.where(AgentThread.status == "archived")
            else:
                # Default inbox: exclude archived and outbound-only threads
                base = base.where(
                    AgentThread.status != "archived",
                    or_(AgentThread.last_direction == "inbound", AgentThread.has_pending == True),
                )
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
            base = base.where(
                or_(
                    AgentThread.visibility_permission.is_(None),
                    AgentThread.visibility_permission.in_(user_permission_slugs),
                )
            )
        # Folder filtering (skip when showing stale, auto_sent, auto_handled, or failed — those search all folders)
        if status in ("stale", "auto_sent", "auto_handled", "failed"):
            pass  # No folder filter for global searches
        elif folder_key == "inbox" or (not folder_id and not folder_key):
            # Inbox = NULL folder_id OR explicitly assigned to inbox system folder
            from src.models.inbox_folder import InboxFolder
            inbox_folder = (await self.db.execute(
                select(InboxFolder.id).where(
                    InboxFolder.organization_id == org_id,
                    InboxFolder.system_key == "inbox",
                )
            )).scalar_one_or_none()
            if inbox_folder:
                base = base.where(or_(AgentThread.folder_id.is_(None), AgentThread.folder_id == inbox_folder))
            else:
                base = base.where(AgentThread.folder_id.is_(None))
        elif folder_key == "sent":
            # Sent is a VIEW, not exclusive placement: any thread with at least
            # one outbound `sent` message, regardless of the thread's folder_id.
            # A thread routed to Clients/Billing/etc. still surfaces here after
            # we reply — matches the Gmail mental model.
            base = base.where(
                AgentThread.id.in_(
                    select(AgentMessage.thread_id).where(
                        AgentMessage.organization_id == org_id,
                        AgentMessage.direction == "outbound",
                        AgentMessage.status == "sent",
                    )
                )
            )
        elif folder_key:
            from src.models.inbox_folder import InboxFolder
            target = (await self.db.execute(
                select(InboxFolder.id).where(
                    InboxFolder.organization_id == org_id,
                    InboxFolder.system_key == folder_key,
                )
            )).scalar_one_or_none()
            if target:
                base = base.where(AgentThread.folder_id == target)
        elif folder_id:
            base = base.where(AgentThread.folder_id == folder_id)

        if search:
            q = f"%{search}%"
            # Subquery: thread_ids with any message body matching
            body_match = select(AgentMessage.thread_id).where(AgentMessage.body.ilike(q))
            base = base.where(
                AgentThread.contact_email.ilike(q)
                | AgentThread.subject.ilike(q)
                | AgentThread.customer_name.ilike(q)
                | AgentThread.property_address.ilike(q)
                | AgentThread.last_snippet.ilike(q)
                | AgentThread.id.in_(body_match)
            )
        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
        result = await self.db.execute(
            base.order_by(
                desc(AgentThread.has_pending),
                desc(AgentThread.last_message_at),
            ).offset(offset).limit(limit)
        )
        threads = result.scalars().all()

        # Load per-user read state
        read_map = {}
        if current_user_id and threads:
            from src.models.thread_read import ThreadRead
            thread_ids = [t.id for t in threads]
            reads = (await self.db.execute(
                select(ThreadRead.thread_id, ThreadRead.read_at).where(
                    ThreadRead.user_id == current_user_id,
                    ThreadRead.thread_id.in_(thread_ids),
                )
            )).all()
            read_map = {r.thread_id: r.read_at for r in reads}

        presenter = ThreadPresenter(self.db)
        items = await presenter.many(threads, read_map=read_map if current_user_id else None)

        return {"items": items, "total": total}

    async def get_thread_stats(self, org_id: str, user_id: str | None = None, user_permission_slugs: set[str] | None = None, can_manage_inbox: bool = False) -> dict:
        """Thread-level stats. If user_permission_slugs provided, counts only visible threads.

        Ops counts (failed, auto_handled_today, stale_pending) are
        zeroed out for users without inbox.manage — they're a billing/ops concern,
        not a manager-level dashboard. Defense-in-depth alongside the frontend
        chip-rendering gate; if either layer is misconfigured the count never
        leaks to managers/techs.
        """
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

        # Per-user unread: threads with last_message_at > user's read_at (or never read)
        # Scoped to Inbox folder only (NULL folder_id or inbox system folder) — don't count
        # unread in Sent/Automated/Spam since users don't actively monitor those.
        unread = 0
        if user_id:
            from src.models.thread_read import ThreadRead
            from src.models.inbox_folder import InboxFolder

            inbox_folder_id = (await self.db.execute(
                select(InboxFolder.id).where(
                    InboxFolder.organization_id == org_id,
                    InboxFolder.system_key == "inbox",
                )
            )).scalar_one_or_none()

            # Rule-driven auto_read_at silences threads a mark_as_read rule
            # already handled. A thread is unread only if last_message_at
            # exceeds BOTH the user's own read timestamp AND the rule stamp.
            unread_q = (
                select(func.count(AgentThread.id))
                .select_from(
                    AgentThread.__table__.outerjoin(
                        ThreadRead.__table__,
                        (ThreadRead.thread_id == AgentThread.id) & (ThreadRead.user_id == user_id),
                    )
                )
                .where(
                    thread_org,
                    AgentThread.status.notin_(("closed", "ignored")),
                    AgentThread.last_direction == "inbound",
                    or_(
                        ThreadRead.read_at.is_(None),
                        AgentThread.last_message_at > ThreadRead.read_at,
                    ),
                    or_(
                        AgentThread.auto_read_at.is_(None),
                        AgentThread.last_message_at > AgentThread.auto_read_at,
                    ),
                    # Inbox folder only
                    or_(
                        AgentThread.folder_id.is_(None),
                        AgentThread.folder_id == inbox_folder_id,
                    ) if inbox_folder_id else AgentThread.folder_id.is_(None),
                )
            )
            unread_q = _vis_filter(unread_q)
            unread = (await self.db.execute(unread_q)).scalar() or 0

        # Auto-handled today (status=ignored or status=handled with no human action)
        # Surfaces email the AI hid from the inbox so the user knows what's not visible.
        # Excludes threads that any admin/owner has already opened (reviewed).
        today_start = datetime.now(timezone.utc) - timedelta(hours=24)
        from src.models.thread_read import ThreadRead
        from src.models.organization_user import OrganizationUser
        admin_user_ids_subq = (
            select(OrganizationUser.user_id)
            .where(
                OrganizationUser.organization_id == org_id,
                OrganizationUser.role.in_(("owner", "admin")),
            )
        )
        reviewed_thread_ids_subq = (
            select(ThreadRead.thread_id)
            .where(ThreadRead.user_id.in_(admin_user_ids_subq))
        )
        auto_handled_today = (await self.db.execute(
            _vis_filter(
                select(func.count(AgentThread.id))
                .where(
                    thread_org,
                    AgentThread.last_message_at >= today_start,
                    AgentThread.last_direction == "inbound",
                    AgentThread.status.in_(("ignored", "handled")),
                    AgentThread.has_pending == False,  # noqa: E712
                    AgentThread.id.notin_(reviewed_thread_ids_subq),
                )
            )
        )).scalar() or 0

        # Failed sends — count threads where the LATEST outbound attempt failed.
        # See the failed-filter branch above for the rationale: a thread with a
        # later successful retry is not failed, even if earlier attempts crashed.
        latest_outbound = (
            select(
                AgentMessage.thread_id.label("tid"),
                AgentMessage.status.label("st"),
                AgentMessage.delivery_status.label("ds"),
                AgentMessage.delivery_error.label("de"),
            )
            .where(AgentMessage.direction == "outbound")
            .order_by(AgentMessage.thread_id, AgentMessage.received_at.desc())
            .distinct(AgentMessage.thread_id)
            .subquery()
        )
        failed = (await self.db.execute(
            _vis_filter(
                select(func.count(func.distinct(AgentThread.id)))
                .select_from(AgentThread.__table__.join(
                    latest_outbound,
                    latest_outbound.c.tid == AgentThread.id,
                ))
                .where(
                    thread_org,
                    (
                        latest_outbound.c.ds.in_(("bounced", "spam_complaint"))
                        | latest_outbound.c.de.isnot(None)
                        | latest_outbound.c.st.in_(("failed", "queued"))
                    ),
                )
            )
        )).scalar() or 0

        return {
            "total": total,
            "pending": pending,
            "open_actions": open_actions,
            "unread": unread,
            # Ops counts: only exposed to inbox-managers (owner/admin). Lower
            # roles see 0 even if data exists, so the chips never render.
            "stale_pending": stale if can_manage_inbox else 0,
            "failed": failed if can_manage_inbox else 0,
            "auto_handled_today": auto_handled_today if can_manage_inbox else 0,
        }

    async def get_thread_detail(self, org_id: str, thread_id: str, user_permission_slugs: set[str] | None = None, user_id: str | None = None) -> dict | None:
        """Get thread with full conversation timeline.

        Returns None if thread doesn't exist or user lacks required visibility permission.
        """
        result = await self.db.execute(
            select(AgentThread)
            .options(selectinload(AgentThread.case))
            .where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )
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

        # Load attachments for all messages in one query
        msg_ids = [m.id for m in messages]
        atts_by_msg: dict[str, list] = {}
        if msg_ids:
            att_result = await self.db.execute(
                select(MessageAttachment).where(
                    MessageAttachment.source_type == "agent_message",
                    MessageAttachment.source_id.in_(msg_ids),
                )
            )
            for a in att_result.scalars().all():
                atts_by_msg.setdefault(a.source_id, []).append({
                    "id": a.id,
                    "filename": a.filename,
                    "url": f"/api/v1/attachments/{a.id}/file",
                    "mime_type": a.mime_type,
                    "file_size": a.file_size,
                })

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
                "body_html": m.body_html,
                "delivery_status": m.delivery_status,
                "delivery_error": m.delivery_error,
                "first_opened_at": m.first_opened_at.isoformat() if m.first_opened_at else None,
                "open_count": m.open_count,
                "category": m.category,
                "urgency": m.urgency,
                "status": m.status,
                "draft_response": m.draft_response if m.status == "pending" else None,
                "received_at": m.received_at.isoformat() if m.received_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "approved_by": m.approved_by,
                "attachments": atts_by_msg.get(m.id, []),
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
                        "status": m.status,  # preserves "auto_sent" flag so UI can style differently
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
        d = await presenter.one(thread, user_id=user_id)
        d["timeline"] = timeline
        d["actions"] = actions
        return d

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
                title="Thread assigned to you",
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

    async def mark_thread_read(self, thread_id: str, user_id: str, org_id: str | None = None, user_role: str | None = None) -> None:
        """Mark a thread as read.

        If the reader is an admin/owner OR the assigned user, broadcast the read
        to all org users so the thread clears from everyone's unread list.
        Otherwise only mark read for the current user.
        """
        from src.models.thread_read import ThreadRead

        broadcast = False
        if user_role in ("owner", "admin"):
            broadcast = True
        elif org_id:
            # Check if user is the assignee — must scope by org so a caller
            # can't probe foreign threads via this code path.
            # (docs/inbox-security-audit-2026-04-13.md M3.)
            thread = (await self.db.execute(
                select(AgentThread).where(
                    AgentThread.id == thread_id,
                    AgentThread.organization_id == org_id,
                )
            )).scalar_one_or_none()
            if thread and thread.assigned_to_user_id == user_id:
                broadcast = True

        now = datetime.now(timezone.utc)

        if broadcast and org_id:
            # Mark read for all users in the org
            from src.models.organization_user import OrganizationUser
            org_users = (await self.db.execute(
                select(OrganizationUser.user_id).where(OrganizationUser.organization_id == org_id)
            )).scalars().all()

            for uid in org_users:
                existing = (await self.db.execute(
                    select(ThreadRead).where(ThreadRead.user_id == uid, ThreadRead.thread_id == thread_id)
                )).scalar_one_or_none()
                if existing:
                    existing.read_at = now
                else:
                    self.db.add(ThreadRead(user_id=uid, thread_id=thread_id))
        else:
            # Single-user read
            existing = (await self.db.execute(
                select(ThreadRead).where(ThreadRead.user_id == user_id, ThreadRead.thread_id == thread_id)
            )).scalar_one_or_none()
            if existing:
                existing.read_at = now
            else:
                self.db.add(ThreadRead(user_id=user_id, thread_id=thread_id))

        await self.db.flush()

        # Sync to Gmail (non-blocking)
        try:
            thread_obj = thread if 'thread' in dir() else (await self.db.execute(
                select(AgentThread).where(AgentThread.id == thread_id)
            )).scalar_one_or_none()
            if thread_obj and thread_obj.gmail_thread_id and org_id:
                from src.models.email_integration import EmailIntegration, IntegrationStatus
                integration = (await self.db.execute(
                    select(EmailIntegration).where(
                        EmailIntegration.organization_id == org_id,
                        EmailIntegration.type == "gmail_api",
                        EmailIntegration.status == IntegrationStatus.connected.value,
                        EmailIntegration.is_primary == True,  # noqa: E712
                    )
                )).scalar_one_or_none()
                if integration:
                    from src.services.gmail.read_sync import sync_read_state
                    import asyncio
                    asyncio.create_task(sync_read_state(integration, thread_obj.gmail_thread_id, mark_read=True))
        except Exception:
            pass  # Non-blocking

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
