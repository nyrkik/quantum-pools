"""ThreadPresenter — single source of truth for AgentThread serialization.

Resolves:
- matched_customer_id → Customer.display_name (not raw customer_name)
- matched_customer_id → first Property address
"""

from datetime import datetime

from src.presenters.base import Presenter
from src.models.agent_thread import AgentThread


class ThreadPresenter(Presenter):
    """Present AgentThread data with resolved FKs."""

    async def many(self, threads: list[AgentThread], read_map: dict[str, datetime] | None = None) -> list[dict]:
        """Present a list of threads with batch-loaded customer data."""
        cust_ids = {t.matched_customer_id for t in threads if t.matched_customer_id}
        customers = await self._load_customers(cust_ids)
        addresses = await self._load_customer_addresses(cust_ids)

        # Batch-resolve sender tags via InboxRulesService (unified rule engine).
        # Each unique sender is looked up once; thread-level assignment happens
        # in the per-thread loop below.
        sender_tag_by_email: dict[str, str] = {}
        if threads:
            from src.services.inbox_rules_service import InboxRulesService
            org_id = threads[0].organization_id
            svc = InboxRulesService(self.db)
            unique_senders = {t.contact_email.lower() for t in threads if t.contact_email}
            for sender in unique_senders:
                tag = await svc.get_sender_tag(sender, org_id)
                if tag:
                    sender_tag_by_email[sender] = tag

        results = []
        for t in threads:
            d = self._base(t)

            # Customer — always from source of truth
            cust = customers.get(t.matched_customer_id) if t.matched_customer_id else None
            if cust:
                d["customer_name"] = cust.display_name
                d["contact_name"] = t.customer_name if t.customer_name != cust.display_name else None
                d["customer_address"] = addresses.get(t.matched_customer_id)
            else:
                d["customer_name"] = t.customer_name
                d["contact_name"] = None
                d["customer_address"] = None

            # Sender tag — already resolved via the rule engine above.
            d["sender_tag"] = (
                sender_tag_by_email.get(t.contact_email.lower())
                if t.contact_email
                else None
            )

            # Unread status — rule-driven auto_read_at silences threads that
            # matched a mark_as_read rule up to last_message_at. A later
            # message without the rule firing re-unreads the thread naturally.
            if read_map is not None:
                user_read = read_map.get(t.id)
                effective_read = max(
                    x for x in [user_read, t.auto_read_at] if x is not None
                ) if (user_read or t.auto_read_at) else None
                d["is_unread"] = (
                    (t.last_message_at > effective_read)
                    if effective_read and t.last_message_at
                    else t.last_message_at is not None
                )
            else:
                d["is_unread"] = False

            results.append(d)
        return results

    async def one(self, thread: AgentThread, user_id: str | None = None) -> dict:
        """Present a single thread with resolved customer data."""
        d = self._base(thread)

        if thread.matched_customer_id:
            customers = await self._load_customers({thread.matched_customer_id})
            addresses = await self._load_customer_addresses({thread.matched_customer_id})
            cust = customers.get(thread.matched_customer_id)
            if cust:
                d["customer_name"] = cust.display_name
                d["contact_name"] = thread.customer_name if thread.customer_name != cust.display_name else None
                d["customer_address"] = addresses.get(thread.matched_customer_id)
            else:
                d["customer_name"] = thread.customer_name
        else:
            d["customer_name"] = thread.customer_name

        # Unread status — honor rule-driven auto_read_at alongside ThreadRead.
        if user_id:
            from sqlalchemy import select
            from src.models.thread_read import ThreadRead
            read = (await self.db.execute(
                select(ThreadRead.read_at).where(
                    ThreadRead.thread_id == thread.id,
                    ThreadRead.user_id == user_id,
                )
            )).scalar_one_or_none()
            effective_read = max(
                x for x in [read, thread.auto_read_at] if x is not None
            ) if (read or thread.auto_read_at) else None
            d["is_unread"] = (
                (thread.last_message_at > effective_read)
                if effective_read and thread.last_message_at
                else thread.last_message_at is not None
            )
        else:
            d["is_unread"] = False

        # Auto-handled (AI hid this from inbox without human action)
        d["is_auto_handled"] = (
            thread.last_direction == "inbound"
            and thread.status in ("ignored", "handled")
            and not thread.has_pending
        )

        # Sender tag via the unified rule engine
        if thread.contact_email:
            from src.services.inbox_rules_service import InboxRulesService
            d["sender_tag"] = await InboxRulesService(self.db).get_sender_tag(
                thread.contact_email, thread.organization_id
            )
        else:
            d["sender_tag"] = None

        return d

    def _base(self, t: AgentThread) -> dict:
        return {
            "id": t.id,
            "contact_email": t.contact_email,
            "subject": t.subject,
            "matched_customer_id": t.matched_customer_id,
            "status": t.status,
            "urgency": t.urgency,
            "category": t.category,
            "message_count": t.message_count,
            "last_message_at": self._iso(t.last_message_at),
            "last_direction": t.last_direction,
            "last_snippet": t.last_snippet,
            "has_pending": t.has_pending,
            "has_open_actions": t.has_open_actions,
            "assigned_to_user_id": t.assigned_to_user_id,
            "assigned_to_name": t.assigned_to_name,
            "assigned_at": self._iso(t.assigned_at),
            "visibility_permission": t.visibility_permission,
            "delivered_to": t.delivered_to,
            "case_id": t.case_id if hasattr(t, "case_id") else None,
            "folder_id": t.folder_id,
        }
