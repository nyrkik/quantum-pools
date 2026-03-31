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

    async def _detect_equipment_changes(self, org_id: str, action: AgentAction):
        """When a job is marked done, use AI to detect if equipment was installed/replaced and update records."""
        # Only process jobs that have a customer
        customer_id = action.customer_id
        if not customer_id:
            return

        # Build job context — description + comments + email body
        job_text = action.description or ""
        comments = (await self.db.execute(
            select(AgentActionComment).where(AgentActionComment.action_id == action.id).order_by(AgentActionComment.created_at)
        )).scalars().all()
        for c in comments:
            if not c.text.startswith("[DRAFT_EMAIL]") and not c.text.startswith("[SENT_EMAIL]"):
                job_text += f"\n{c.text}"

        if action.agent_message_id:
            msg = (await self.db.execute(
                select(AgentMessage).where(AgentMessage.id == action.agent_message_id)
            )).scalar_one_or_none()
            if msg:
                job_text += f"\nEmail: {msg.body or ''}"
                if msg.final_response:
                    job_text += f"\nOur reply: {msg.final_response}"

        if len(job_text.strip()) < 20:
            return

        # Get current equipment for context
        props = (await self.db.execute(
            select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
        )).scalars().all()

        current_equip = []
        for p in props:
            wfs = (await self.db.execute(
                select(WaterFeature).where(WaterFeature.property_id == p.id, WaterFeature.is_active == True)
            )).scalars().all()
            for wf in wfs:
                from src.models.equipment_item import EquipmentItem
                items = (await self.db.execute(
                    select(EquipmentItem).where(EquipmentItem.water_feature_id == wf.id, EquipmentItem.is_active == True)
                )).scalars().all()
                for ei in items:
                    current_equip.append({
                        "id": ei.id,
                        "wf_id": wf.id,
                        "wf_name": wf.name or wf.water_type,
                        "type": ei.equipment_type,
                        "name": ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip(),
                    })

        # Ask AI if equipment changed
        import anthropic
        import json
        from src.core.ai_models import get_model

        equip_list = "\n".join(f"- {e['type']}: {e['name']} (on {e['wf_name']})" for e in current_equip) if current_equip else "No equipment on file"

        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model=get_model("fast"),
                max_tokens=500,
                messages=[{"role": "user", "content": f"""Analyze this completed pool service job. Was any equipment installed, replaced, or removed?

JOB DETAILS:
{job_text[:1500]}

CURRENT EQUIPMENT ON FILE:
{equip_list}

If equipment was changed, return JSON:
{{"changes": [{{"action": "install"|"replace"|"remove", "equipment_type": "pump"|"filter"|"heater"|"chlorinator"|"automation"|"booster_pump"|"chemical_feeder", "old_name": "name of replaced item or null", "new_name": "full name of new equipment e.g. Waterway Crystal Water DE Filter", "new_brand": "manufacturer", "new_model": "model number if known"}}]}}

If NO equipment changes, return: {{"changes": []}}

JSON only, no markdown."""}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
        except Exception as e:
            logger.warning(f"AI equipment detection failed: {e}")
            return

        changes = result.get("changes", [])
        if not changes:
            return

        logger.info(f"Equipment changes detected for job {action.id}: {changes}")

        from src.models.equipment_item import EquipmentItem
        from src.services.parts.equipment_catalog_service import EquipmentCatalogService
        import uuid as _uuid

        catalog_svc = EquipmentCatalogService(self.db)

        for change in changes:
            eq_type = change.get("equipment_type", "equipment")
            new_name = change.get("new_name", "")
            action_type = change.get("action", "install")

            if action_type == "remove":
                # Deactivate matching equipment
                old_name = change.get("old_name", "")
                if old_name:
                    for e in current_equip:
                        if old_name.lower() in e["name"].lower() or e["name"].lower() in old_name.lower():
                            old_item = (await self.db.execute(
                                select(EquipmentItem).where(EquipmentItem.id == e["id"])
                            )).scalar_one_or_none()
                            if old_item:
                                old_item.is_active = False
                continue

            if not new_name:
                continue

            # Resolve new equipment against catalog
            catalog_result = await catalog_svc.resolve(new_name, eq_type)
            catalog_id = catalog_result.get("entry", {}).get("id") if catalog_result.get("entry") else None

            # Find which WF to add to — match by old equipment or use first WF
            target_wf_id = None
            old_name = change.get("old_name")
            if old_name and action_type == "replace":
                for e in current_equip:
                    if e["type"] == eq_type and (old_name.lower() in e["name"].lower() or e["name"].lower() in old_name.lower()):
                        target_wf_id = e["wf_id"]
                        # Deactivate old
                        old_item = (await self.db.execute(
                            select(EquipmentItem).where(EquipmentItem.id == e["id"])
                        )).scalar_one_or_none()
                        if old_item:
                            old_item.is_active = False
                        break

            if not target_wf_id and props:
                # Default to first WF on first property
                first_wf = (await self.db.execute(
                    select(WaterFeature).where(
                        WaterFeature.property_id == props[0].id, WaterFeature.is_active == True
                    ).limit(1)
                )).scalar_one_or_none()
                if first_wf:
                    target_wf_id = first_wf.id

            if not target_wf_id:
                continue

            # Create new equipment item
            new_item = EquipmentItem(
                id=str(_uuid.uuid4()),
                organization_id=org_id,
                water_feature_id=target_wf_id,
                equipment_type=eq_type,
                brand=change.get("new_brand"),
                model=change.get("new_model"),
                normalized_name=new_name,
                catalog_equipment_id=catalog_id,
            )
            self.db.add(new_item)
            logger.info(f"Added equipment: {new_name} ({eq_type}) to WF {target_wf_id}")

        await self.db.commit()

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
                        customer_context += f"\n  {', '.join(parts)}"

                        # Include equipment from catalog
                        from src.models.equipment_item import EquipmentItem
                        from sqlalchemy.orm import selectinload as _sil
                        equip_result = await self.db.execute(
                            select(EquipmentItem).options(_sil(EquipmentItem.catalog_equipment)).where(
                                EquipmentItem.water_feature_id == wf.id,
                                EquipmentItem.is_active == True,
                            )
                        )
                        for ei in equip_result.scalars().all():
                            name = (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                                    ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip())
                            if name:
                                customer_context += f"\n    {ei.equipment_type}: {name}"

        return customer_id, customer_context

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
        action = AgentAction(
            organization_id=org_id,
            agent_message_id=agent_message_id or None,
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

            action.invoice_id = invoice.id

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
                        agent_message_id=rec.get("agent_message_id"),
                        thread_id=action.thread_id,
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
