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
        """Return all folders with thread counts (total + per-user unread)."""
        from src.models.thread_read import ThreadRead

        # Folders with threads assigned — unread = threads where the user hasn't
        # read the latest inbound message (per thread_reads table).
        unread_filter = and_(
            AgentThread.last_direction == "inbound",
            AgentThread.status.notin_(("closed", "ignored")),
        )

        rows = (await self.db.execute(
            select(
                InboxFolder,
                func.count(AgentThread.id).filter(AgentThread.id.isnot(None)).label("thread_count"),
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
                    or_(
                        ThreadRead.read_at.is_(None),
                        AgentThread.last_message_at > ThreadRead.read_at,
                    ),
                )
                .group_by(AgentThread.folder_id)
            )).all()
            for fid, cnt in unread_rows:
                folder_unread[fid] = cnt

        result = []
        for folder, thread_count in rows:
            tc = thread_count
            uc = folder_unread.get(folder.id, 0)
            # Merge NULL folder_id counts into the inbox system folder
            if folder.system_key == "inbox":
                tc += inbox_thread_count
                uc += folder_unread.get(None, 0)
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
