"""Service layer for agent action (job) business logic."""

from src.core.ai_models import get_model
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import anthropic
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_action_task import AgentActionTask
from src.models.agent_message import AgentMessage
from src.models.customer import Customer
from src.models.notification import Notification
from src.models.organization_user import OrganizationUser
from src.models.property import Property
from src.models.user import User
from src.models.water_feature import WaterFeature

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def _serialize_action(a: AgentAction, include_comments: bool = False) -> dict:
    d = {
        "id": a.id,
        "agent_message_id": a.agent_message_id,
        "action_type": a.action_type,
        "description": a.description,
        "assigned_to": a.assigned_to,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "status": a.status,
        "notes": a.notes,
        "customer_name": a.customer_name,
        "property_address": a.property_address,
        "created_by": a.created_by,
        "invoice_id": a.invoice_id,
        "parent_action_id": a.parent_action_id,
        "task_count": a.task_count or 0,
        "tasks_completed": a.tasks_completed or 0,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "is_suggested": a.is_suggested if hasattr(a, "is_suggested") else False,
        "suggestion_confidence": a.suggestion_confidence if hasattr(a, "suggestion_confidence") else None,
    }
    if include_comments and hasattr(a, "comments") and a.comments:
        d["comments"] = [
            {"id": c.id, "author": c.author, "text": c.text, "created_at": c.created_at.isoformat()}
            for c in a.comments
        ]
    return d


def _serialize_task(t: AgentActionTask) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "assigned_to": t.assigned_to,
        "status": t.status,
        "sort_order": t.sort_order,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "notes": t.notes,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "completed_by": t.completed_by,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat(),
    }


class AgentActionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _update_task_counts(self, action_id: str):
        """Recalculate denormalized task counts on the job."""
        total = (await self.db.execute(
            select(func.count(AgentActionTask.id)).where(
                AgentActionTask.action_id == action_id,
                AgentActionTask.status != "cancelled",
            )
        )).scalar() or 0
        done = (await self.db.execute(
            select(func.count(AgentActionTask.id)).where(
                AgentActionTask.action_id == action_id,
                AgentActionTask.status == "done",
            )
        )).scalar() or 0
        action = (await self.db.execute(
            select(AgentAction).where(AgentAction.id == action_id)
        )).scalar_one_or_none()
        if action:
            action.task_count = total
            action.tasks_completed = done

    async def _find_org_user(self, org_id: str, first_name: str, exclude_user_id: str | None = None):
        """Find an OrganizationUser by first name within an org."""
        query = (
            select(OrganizationUser)
            .join(User, OrganizationUser.user_id == User.id)
            .where(
                OrganizationUser.organization_id == org_id,
                User.first_name == first_name,
            )
        )
        if exclude_user_id:
            query = query.where(User.id != exclude_user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _build_customer_context(self, org_id: str, action: AgentAction) -> tuple[str | None, str]:
        """Build customer context string for AI calls. Returns (customer_id, context_text)."""
        customer_context = ""
        customer_id = None

        if action.property_address:
            customer_context += f"\nJob address: {action.property_address}"
        if action.customer_name:
            customer_context += f"\nJob contact: {action.customer_name}"

        # Try to find customer from linked message
        if action.agent_message_id:
            msg_check = await self.db.execute(
                select(AgentMessage).where(
                    AgentMessage.id == action.agent_message_id,
                    AgentMessage.organization_id == org_id,
                )
            )
            parent_msg = msg_check.scalar_one_or_none()
            if parent_msg and parent_msg.matched_customer_id:
                customer_id = parent_msg.matched_customer_id

        # For standalone actions, find customer by name
        if not customer_id and action.customer_name:
            cust_match = await self.db.execute(
                select(Customer).where(
                    Customer.organization_id == org_id,
                    Customer.is_active == True,
                    or_(
                        Customer.display_name_col.ilike(f"%{action.customer_name}%"),
                        Customer.first_name.ilike(f"%{action.customer_name}%"),
                        Customer.last_name.ilike(f"%{action.customer_name}%"),
                        Customer.company_name.ilike(f"%{action.customer_name}%"),
                    )
                ).limit(1)
            )
            matched = cust_match.scalar_one_or_none()
            if matched:
                customer_id = matched.id

        if customer_id:
            cust = (await self.db.execute(
                select(Customer).where(Customer.id == customer_id)
            )).scalar_one_or_none()
            if cust:
                customer_context += f"\nCustomer: {cust.display_name}"
                if cust.email:
                    customer_context += f"\nEmail: {cust.email}"
                if cust.phone:
                    customer_context += f"\nPhone: {cust.phone}"
                if cust.preferred_day:
                    customer_context += f"\nService days: {cust.preferred_day}"
                if cust.monthly_rate:
                    customer_context += f"\nRate: ${cust.monthly_rate:.2f}/mo"

                props = (await self.db.execute(
                    select(Property).where(
                        Property.customer_id == customer_id,
                        Property.is_active == True,
                    )
                )).scalars().all()
                for p in props:
                    customer_context += f"\nProperty: {p.full_address}"
                    if p.gate_code:
                        customer_context += f" (Gate: {p.gate_code})"
                    if p.access_instructions:
                        customer_context += f" Access: {p.access_instructions}"
                    if p.dog_on_property:
                        customer_context += " DOG"
                    wfs = (await self.db.execute(
                        select(WaterFeature).where(
                            WaterFeature.property_id == p.id,
                            WaterFeature.is_active == True,
                        )
                    )).scalars().all()
                    for wf in wfs:
                        parts = [wf.name or wf.water_type]
                        if wf.pool_gallons:
                            parts.append(f"{wf.pool_gallons:,} gal")
                        if wf.filter_type:
                            parts.append(f"filter: {wf.filter_type}")
                        if wf.pump_type:
                            parts.append(f"pump: {wf.pump_type}")
                        if wf.sanitizer_type:
                            parts.append(f"sanitizer: {wf.sanitizer_type}")
                        customer_context += f"\n  {', '.join(parts)}"

        return customer_id, customer_context

    # ---- Main CRUD ----

    async def list_actions(
        self,
        org_id: str,
        status: str | None = None,
        assigned_to: str | None = None,
        action_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List actions with optional filters."""
        query = (
            select(AgentAction, AgentMessage)
            .outerjoin(AgentMessage, AgentAction.agent_message_id == AgentMessage.id)
            .where(AgentAction.organization_id == org_id)
            .order_by(
                desc(AgentAction.status.in_(("open", "in_progress"))),
                AgentAction.due_date.asc().nulls_last(),
            )
            .limit(limit)
        )
        if status:
            query = query.where(AgentAction.status == status)
        if assigned_to:
            query = query.where(AgentAction.assigned_to == assigned_to)
        if action_type:
            query = query.where(AgentAction.action_type == action_type)

        result = await self.db.execute(query)
        rows = result.all()
        items = []
        for action, msg in rows:
            d = _serialize_action(action)
            if msg:
                d["from_email"] = msg.from_email
                d["customer_name"] = msg.customer_name or action.customer_name
                d["subject"] = msg.subject
            else:
                d["from_email"] = None
                d["customer_name"] = action.customer_name
                d["subject"] = None
            d["property_address"] = action.property_address
            items.append(d)
        return items

    async def create_action(
        self,
        org_id: str,
        action_type: str,
        description: str,
        created_by: str,
        agent_message_id: str | None = None,
        assigned_to: str | None = None,
        due_date: str | None = None,
        customer_name: str | None = None,
        property_address: str | None = None,
    ) -> dict:
        """Create a new action/job."""
        due = datetime.fromisoformat(due_date) if due_date else None
        action = AgentAction(
            organization_id=org_id,
            agent_message_id=agent_message_id or None,
            action_type=action_type,
            description=description,
            assigned_to=assigned_to,
            due_date=due,
            customer_name=customer_name,
            property_address=property_address,
            created_by=created_by,
            status="open",
        )
        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)
        return _serialize_action(action)

    async def update_action(
        self,
        org_id: str,
        action_id: str,
        user_id: str,
        user_first_name: str,
        status: str | None = None,
        assigned_to: str | None = None,
        description: str | None = None,
        due_date: str | None = None,
        notes: str | None = None,
        invoice_id: str | None = None,
    ) -> dict | None:
        """Update action status, assignment, description. Handles notifications and follow-up suggestions."""
        result = await self.db.execute(
            select(AgentAction).where(
                AgentAction.id == action_id,
                AgentAction.organization_id == org_id,
            )
        )
        action = result.scalar_one_or_none()
        if not action:
            return None

        was_not_done = action.status != "done"

        if status is not None:
            action.status = status
            if status == "done":
                action.completed_at = datetime.now(timezone.utc)
            elif status in ("open", "in_progress"):
                action.completed_at = None
        old_assignee = action.assigned_to
        if assigned_to is not None:
            action.assigned_to = assigned_to
        if description is not None:
            action.description = description
        if due_date is not None:
            action.due_date = datetime.fromisoformat(due_date) if due_date else None
        if notes is not None:
            action.notes = notes.strip() or None
        if invoice_id is not None:
            action.invoice_id = invoice_id

        await self.db.commit()

        # Notify new assignee on reassignment
        if assigned_to and assigned_to != old_assignee:
            target = await self._find_org_user(
                org_id, assigned_to.split()[0], exclude_user_id=user_id
            )
            if target:
                self.db.add(Notification(
                    organization_id=org_id,
                    user_id=target.user_id,
                    type="job_assigned",
                    title=f"Job assigned to you: {action.description[:50]}",
                    body=f"Assigned by {user_first_name}",
                    link=f"/jobs?action={action.id}",
                ))
                await self.db.commit()

        # If just marked done, evaluate if a follow-up action is needed
        suggestion = None
        if status == "done" and was_not_done:
            from src.services.customer_agent import evaluate_next_action
            try:
                rec = await evaluate_next_action(action_id)
                if rec:
                    due_days = rec.get("due_days", 3)
                    follow_due = datetime.now(timezone.utc) + timedelta(days=due_days) if due_days else None
                    suggested = AgentAction(
                        organization_id=org_id,
                        agent_message_id=rec["agent_message_id"],
                        action_type=rec["action_type"],
                        description=rec["description"],
                        due_date=follow_due,
                        status="suggested",
                        created_by="DeepBlue",
                    )
                    self.db.add(suggested)
                    await self.db.commit()
                    await self.db.refresh(suggested)
                    suggestion = {
                        **_serialize_action(suggested),
                        "reasoning": rec.get("reasoning", ""),
                    }
            except Exception as e:
                logger.error(f"Next action eval failed: {e}")

        result_dict = _serialize_action(action)
        if suggestion:
            result_dict["suggestion"] = suggestion
        return result_dict

    async def get_action_detail(self, org_id: str, action_id: str) -> dict | None:
        """Get action with comments, tasks, related jobs, parent message."""
        result = await self.db.execute(
            select(AgentAction)
            .options(selectinload(AgentAction.comments), selectinload(AgentAction.tasks))
            .where(AgentAction.id == action_id, AgentAction.organization_id == org_id)
        )
        action = result.scalar_one_or_none()
        if not action:
            return None

        d = _serialize_action(action, include_comments=True)

        if action.agent_message_id:
            msg_result = await self.db.execute(
                select(AgentMessage).where(
                    AgentMessage.id == action.agent_message_id,
                    AgentMessage.organization_id == org_id,
                )
            )
            msg = msg_result.scalar_one_or_none()
            if msg:
                d["from_email"] = msg.from_email
                d["customer_name"] = msg.customer_name or action.customer_name
                d["matched_customer_id"] = msg.matched_customer_id
                d["subject"] = msg.subject
                from src.services.agents.mail_agent import strip_quoted_reply, strip_email_signature
                d["email_body"] = strip_email_signature(strip_quoted_reply(msg.body))[:500] if msg.body else ""
                d["our_response"] = msg.final_response or msg.draft_response

                siblings_result = await self.db.execute(
                    select(AgentAction)
                    .options(selectinload(AgentAction.comments))
                    .where(
                        AgentAction.agent_message_id == action.agent_message_id,
                        AgentAction.organization_id == org_id,
                        AgentAction.id != action.id,
                    )
                    .order_by(AgentAction.created_at)
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
        else:
            d["customer_name"] = action.customer_name

        d["tasks"] = [_serialize_task(t) for t in (action.tasks or [])]

        return d

    async def add_comment(
        self,
        org_id: str,
        action_id: str,
        author: str,
        text: str,
        user_id: str,
        user_first_name: str,
    ) -> dict | None:
        """Add comment with DeepBlue auto-answer and resolution evaluation logic."""
        result = await self.db.execute(
            select(AgentAction).where(
                AgentAction.id == action_id,
                AgentAction.organization_id == org_id,
            )
        )
        action = result.scalar_one_or_none()
        if not action:
            return None

        comment = AgentActionComment(
            organization_id=org_id,
            action_id=action_id,
            author=author,
            text=text.strip(),
        )
        self.db.add(comment)

        # Notify assignee if someone else commented
        if action.assigned_to:
            assignee_ou = await self._find_org_user(
                org_id, action.assigned_to, exclude_user_id=user_id
            )
            if assignee_ou:
                self.db.add(Notification(
                    organization_id=org_id,
                    user_id=assignee_ou.user_id,
                    type="action_comment",
                    title=f"Comment on: {action.description[:60]}",
                    body=f"{user_first_name}: {text.strip()[:100]}",
                    link=f"/jobs?action={action_id}",
                ))

        await self.db.commit()
        await self.db.refresh(comment)

        # Run comment through the agent pipeline
        from src.services.agents.comment_pipeline import CommentPipeline

        pipeline = CommentPipeline(self.db)
        pipeline_result = await pipeline.process_comment(
            org_id=org_id,
            action=action,
            comment_text=text,
            user_id=user_id,
            user_name=user_first_name,
            build_customer_context_fn=self._build_customer_context,
            find_org_user_fn=self._find_org_user,
        )

        return {
            "id": comment.id,
            "author": comment.author,
            "text": comment.text,
            "created_at": comment.created_at.isoformat(),
            "action_resolved": pipeline_result.get("action_resolved", False),
            "action_updated": pipeline_result.get("updated_description") is not None,
            "new_description": pipeline_result.get("updated_description"),
            "auto_comment": pipeline_result.get("auto_comment"),
        }

    async def draft_invoice(self, org_id: str, action_id: str) -> dict | None:
        """AI-generated invoice draft from action context."""
        result = await self.db.execute(
            select(AgentAction)
            .options(selectinload(AgentAction.comments))
            .where(AgentAction.id == action_id, AgentAction.organization_id == org_id)
        )
        action = result.scalar_one_or_none()
        if not action:
            return None

        # Load parent message if exists
        msg = None
        if action.agent_message_id:
            msg_result = await self.db.execute(
                select(AgentMessage).where(
                    AgentMessage.id == action.agent_message_id,
                    AgentMessage.organization_id == org_id,
                )
            )
            msg = msg_result.scalar_one_or_none()

        # Get customer ID
        customer_id = msg.matched_customer_id if msg else None
        customer_name = (msg.customer_name or msg.from_email) if msg else (action.customer_name or "Unknown")

        if not customer_id and action.customer_name:
            cust_result = await self.db.execute(
                select(Customer.id).where(
                    Customer.organization_id == org_id,
                    Customer.display_name.ilike(f"%{action.customer_name}%"),
                ).limit(1)
            )
            customer_id = cust_result.scalar_one_or_none()

        # Build context
        comments_text = ""
        if action.comments:
            comments_text = "\n".join(
                f"- {c.author}: {c.text}" for c in action.comments
            )

        # Get sibling actions if linked to a message
        all_actions_text = ""
        if msg:
            siblings = await self.db.execute(
                select(AgentAction)
                .options(selectinload(AgentAction.comments))
                .where(
                    AgentAction.agent_message_id == msg.id,
                    AgentAction.organization_id == org_id,
                )
            )
            for a in siblings.scalars().all():
                all_actions_text += f"\n- [{a.status}] {a.action_type}: {a.description}"
                if a.comments:
                    for c in a.comments:
                        all_actions_text += f"\n  {c.author}: {c.text}"
        else:
            all_actions_text = f"\n- [{action.status}] {action.action_type}: {action.description}"
            if action.comments:
                for c in action.comments:
                    all_actions_text += f"\n  {c.author}: {c.text}"

        prompt = f"""Generate invoice line items for a pool service company based on this context.

Customer: {customer_name}
{f"Original email subject: {msg.subject}" if msg else f"Job: {action.action_type} — {action.description}"}

Action item: {action.action_type} — {action.description}

All action items and comments for this event:{all_actions_text}

Based on the work described, generate invoice line items. Extract specific services, parts, and costs from the comments and descriptions.

Respond with JSON:
{{
  "subject": "Brief invoice subject (e.g., 'Pool Valve Repair - Pinebrook Village')",
  "line_items": [
    {{
      "description": "what was done or provided",
      "quantity": 1,
      "unit_price": 0.00
    }}
  ],
  "notes": "any notes for the invoice"
}}

Rules:
- Extract actual dollar amounts mentioned in comments if available
- If no price was mentioned, use unit_price: 0 and note "Price TBD" in description
- Separate labor from parts/materials if both mentioned
- Keep descriptions clear and professional
- Include a subject line suitable for the invoice header"""

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model=await get_model("fast"),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
            if json_match:
                draft = json.loads(json_match.group())
                return {
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "subject": draft.get("subject", f"Service - {customer_name}"),
                    "line_items": draft.get("line_items", []),
                    "notes": draft.get("notes", ""),
                }
        except Exception as e:
            raise Exception(f"Failed to draft invoice: {str(e)}")

        return {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "subject": f"Service - {customer_name}",
            "line_items": [],
            "notes": "",
        }

    # ---- Tasks ----

    async def list_tasks(self, org_id: str, action_id: str) -> list[dict]:
        """List tasks for a job."""
        result = await self.db.execute(
            select(AgentActionTask).where(
                AgentActionTask.action_id == action_id,
                AgentActionTask.organization_id == org_id,
            ).order_by(AgentActionTask.sort_order, AgentActionTask.created_at)
        )
        return [_serialize_task(t) for t in result.scalars().all()]

    async def create_task(
        self,
        org_id: str,
        action_id: str,
        title: str,
        created_by: str,
        assigned_to: str | None = None,
        due_date: str | None = None,
        notes: str | None = None,
    ) -> dict | None:
        """Add a task to a job."""
        action = (await self.db.execute(
            select(AgentAction).where(
                AgentAction.id == action_id,
                AgentAction.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not action:
            return None

        due = datetime.fromisoformat(due_date) if due_date else None

        max_sort = (await self.db.execute(
            select(func.max(AgentActionTask.sort_order)).where(
                AgentActionTask.action_id == action_id
            )
        )).scalar() or 0

        task = AgentActionTask(
            organization_id=org_id,
            action_id=action_id,
            title=title,
            assigned_to=assigned_to,
            due_date=due,
            notes=notes,
            sort_order=max_sort + 1,
            created_by=created_by,
        )
        self.db.add(task)
        await self._update_task_counts(action_id)
        await self.db.commit()
        await self.db.refresh(task)

        return {
            "id": task.id,
            "title": task.title,
            "assigned_to": task.assigned_to,
            "status": task.status,
            "sort_order": task.sort_order,
            "created_at": task.created_at.isoformat(),
        }

    async def update_task(
        self,
        org_id: str,
        action_id: str,
        task_id: str,
        user_full_name: str,
        title: str | None = None,
        assigned_to: str | None = None,
        status: str | None = None,
        due_date: str | None = None,
        notes: str | None = None,
        sort_order: int | None = None,
    ) -> dict | None:
        """Update a task. Returns {"ok": True} or None if not found."""
        task = (await self.db.execute(
            select(AgentActionTask).where(
                AgentActionTask.id == task_id,
                AgentActionTask.action_id == action_id,
                AgentActionTask.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not task:
            return None

        if title is not None:
            task.title = title
        if assigned_to is not None:
            task.assigned_to = assigned_to
        if status is not None:
            task.status = status
            if status == "done":
                task.completed_at = datetime.now(timezone.utc)
                task.completed_by = user_full_name
            elif status == "open":
                task.completed_at = None
                task.completed_by = None
        if due_date is not None:
            task.due_date = datetime.fromisoformat(due_date) if due_date else None
        if notes is not None:
            task.notes = notes
        if sort_order is not None:
            task.sort_order = sort_order

        await self._update_task_counts(action_id)
        await self.db.commit()

        return {"ok": True}

    async def delete_task(self, org_id: str, action_id: str, task_id: str) -> bool:
        """Delete a task. Returns True if deleted, False if not found."""
        task = (await self.db.execute(
            select(AgentActionTask).where(
                AgentActionTask.id == task_id,
                AgentActionTask.action_id == action_id,
                AgentActionTask.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not task:
            return False

        await self.db.delete(task)
        await self._update_task_counts(action_id)
        await self.db.commit()

        return True
