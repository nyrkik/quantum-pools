"""Service layer for agent action (job) business logic."""

from src.core.ai_models import get_model
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone

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

from src.presenters.action_presenter import ActionPresenter

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")



# _serialize_action REMOVED — use ActionPresenter instead




# _serialize_task REMOVED — use ActionPresenter._task() instead


class AgentActionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _next_estimate_number(self, org_id: str) -> str:
        """Generate next EST-YYYY-NNNN number."""
        from src.services.invoice_service import InvoiceService
        svc = InvoiceService(self.db)
        return await svc.next_estimate_number(org_id)

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

    async def _create_invoice_from_estimate(self, org_id: str, action_id: str) -> dict | None:
        """If the job has an approved estimate, create a draft invoice from it."""
        from src.models.invoice import Invoice
        from src.models.job_invoice import JobInvoice
        from src.services.invoice_service import InvoiceService
        from sqlalchemy.orm import selectinload

        # Find linked invoices/estimates for this job
        result = await self.db.execute(
            select(Invoice)
            .join(JobInvoice, JobInvoice.invoice_id == Invoice.id)
            .where(JobInvoice.action_id == action_id)
            .options(selectinload(Invoice.line_items))
        )
        linked = result.scalars().all()
        if not linked:
            return None

        # Find an approved estimate that hasn't been converted yet
        estimate = None
        for inv in linked:
            if inv.document_type == "estimate" and inv.approved_at and inv.status != "void":
                estimate = inv
                break
        if not estimate:
            return None

        # Check no invoice already exists for this job
        for inv in linked:
            if inv.document_type == "invoice":
                return None

        # Create draft invoice copying estimate line items
        svc = InvoiceService(self.db)
        line_items_data = []
        if estimate.line_items:
            for li in estimate.line_items:
                line_items_data.append({
                    "description": li.description,
                    "quantity": float(li.quantity),
                    "unit_price": float(li.unit_price),
                    "is_taxed": li.is_taxed if hasattr(li, "is_taxed") else False,
                })

        invoice = await svc.create(
            org_id=org_id,
            customer_id=estimate.customer_id,
            line_items_data=line_items_data,
            document_type="invoice",
            subject=estimate.subject,
            issue_date=date.today(),
            tax_rate=float(estimate.tax_rate or 0),
            discount=float(estimate.discount or 0),
            notes=estimate.notes,
            case_id=estimate.case_id,
        )

        # Link the new invoice to this job
        from src.services.job_invoice_service import link_job_invoice
        await link_job_invoice(self.db, action_id, invoice.id, linked_by="auto")
        await self.db.commit()

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "total": float(invoice.total or 0),
            "status": invoice.status,
            "estimate_number": estimate.invoice_number,
        }

    async def _detect_equipment_changes(self, org_id: str, action: AgentAction):
        """Delegated to equipment_agent.detect_equipment_changes."""
        from src.services.agents.equipment_agent import detect_equipment_changes
        await detect_equipment_changes(self.db, org_id, action)

    async def _build_customer_context(self, org_id: str, action: AgentAction) -> tuple[str | None, str]:
        """Delegated to customer_context_service.build_customer_context."""
        from src.services.customer_context_service import build_customer_context
        return await build_customer_context(
            self.db, org_id,
            customer_id=action.customer_id,
            customer_name=action.customer_name,
            agent_message_id=action.agent_message_id,
            property_address=action.property_address,
        )

    # ---- Main CRUD ----

    async def list_actions(
        self,
        org_id: str,
        status: str | None = None,
        assigned_to: str | None = None,
        action_type: str | None = None,
        customer_id: str | None = None,
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
        if customer_id:
            query = query.where(AgentAction.customer_id == customer_id)

        result = await self.db.execute(query)
        rows = result.all()

        # Build message map for presenter
        actions_list = []
        msg_map = {}
        for action, msg in rows:
            actions_list.append(action)
            if msg:
                msg_map[msg.id] = msg

        presenter = ActionPresenter(self.db)
        return await presenter.many(actions_list, msg_map=msg_map)

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
        customer_id: str | None = None,
        property_address: str | None = None,
        job_path: str = "internal",
        line_items: list | None = None,
    ) -> dict:
        """Create a new action/job. For customer path, auto-creates a draft estimate."""
        from src.models.customer import Customer

        # Resolve customer_id from name if not provided
        if not customer_id and customer_name:
            cust_result = await self.db.execute(
                select(Customer).where(Customer.organization_id == org_id).limit(50)
            )
            for c in cust_result.scalars().all():
                full = f"{c.first_name} {c.last_name}".strip()
                if customer_name.lower() in full.lower() or full.lower() in customer_name.lower():
                    customer_id = c.id
                    break

        due = datetime.fromisoformat(due_date) if due_date else None

        # Find or create a case for this job
        case_id = None
        try:
            from src.services.service_case_service import ServiceCaseService
            case_svc = ServiceCaseService(self.db)
            case = await case_svc.find_or_create_case(
                org_id=org_id,
                customer_id=customer_id,
                thread_id=None,
                subject=description,
                source="manual",
                created_by=created_by,
            )
            case_id = case.id
        except Exception as e:
            logger.warning(f"Case creation failed for manual job: {e}")

        action = AgentAction(
            organization_id=org_id,
            agent_message_id=agent_message_id or None,
            case_id=case_id,
            action_type=action_type,
            description=description,
            assigned_to=assigned_to,
            due_date=due,
            customer_id=customer_id,
            customer_name=customer_name,
            property_address=property_address,
            created_by=created_by,
            job_path=job_path,
            status="open",
        )
        self.db.add(action)
        await self.db.flush()

        # Customer path: create a draft estimate linked to this job
        if job_path == "customer" and line_items:
            import uuid as _uuid
            from src.models.invoice import Invoice, InvoiceLineItem

            customer_id = action.customer_id
            if not customer_id and customer_name:
                cust_result = await self.db.execute(
                    select(Customer).where(
                        Customer.organization_id == org_id,
                    ).limit(50)
                )
                for c in cust_result.scalars().all():
                    full = f"{c.first_name} {c.last_name}".strip()
                    if customer_name.lower() in full.lower() or full.lower() in customer_name.lower():
                        customer_id = c.id
                        action.customer_id = c.id
                        break

            total = sum(li.get("quantity", 1) * li.get("unit_price", 0) for li in line_items)
            invoice = Invoice(
                id=str(_uuid.uuid4()),
                organization_id=org_id,
                customer_id=customer_id,
                case_id=case_id,
                invoice_number=await self._next_estimate_number(org_id),
                document_type="estimate",
                subject=description,
                status="draft",
                issue_date=datetime.now(timezone.utc).date(),
                due_date=due.date() if due else None,
                total=total,
                balance=total,
            )
            self.db.add(invoice)
            await self.db.flush()

            for i, li in enumerate(line_items):
                qty = li.get("quantity", 1)
                price = li.get("unit_price", 0)
                line = InvoiceLineItem(
                    id=str(_uuid.uuid4()),
                    invoice_id=invoice.id,
                    description=li.get("description", ""),
                    quantity=qty,
                    unit_price=price,
                    total=qty * price,
                    sort_order=i,
                )
                self.db.add(line)

            from src.services.job_invoice_service import link_job_invoice
            await link_job_invoice(self.db, action.id, invoice.id)

        await self.db.commit()
        await self.db.refresh(action)
        return await ActionPresenter(self.db).one(action, include_comments=False, include_email=False)

    async def update_action(
        self,
        org_id: str,
        action_id: str,
        user_id: str,
        user_first_name: str,
        status: str | None = None,
        action_type: str | None = None,
        assigned_to: str | None = None,
        description: str | None = None,
        due_date: str | None = None,
        notes: str | None = None,
        invoice_id: str | None = None,
        thread_id: str | None = None,
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
        if action_type is not None:
            action.action_type = action_type
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
            from src.services.job_invoice_service import link_job_invoice
            await link_job_invoice(self.db, action.id, invoice_id)
        if thread_id is not None:
            action.thread_id = thread_id if thread_id else None

        await self.db.commit()

        # Recompute case flags/actor if this action belongs to a case
        if action.case_id:
            try:
                from src.services.service_case_service import ServiceCaseService
                case_svc = ServiceCaseService(self.db)
                await case_svc.update_status_from_children(action.case_id)
                await self.db.commit()
            except Exception as e:
                logger.warning(f"Case recompute failed for {action.case_id}: {e}")

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

        # Notify assignee when job is completed
        if status == "done" and was_not_done and action.assigned_to:
            target = await self._find_org_user(org_id, action.assigned_to.split()[0], exclude_user_id=user_id)
            if target:
                self.db.add(Notification(
                    organization_id=org_id,
                    user_id=target.user_id,
                    type="job_completed",
                    title=f"Job completed: {(action.description or '')[:50]}",
                    body=f"Marked done by {user_first_name}",
                    link=f"/jobs?action={action.id}",
                ))
                await self.db.commit()

        # If just marked done, check for equipment changes
        if status == "done" and was_not_done:
            try:
                await self._detect_equipment_changes(org_id, action)
            except Exception as e:
                logger.warning(f"Equipment change detection failed for {action_id}: {e}")

        # If just marked done, auto-create draft invoice from approved estimate
        created_invoice = None
        if status == "done" and was_not_done:
            try:
                created_invoice = await self._create_invoice_from_estimate(org_id, action_id)
            except Exception as e:
                logger.warning(f"Auto-invoice from estimate failed for {action_id}: {e}")

        # If just marked done, evaluate if a follow-up action is needed
        suggestion = None
        if status == "done" and was_not_done:
            from src.services.agents.job_manager import evaluate_next_action
            try:
                rec = await evaluate_next_action(action_id)
                if rec:
                    due_days = rec.get("due_days", 3)
                    follow_due = datetime.now(timezone.utc) + timedelta(days=due_days) if due_days else None
                    suggested = AgentAction(
                        organization_id=org_id,
                        agent_message_id=rec.get("agent_message_id"),
                        thread_id=action.thread_id,
                        case_id=action.case_id,
                        parent_action_id=action.id,
                        action_type=rec["action_type"],
                        description=rec["description"],
                        due_date=follow_due,
                        status="suggested",
                        created_by="DeepBlue",
                        customer_id=action.customer_id,
                        customer_name=action.customer_name,
                        property_address=action.property_address,
                    )
                    self.db.add(suggested)
                    await self.db.commit()
                    await self.db.refresh(suggested)
                    presenter = ActionPresenter(self.db)
                    suggestion = {
                        **(await presenter.one(suggested, include_comments=False, include_email=False)),
                        "reasoning": rec.get("reasoning", ""),
                    }
            except Exception as e:
                logger.error(f"Next action eval failed: {e}")

        presenter = ActionPresenter(self.db)
        result_dict = await presenter.one(action, include_comments=False, include_email=False)
        if suggestion:
            result_dict["suggestion"] = suggestion
        if created_invoice:
            result_dict["created_invoice"] = created_invoice
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

        return await ActionPresenter(self.db).one(action)

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

        pipeline_result: dict = {}
        clean_text = text.strip()

        # @DeepBlue — run through AI pipeline
        if clean_text.lower().startswith("@deepblue"):
            # Strip the mention for the pipeline
            command_text = re.sub(r'^@deepblue\s*', '', clean_text, flags=re.IGNORECASE).strip()
            if command_text:
                from src.services.agents.comment_pipeline import CommentPipeline
                pipeline = CommentPipeline(self.db)
                pipeline_result = await pipeline.process_comment(
                    org_id=org_id,
                    action=action,
                    comment_text=command_text,
                    user_id=user_id,
                    user_name=user_first_name,
                    build_customer_context_fn=self._build_customer_context,
                    find_org_user_fn=self._find_org_user,
                )

        # @{team member} — notify that person
        elif clean_text.startswith("@"):
            mention_match = re.match(r'^@(\S+(?:\s+\S+)?)\s*(.*)', clean_text, re.DOTALL)
            if mention_match:
                mentioned_name = mention_match.group(1)
                target_ou = await self._find_org_user(org_id, mentioned_name, exclude_user_id=None)
                if target_ou:
                    self.db.add(Notification(
                        organization_id=org_id,
                        user_id=target_ou.user_id,
                        type="mention",
                        title=f"You were mentioned on: {action.description[:50]}",
                        body=f"{user_first_name}: {clean_text[:100]}",
                        link=f"/jobs?action={action_id}",
                    ))
                    await self.db.commit()

        # No @ — just a comment, no AI processing

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

        # Get customer ID and display name from source of truth
        customer_id = action.customer_id or (msg.matched_customer_id if msg else None)
        customer_name = "Unknown"

        if customer_id:
            cust = (await self.db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
            if cust:
                customer_name = cust.display_name

        if customer_name == "Unknown":
            customer_name = (msg.customer_name or msg.from_email) if msg else (action.customer_name or "Unknown")

        if not customer_id and action.customer_name:
            cust_result = await self.db.execute(
                select(Customer.id).where(
                    Customer.organization_id == org_id,
                    Customer.display_name_col.ilike(f"%{action.customer_name}%"),
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

        # Get org billing rate
        from src.models.org_cost_settings import OrgCostSettings
        settings_result = await self.db.execute(
            select(OrgCostSettings).where(OrgCostSettings.organization_id == org_id)
        )
        settings = settings_result.scalar_one_or_none()
        labor_rate = settings.billable_labor_rate if settings and hasattr(settings, "billable_labor_rate") else 125.0

        prompt = f"""You are a pool service estimator. Generate estimate/invoice line items from this job context.

Customer: {customer_name}
{f"Original email subject: {msg.subject}" if msg else f"Job: {action.action_type} — {action.description}"}

Action item: {action.action_type} — {action.description}

All action items and comments:{all_actions_text}

Labor rate: ${labor_rate:.2f}/hour. Use this exact rate for all labor line items.

Respond with JSON only:
{{
  "subject": "Short title (e.g., 'Pool Valve Repair - Pinebrook Village')",
  "line_items": [
    {{"description": "what was done or provided", "quantity": 1, "unit_price": 100.00}}
  ],
  "notes": ""
}}

Rules:
- Every line item MUST have a real price. Extract from comments if mentioned, otherwise use realistic market prices. NEVER use $0 or "Price TBD".
- Separate labor from parts/materials if both are mentioned.
- Descriptions: professional, specific to the work. No addresses, no customer names, no internal status info.
- Subject: short description of the work. No pricing language, no "TBD", no dollar amounts.
- Notes: ONLY include notes if there is genuinely useful information for the customer (e.g., warranty terms, scheduling constraints). If there is nothing useful, use an empty string. NEVER include internal status, placeholder text, "awaiting assessment", "customer name pending", or any speculative language. When in doubt, leave notes empty."""

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
        return [ActionPresenter._task(t) for t in result.scalars().all()]

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
