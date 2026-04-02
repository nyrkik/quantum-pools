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

            # Unread status
            if read_map is not None:
                d["is_unread"] = (
                    t.last_message_at > read_map[t.id]
                    if t.id in read_map and t.last_message_at
                    else t.last_message_at is not None
                )
            else:
                d["is_unread"] = False

            results.append(d)
        return results

    async def one(self, thread: AgentThread) -> dict:
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
        }
