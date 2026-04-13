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

        # Batch-load auto_sent status per thread
        auto_sent_threads: set[str] = set()
        if threads:
            from sqlalchemy import select
            from src.models.agent_message import AgentMessage
            thread_ids = [t.id for t in threads]
            rows = (await self.db.execute(
                select(AgentMessage.thread_id)
                .where(AgentMessage.thread_id.in_(thread_ids), AgentMessage.status == "auto_sent")
                .distinct()
            )).all()
            auto_sent_threads = {r[0] for r in rows}

        # Batch-load sender tags from suppressed_email_senders
        sender_tags: dict[str, str] = {}
        if threads:
            from sqlalchemy import select, func
            from src.models.suppressed_sender import SuppressedEmailSender
            org_id = threads[0].organization_id
            sender_emails = {t.contact_email.lower() for t in threads if t.contact_email}
            if sender_emails:
                # Check exact matches + domain patterns
                sender_domains = {f"*@{e.split('@')[-1]}" for e in sender_emails if "@" in e}
                all_patterns = sender_emails | sender_domains
                rows = (await self.db.execute(
                    select(SuppressedEmailSender.email_pattern, SuppressedEmailSender.reason)
                    .where(
                        SuppressedEmailSender.organization_id == org_id,
                        func.lower(SuppressedEmailSender.email_pattern).in_(all_patterns),
                    )
                )).all()
                for pattern, reason in rows:
                    sender_tags[pattern.lower()] = reason or "other"

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

            # Sender tag (exact match, then domain pattern)
            if t.contact_email:
                email_lower = t.contact_email.lower()
                d["sender_tag"] = sender_tags.get(email_lower)
                if not d["sender_tag"] and "@" in email_lower:
                    d["sender_tag"] = sender_tags.get(f"*@{email_lower.split('@')[-1]}")
            else:
                d["sender_tag"] = None

            # Auto-sent
            d["has_auto_sent"] = t.id in auto_sent_threads

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

        # Unread status
        if user_id:
            from sqlalchemy import select
            from src.models.thread_read import ThreadRead
            read = (await self.db.execute(
                select(ThreadRead.read_at).where(
                    ThreadRead.thread_id == thread.id,
                    ThreadRead.user_id == user_id,
                )
            )).scalar_one_or_none()
            d["is_unread"] = (
                thread.last_message_at > read if read and thread.last_message_at else thread.last_message_at is not None
            )
        else:
            d["is_unread"] = False

        # Auto-sent
        from src.models.agent_message import AgentMessage
        auto = (await self.db.execute(
            select(AgentMessage.id).where(
                AgentMessage.thread_id == thread.id,
                AgentMessage.status == "auto_sent",
            ).limit(1)
        )).scalar_one_or_none()
        d["has_auto_sent"] = auto is not None

        # Sender tag
        if thread.contact_email:
            from sqlalchemy import select, func
            from src.models.suppressed_sender import SuppressedEmailSender
            tag = (await self.db.execute(
                select(SuppressedEmailSender.reason).where(
                    SuppressedEmailSender.organization_id == thread.organization_id,
                    func.lower(SuppressedEmailSender.email_pattern) == thread.contact_email.lower(),
                ).limit(1)
            )).scalar_one_or_none()
            d["sender_tag"] = tag
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
