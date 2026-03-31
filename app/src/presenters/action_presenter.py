"""ActionPresenter — single source of truth for AgentAction serialization.

Resolves:
- customer_id → Customer.display_name (not raw customer_name)
- customer_id → first Property address
- agent_message_id → email context (from, subject, body)
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.presenters.base import Presenter
from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_action_task import AgentActionTask
from src.models.agent_message import AgentMessage
from src.models.customer import Customer


class ActionPresenter(Presenter):
    """Present AgentAction (job) data with resolved FKs."""

    async def many(self, actions: list[AgentAction], msg_map: dict[str, AgentMessage] | None = None) -> list[dict]:
        """Present a list of actions with batch-loaded customer data."""
        # Batch load customers — include message matched_customer_id and thread matched_customer_id
        cust_ids = {a.customer_id for a in actions if a.customer_id}
        if msg_map:
            for msg in msg_map.values():
                if msg.matched_customer_id:
                    cust_ids.add(msg.matched_customer_id)
        # Also check threads for any remaining unmatched actions
        thread_ids = {a.thread_id for a in actions if a.thread_id and not a.customer_id}
        if thread_ids:
            from src.models.agent_thread import AgentThread
            thread_result = await self.db.execute(
                select(AgentThread.id, AgentThread.matched_customer_id).where(
                    AgentThread.id.in_(list(thread_ids)),
                    AgentThread.matched_customer_id.isnot(None),
                )
            )
            thread_cust_map = {tid: cid for tid, cid in thread_result.all()}
            cust_ids.update(thread_cust_map.values())
        else:
            thread_cust_map = {}

        customers = await self._load_customers(cust_ids)
        addresses = await self._load_customer_addresses(cust_ids)

        results = []
        for action in actions:
            d = self._base(action)
            msg = msg_map.get(action.agent_message_id) if msg_map and action.agent_message_id else None

            # Customer — always from source of truth
            # Try action.customer_id → message matched → thread matched
            cust_id = (action.customer_id
                       or (msg.matched_customer_id if msg else None)
                       or thread_cust_map.get(action.thread_id))
            cust = customers.get(cust_id) if cust_id else None
            if not cust and cust_id and cust_id not in customers:
                # Batch didn't include this — load individually
                extra = await self._load_customers({cust_id})
                cust = extra.get(cust_id)
                if cust:
                    customers[cust_id] = cust
                    extra_addr = await self._load_customer_addresses({cust_id})
                    addresses.update(extra_addr)
            if cust:
                d["customer_name"] = cust.display_name
                d["contact_name"] = action.customer_name if action.customer_name and action.customer_name != cust.display_name else None
                d["customer_address"] = addresses.get(cust_id, action.property_address)
            else:
                d["customer_name"] = action.customer_name
                d["contact_name"] = None
                d["customer_address"] = action.property_address

            # Message context
            if msg:
                d["from_email"] = msg.from_email
                d["subject"] = msg.subject
            else:
                d["from_email"] = None
                d["subject"] = None

            results.append(d)
        return results

    async def one(self, action: AgentAction, include_comments: bool = True, include_email: bool = True) -> dict:
        """Present a single action with full detail."""
        d = self._base(action)

        # Customer — from source of truth
        cust_id = action.customer_id
        if include_email and action.agent_message_id:
            msg = (await self.db.execute(
                select(AgentMessage).where(AgentMessage.id == action.agent_message_id)
            )).scalar_one_or_none()
            if msg:
                cust_id = cust_id or msg.matched_customer_id
                d["from_email"] = msg.from_email
                d["matched_customer_id"] = msg.matched_customer_id
                d["subject"] = msg.subject
                from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature
                d["email_body"] = strip_email_signature(strip_quoted_reply(msg.body)) if msg.body else ""
                d["our_response"] = msg.final_response or msg.draft_response
                d["response_is_draft"] = not msg.final_response and bool(msg.draft_response)

                # Related jobs from same message
                siblings_result = await self.db.execute(
                    select(AgentAction)
                    .options(selectinload(AgentAction.comments))
                    .where(
                        AgentAction.agent_message_id == action.agent_message_id,
                        AgentAction.organization_id == action.organization_id,
                        AgentAction.id != action.id,
                    ).order_by(AgentAction.created_at)
                )
                d["related_jobs"] = [
                    {
                        "id": s.id,
                        "action_type": s.action_type,
                        "description": s.description,
                        "status": s.status,
                        "comments": [
                            {"author": c.author, "text": c.text}
                            for c in (s.comments or [])
                        ],
                    }
                    for s in siblings_result.scalars().all()
                ]

        # Resolve customer from source of truth
        if cust_id:
            cust = (await self.db.execute(
                select(Customer).where(Customer.id == cust_id)
            )).scalar_one_or_none()
            if cust:
                d["customer_name"] = cust.display_name
                d["contact_name"] = action.customer_name if action.customer_name != cust.display_name else None
            else:
                d["customer_name"] = action.customer_name
        else:
            d["customer_name"] = action.customer_name

        # Comments — only access if explicitly loaded (avoid lazy load in async)
        if include_comments:
            try:
                comments = action.comments
                if comments:
                    d["comments"] = [
                        {"id": c.id, "author": c.author, "text": c.text, "created_at": self._iso(c.created_at)}
                        for c in comments
                    ]
            except Exception:
                d["comments"] = []

        # Tasks — only access if explicitly loaded
        try:
            tasks = action.tasks
            d["tasks"] = [self._task(t) for t in (tasks or [])]
        except Exception:
            d["tasks"] = []

        return d

    def _base(self, a: AgentAction) -> dict:
        """Base fields — never returned directly, always augmented by one() or many()."""
        return {
            "id": a.id,
            "agent_message_id": a.agent_message_id,
            "thread_id": a.thread_id,
            "customer_id": a.customer_id,
            "action_type": a.action_type,
            "description": a.description,
            "assigned_to": a.assigned_to,
            "due_date": self._iso(a.due_date),
            "status": a.status,
            "job_path": a.job_path if hasattr(a, "job_path") else "internal",
            "notes": a.notes,
            "invoice_id": a.invoice_id,
            "parent_action_id": a.parent_action_id,
            "task_count": a.task_count or 0,
            "tasks_completed": a.tasks_completed or 0,
            "completed_at": self._iso(a.completed_at),
            "created_at": self._iso(a.created_at),
            "is_suggested": a.is_suggested if hasattr(a, "is_suggested") else False,
            "suggestion_confidence": a.suggestion_confidence if hasattr(a, "suggestion_confidence") else None,
            "created_by": a.created_by,
            "property_address": a.property_address,
        }

    @staticmethod
    def _task(t: AgentActionTask) -> dict:
        return {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "assigned_to": t.assigned_to,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "notes": t.notes,
            "sort_order": t.sort_order,
        }
