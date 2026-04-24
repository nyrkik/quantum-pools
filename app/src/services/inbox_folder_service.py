"""InboxFolderService — folder CRUD, thread moves, system folder seeding."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.inbox_folder import InboxFolder, SYSTEM_FOLDERS
from src.models.agent_thread import AgentThread


class InboxFolderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_folders(self, org_id: str, user_id: str | None = None) -> list[dict]:
        """Return all folders with thread counts (total + per-user unread).

        Historical threads (`is_historical=True`) are excluded from every
        count — they belong on the customer detail page and the All Mail
        folder, not in folder-badge totals that would otherwise show
        thousands of pre-cutover threads in Inbox.
        """
        from src.models.thread_read import ThreadRead

        # Folders with threads assigned — unread = threads where the user hasn't
        # read the latest inbound message (per thread_reads table).
        unread_filter = and_(
            AgentThread.last_direction == "inbound",
            AgentThread.status.notin_(("closed", "ignored", "archived")),
        )
        # Partial-index-friendly exclusion — keeps historical off every count.
        not_historical = AgentThread.is_historical == False  # noqa: E712

        rows = (await self.db.execute(
            select(
                InboxFolder,
                func.count(AgentThread.id).filter(AgentThread.id.isnot(None), not_historical).label("thread_count"),
            )
            .outerjoin(AgentThread, AgentThread.folder_id == InboxFolder.id)
            .where(InboxFolder.organization_id == org_id)
            .group_by(InboxFolder.id)
            .order_by(InboxFolder.sort_order, InboxFolder.created_at)
        )).all()

        # Inbox count (NULL folder_id threads)
        inbox_thread_count = (await self.db.execute(
            select(func.count(AgentThread.id)).where(
                AgentThread.organization_id == org_id,
                AgentThread.folder_id.is_(None),
                not_historical,
            )
        )).scalar() or 0

        # Per-user unread counts per folder (requires a separate query with thread_reads join)
        folder_unread: dict[str | None, int] = {}
        if user_id:
            # Query: for each folder, count threads that are inbound, not closed/ignored,
            # and either never read or read before last_message_at
            unread_rows = (await self.db.execute(
                select(
                    AgentThread.folder_id,
                    func.count(AgentThread.id),
                )
                .select_from(
                    AgentThread.__table__.outerjoin(
                        ThreadRead.__table__,
                        and_(
                            ThreadRead.thread_id == AgentThread.id,
                            ThreadRead.user_id == user_id,
                        ),
                    )
                )
                .where(
                    AgentThread.organization_id == org_id,
                    unread_filter,
                    not_historical,
                    or_(
                        ThreadRead.read_at.is_(None),
                        AgentThread.last_message_at > ThreadRead.read_at,
                    ),
                )
                .group_by(AgentThread.folder_id)
            )).all()
            for fid, cnt in unread_rows:
                folder_unread[fid] = cnt

        # Sent is a view, not exclusive placement: count threads with any
        # outbound `sent` message regardless of folder_id. Matches the list
        # behavior in AgentThreadService.list_threads.
        from src.models.agent_message import AgentMessage
        sent_thread_count = (await self.db.execute(
            select(func.count(func.distinct(AgentMessage.thread_id)))
            .select_from(AgentMessage.__table__.join(
                AgentThread.__table__,
                AgentMessage.thread_id == AgentThread.id,
            ))
            .where(
                AgentMessage.organization_id == org_id,
                AgentMessage.direction == "outbound",
                AgentMessage.status == "sent",
                not_historical,
            )
        )).scalar() or 0

        # All Mail: failsafe count = every live thread across all folders/status/directions.
        # Mirrors the folder_key=="all_mail" branch semantics in list_threads.
        all_mail_thread_count = (await self.db.execute(
            select(func.count(AgentThread.id)).where(
                AgentThread.organization_id == org_id,
                not_historical,
            )
        )).scalar() or 0

        # Outbox: threads whose MOST RECENT outbound message is stuck
        # (queued / failed / bounced / delivery_error). Matches the
        # folder_key=="outbox" list branch in AgentThreadService.list_threads.
        # Ignores folder_id — a thread routed to any custom folder still
        # surfaces here if its latest outbound is stuck.
        latest_outbound_sq = (
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
        outbox_thread_count = (await self.db.execute(
            select(func.count(func.distinct(AgentThread.id)))
            .select_from(AgentThread.__table__.join(
                latest_outbound_sq,
                latest_outbound_sq.c.tid == AgentThread.id,
            ))
            .where(
                AgentThread.organization_id == org_id,
                not_historical,
                (
                    latest_outbound_sq.c.ds.in_(("bounced", "spam_complaint"))
                    | latest_outbound_sq.c.de.isnot(None)
                    | latest_outbound_sq.c.st.in_(("failed", "queued"))
                ),
            )
        )).scalar() or 0

        # AI Review folder: virtual count from auto_handled_at, not folder_id.
        # No thread.folder_id ever points at ai_review — the seeded folder row
        # exists only so the sidebar can render it as a system folder.
        ai_review_thread_count = (await self.db.execute(
            select(func.count(AgentThread.id)).where(
                AgentThread.organization_id == org_id,
                not_historical,
                AgentThread.auto_handled_at.isnot(None),
                AgentThread.auto_handled_feedback_at.is_(None),
            )
        )).scalar() or 0

        result = []
        for folder, thread_count in rows:
            tc = thread_count
            uc = folder_unread.get(folder.id, 0)
            # Merge NULL folder_id counts into the inbox system folder
            if folder.system_key == "inbox":
                tc += inbox_thread_count
                uc += folder_unread.get(None, 0)
            elif folder.system_key == "sent":
                tc = sent_thread_count
                uc = 0  # Sent folder isn't something users track as unread
            elif folder.system_key == "outbox":
                # Outbox count = threads with stuck outbound, not folder_id
                # assignments. Expose it as the unread count so the sidebar
                # badge surfaces the number that needs attention (same slot
                # the eye is already drawn to).
                tc = outbox_thread_count
                uc = outbox_thread_count
            elif folder.system_key == "all_mail":
                # All Mail shows every live thread — informational total, no
                # unread badge (would just mirror Inbox's count and add noise).
                tc = all_mail_thread_count
                uc = 0
            elif folder.system_key == "ai_review":
                # AI Review = unreviewed AI auto-closes. Surface the count
                # as the unread badge so the amber pill is the user's nudge
                # to review what the AI silently closed.
                tc = ai_review_thread_count
                uc = ai_review_thread_count
            result.append({
                "id": folder.id,
                "name": folder.name,
                "icon": folder.icon,
                "color": folder.color,
                "sort_order": folder.sort_order,
                "is_system": folder.is_system,
                "system_key": folder.system_key,
                "thread_count": tc,
                "unread_count": uc,
            })
        return result

    async def create_folder(self, org_id: str, name: str, icon: str | None = None, color: str | None = None) -> dict:
        """Create a custom folder."""
        # Get next sort_order
        max_order = (await self.db.execute(
            select(func.max(InboxFolder.sort_order)).where(InboxFolder.organization_id == org_id)
        )).scalar() or 0

        folder = InboxFolder(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            name=name,
            icon=icon,
            color=color,
            sort_order=max_order + 1,
            is_system=False,
        )
        self.db.add(folder)
        await self.db.commit()
        return self._to_dict(folder)

    async def update_folder(self, org_id: str, folder_id: str, **kwargs) -> dict | None:
        """Update folder properties. Cannot rename system folders."""
        folder = (await self.db.execute(
            select(InboxFolder).where(
                InboxFolder.id == folder_id,
                InboxFolder.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not folder:
            return None
        if folder.is_system and "name" in kwargs:
            del kwargs["name"]  # can't rename system folders
        for k, v in kwargs.items():
            if hasattr(folder, k) and k not in ("id", "organization_id", "is_system", "system_key"):
                setattr(folder, k, v)
        await self.db.commit()
        return self._to_dict(folder)

    async def delete_folder(self, org_id: str, folder_id: str) -> bool:
        """Delete a custom folder. Moves its threads back to Inbox (NULL). Cannot delete system folders."""
        folder = (await self.db.execute(
            select(InboxFolder).where(
                InboxFolder.id == folder_id,
                InboxFolder.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not folder or folder.is_system:
            return False
        # Move threads to Inbox
        await self.db.execute(
            AgentThread.__table__.update()
            .where(AgentThread.folder_id == folder_id)
            .values(folder_id=None)
        )
        await self.db.delete(folder)
        await self.db.commit()
        return True

    async def move_thread(self, org_id: str, thread_id: str, folder_id: str | None) -> bool:
        """Move a thread to a folder. Sets folder_override=True to prevent rule re-assignment."""
        thread = (await self.db.execute(
            select(AgentThread).where(
                AgentThread.id == thread_id,
                AgentThread.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not thread:
            return False
        # Validate target folder exists in this org (or None for Inbox)
        if folder_id:
            folder = (await self.db.execute(
                select(InboxFolder).where(
                    InboxFolder.id == folder_id,
                    InboxFolder.organization_id == org_id,
                )
            )).scalar_one_or_none()
            if not folder:
                return False
        thread.folder_id = folder_id
        thread.folder_override = True
        await self.db.commit()
        return True

    async def get_system_folder_id(self, org_id: str, system_key: str) -> str | None:
        """Get the ID of a system folder by key."""
        row = (await self.db.execute(
            select(InboxFolder.id).where(
                InboxFolder.organization_id == org_id,
                InboxFolder.system_key == system_key,
            )
        )).scalar_one_or_none()
        return row

    async def ensure_system_folders(self, org_id: str):
        """Idempotent: create system folders if they don't exist."""
        for sf in SYSTEM_FOLDERS:
            existing = (await self.db.execute(
                select(InboxFolder).where(
                    InboxFolder.organization_id == org_id,
                    InboxFolder.system_key == sf["system_key"],
                )
            )).scalar_one_or_none()
            if not existing:
                self.db.add(InboxFolder(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    is_system=True,
                    **sf,
                ))
        await self.db.commit()

    def _to_dict(self, f: InboxFolder) -> dict:
        return {
            "id": f.id,
            "name": f.name,
            "icon": f.icon,
            "color": f.color,
            "sort_order": f.sort_order,
            "is_system": f.is_system,
            "system_key": f.system_key,
        }
