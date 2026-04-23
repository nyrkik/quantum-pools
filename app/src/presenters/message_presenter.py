"""MessagePresenter — internal thread/message serialization."""

from sqlalchemy import select, func
from src.presenters.base import Presenter
from src.models.internal_message import InternalThread, InternalMessage
from src.models.message_attachment import MessageAttachment
from src.models.user import User


class MessagePresenter(Presenter):

    async def many_threads(self, threads: list[InternalThread], user_id: str) -> list[dict]:
        # Batch load user names
        all_user_ids = set()
        for t in threads:
            all_user_ids.update(t.participant_ids or [])
            if t.last_message_by:
                all_user_ids.add(t.last_message_by)
        user_names = await self._load_user_names(all_user_ids)
        customers = await self._load_customers({t.customer_id for t in threads if t.customer_id})

        # Batch load read states
        from src.models.thread_read import ThreadRead
        thread_ids = [t.id for t in threads]
        read_map: dict[str, "datetime"] = {}
        if thread_ids:
            reads = (await self.db.execute(
                select(ThreadRead.thread_id, ThreadRead.read_at).where(
                    ThreadRead.user_id == user_id,
                    ThreadRead.thread_id.in_(thread_ids),
                )
            )).all()
            read_map = {r.thread_id: r.read_at for r in reads}

        results = []
        for t in threads:
            # Get last message preview
            last_msg = (await self.db.execute(
                select(InternalMessage).where(InternalMessage.thread_id == t.id)
                .order_by(InternalMessage.created_at.desc()).limit(1)
            )).scalar_one_or_none()

            other_ids = [uid for uid in (t.participant_ids or []) if uid != user_id]
            other_names = [user_names.get(uid, "Unknown") for uid in other_ids]
            cust = customers.get(t.customer_id) if t.customer_id else None

            # Unread: last message not from me AND (never read OR read before last message)
            if t.last_message_by == user_id:
                is_unread = False
            elif t.id in read_map:
                is_unread = t.last_message_at > read_map[t.id] if t.last_message_at else False
            else:
                is_unread = t.last_message_by is not None

            results.append({
                "id": t.id,
                "participants": other_names,
                "participant_ids": t.participant_ids,
                "subject": t.subject,
                "customer_name": cust.display_name if cust else None,
                "customer_id": t.customer_id,
                "action_id": t.action_id,
                "priority": t.priority,
                "is_unread": is_unread,
                "message_count": t.message_count,
                "last_message": last_msg.text[:100] if last_msg else None,
                "last_message_by": user_names.get(t.last_message_by, "") if t.last_message_by else None,
                "last_message_at": self._iso(t.last_message_at),
                "converted_to_action_id": t.converted_to_action_id,
                "case_id": t.case_id if hasattr(t, "case_id") else None,
                "created_at": self._iso(t.created_at),
            })
        return results

    async def thread_detail(self, thread: InternalThread, user_id: str) -> dict:
        # Load messages
        msgs_result = await self.db.execute(
            select(InternalMessage).where(InternalMessage.thread_id == thread.id)
            .order_by(InternalMessage.created_at)
        )
        messages = msgs_result.scalars().all()

        # Load user names
        user_ids = {m.from_user_id for m in messages if m.from_user_id}
        user_ids.update(thread.participant_ids or [])
        user_names = await self._load_user_names(user_ids)
        customers = await self._load_customers({thread.customer_id} if thread.customer_id else set())
        cust = customers.get(thread.customer_id) if thread.customer_id else None

        # Load attachments for all messages in one query
        msg_ids = [m.id for m in messages]
        attachments_by_msg = await self._load_attachments("internal_message", msg_ids)

        # Load reactions grouped by (message_id, emoji) so the frontend can
        # render chips with counts + user names without a per-message fetch.
        reactions_by_msg = await self._load_reactions(msg_ids)

        # Load case summary for the link picker
        case_number = None
        case_title = None
        if getattr(thread, "case_id", None):
            from src.models.service_case import ServiceCase
            case = (await self.db.execute(
                select(ServiceCase.case_number, ServiceCase.title).where(ServiceCase.id == thread.case_id)
            )).one_or_none()
            if case:
                case_number, case_title = case

        return {
            "id": thread.id,
            "participant_ids": thread.participant_ids,
            "participants": [user_names.get(uid, "Unknown") for uid in (thread.participant_ids or [])],
            "subject": thread.subject,
            "customer_name": cust.display_name if cust else None,
            "customer_id": thread.customer_id,
            "action_id": thread.action_id,
            "priority": thread.priority,
            "converted_to_action_id": thread.converted_to_action_id,
            "case_id": thread.case_id if hasattr(thread, "case_id") else None,
            "case_number": case_number,
            "case_title": case_title,
            "created_at": self._iso(thread.created_at),
            "messages": [
                {
                    "id": m.id,
                    "from_user_id": m.from_user_id,
                    "from_name": user_names.get(m.from_user_id, "Unknown"),
                    "text": m.text,
                    "attachments": self._format_attachments(attachments_by_msg.get(m.id, [])),
                    "reactions": reactions_by_msg.get(m.id, []),
                    "created_at": self._iso(m.created_at),
                }
                for m in messages
            ],
        }

    async def _load_reactions(self, message_ids: list[str]) -> dict[str, list[dict]]:
        """Return {message_id: [{emoji, count, user_ids:[], user_names:[]}]}.

        Grouped and sorted by count desc so the frontend renders the most
        popular reaction first.
        """
        if not message_ids:
            return {}
        from src.models.internal_message_reaction import InternalMessageReaction
        rows = (await self.db.execute(
            select(
                InternalMessageReaction.message_id,
                InternalMessageReaction.emoji,
                InternalMessageReaction.user_id,
            ).where(InternalMessageReaction.message_id.in_(message_ids))
        )).all()
        if not rows:
            return {}

        # Resolve user names for the list of reacting users.
        user_ids = {r.user_id for r in rows}
        user_names = await self._load_user_names(user_ids)

        # Group: message_id → emoji → [user_ids]
        grouped: dict[str, dict[str, list[str]]] = {}
        for r in rows:
            grouped.setdefault(r.message_id, {}).setdefault(r.emoji, []).append(r.user_id)

        result: dict[str, list[dict]] = {}
        for mid, by_emoji in grouped.items():
            entries = [
                {
                    "emoji": emoji,
                    "count": len(uids),
                    "user_ids": uids,
                    "user_names": [user_names.get(uid, "Unknown") for uid in uids],
                }
                for emoji, uids in by_emoji.items()
            ]
            entries.sort(key=lambda e: (-e["count"], e["emoji"]))
            result[mid] = entries
        return result

    async def _load_user_names(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        result = await self.db.execute(
            select(User).where(User.id.in_(list(ids)))
        )
        return {u.id: f"{u.first_name} {u.last_name}".strip() for u in result.scalars().all()}

    async def _load_attachments(self, source_type: str, source_ids: list[str]) -> dict[str, list]:
        if not source_ids:
            return {}
        result = await self.db.execute(
            select(MessageAttachment).where(
                MessageAttachment.source_type == source_type,
                MessageAttachment.source_id.in_(source_ids),
            )
        )
        by_msg: dict[str, list] = {}
        for a in result.scalars().all():
            by_msg.setdefault(a.source_id, []).append(a)
        return by_msg

    @staticmethod
    def _format_attachments(attachments: list) -> list[dict]:
        return [
            {
                "id": a.id,
                "filename": a.filename,
                "url": f"/api/v1/attachments/{a.id}/file",
                "mime_type": a.mime_type,
                "file_size": a.file_size,
            }
            for a in attachments
        ]
