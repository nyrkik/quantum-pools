"""MessagePresenter — internal thread/message serialization."""

from sqlalchemy import select, func
from src.presenters.base import Presenter
from src.models.internal_message import InternalThread, InternalMessage
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

            results.append({
                "id": t.id,
                "participants": other_names,
                "participant_ids": t.participant_ids,
                "subject": t.subject,
                "customer_name": cust.display_name if cust else None,
                "customer_id": t.customer_id,
                "action_id": t.action_id,
                "priority": t.priority,
                "status": t.status,
                "message_count": t.message_count,
                "last_message": last_msg.text[:100] if last_msg else None,
                "last_message_by": user_names.get(t.last_message_by, "") if t.last_message_by else None,
                "last_message_at": self._iso(t.last_message_at),
                "acknowledged_at": self._iso(t.acknowledged_at),
                "completed_at": self._iso(t.completed_at),
                "converted_to_action_id": t.converted_to_action_id,
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

        return {
            "id": thread.id,
            "participant_ids": thread.participant_ids,
            "participants": [user_names.get(uid, "Unknown") for uid in (thread.participant_ids or [])],
            "subject": thread.subject,
            "customer_name": cust.display_name if cust else None,
            "customer_id": thread.customer_id,
            "action_id": thread.action_id,
            "priority": thread.priority,
            "status": thread.status,
            "acknowledged_at": self._iso(thread.acknowledged_at),
            "completed_at": self._iso(thread.completed_at),
            "converted_to_action_id": thread.converted_to_action_id,
            "created_at": self._iso(thread.created_at),
            "messages": [
                {
                    "id": m.id,
                    "from_user_id": m.from_user_id,
                    "from_name": user_names.get(m.from_user_id, "Unknown"),
                    "text": m.text,
                    "created_at": self._iso(m.created_at),
                }
                for m in messages
            ],
        }

    async def _load_user_names(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        result = await self.db.execute(
            select(User).where(User.id.in_(list(ids)))
        )
        return {u.id: f"{u.first_name} {u.last_name}".strip() for u in result.scalars().all()}
