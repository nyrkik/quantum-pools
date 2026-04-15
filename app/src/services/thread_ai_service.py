"""Thread AI service — Claude-powered drafting, job extraction, estimate generation.

Split from AgentThreadService to isolate AI-powered operations.
All Anthropic calls use AsyncAnthropic (non-blocking).
"""

import json
import logging
import os
import re
from datetime import date as date_type

from anthropic import AsyncAnthropic
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.ai_models import get_model
from src.models.agent_action import AgentAction
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


class ThreadAIService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def revise_draft(self, org_id: str, thread_id: str, draft: str, instruction: str) -> dict:
        """Revise a draft response using Claude."""
        thread = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        prompt = f"""Revise this email draft based on the instruction below.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}

Current draft:
{draft}

Instruction: {instruction}

Rules:
- Apply the instruction to the draft
- Keep the same general structure and signature
- Never admit fault or accept blame
- Return ONLY the revised email text, nothing else"""

        try:
            client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
            response = await client.messages.create(
                model=await get_model("fast"),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"draft": response.content[0].text.strip()}
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

    async def draft_followup(self, org_id: str, thread_id: str) -> dict:
        """Draft a follow-up for a thread using full conversation context."""
        thread = (await self.db.execute(select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id))).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Get conversation
        msgs = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id, AgentMessage.organization_id == org_id).order_by(AgentMessage.received_at)
        )).scalars().all()

        convo = ""
        for m in msgs:
            who = "Client" if m.direction == "inbound" else "Us"
            convo += f"\n[{who}]: {(m.body or m.final_response or '')[:300]}"

        # Get actions + comments
        actions_result = await self.db.execute(
            select(AgentAction).options(selectinload(AgentAction.comments)).where(AgentAction.thread_id == thread_id, AgentAction.organization_id == org_id)
        )
        actions_ctx = ""
        for a in actions_result.scalars().all():
            actions_ctx += f"\n- [{a.status}] {a.action_type}: {a.description}"
            if a.comments:
                for c in a.comments:
                    actions_ctx += f"\n  {c.author}: {c.text}"

        prompt = f"""Draft a follow-up email for a pool service company.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Jobs and comments:{actions_ctx or ' None'}

Draft a follow-up email continuing this conversation. Reference what's been discussed and any work done.

Rules:
- Professional, friendly tone
- Never admit fault
- Keep it concise — 2-4 sentences
- NEVER include the property address in the email. The client knows where they live. Use property name if it has one, otherwise skip.
- Do NOT include a signature — the system appends it automatically
- End with a brief closing like "Best," on its own line

Return ONLY the email body text (no signature)."""

        # Inject lessons from past corrections
        try:
            from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_DRAFTER
            learner = AgentLearningService(self.db)
            lessons = await learner.build_lessons_prompt(
                org_id, AGENT_EMAIL_DRAFTER,
                category=thread.category, customer_id=thread.matched_customer_id,
            )
            if lessons:
                prompt += "\n\n" + lessons
        except Exception:
            pass

        try:
            client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
            response = await client.messages.create(
                model=await get_model("fast"),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"draft": response.content[0].text.strip(), "to": thread.contact_email, "subject": thread.subject}
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

    async def create_job_from_thread(self, org_id: str, thread_id: str, created_by: str) -> dict:
        """AI reads conversation and creates a job with description extracted from context."""
        thread = (await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Jobs live inside cases. The thread must be linked to a case first — either attached
        # to an existing case or a new case created — via LinkCasePicker in the UI.
        if not thread.case_id:
            return {"error": "no_case", "detail": "Link this thread to a case before adding a job"}

        # A thread can legitimately spawn multiple jobs (different work items surfaced in same
        # conversation). All jobs from the thread share a case via thread.case_id.

        # Build conversation context
        msgs = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id).order_by(AgentMessage.received_at)
        )).scalars().all()

        convo = ""
        for m in msgs:
            who = "Client" if m.direction == "inbound" else "Us"
            convo += f"\n[{who}]: {(m.body or '')[:300]}"

        # AI extracts job details
        prompt = f"""Extract a job/work item from this pool service email conversation.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Respond with JSON:
{{"action_type": "repair|follow_up|bid|site_visit|callback|schedule_change|equipment|other", "description": "MAXIMUM 8 WORDS. Format: verb + what — location. Example: 'Replace pump seal — Sierra Oaks'. NO addresses, emails, phone numbers, or extra details."}}"""

        try:
            client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
            response = await client.messages.create(
                model=await get_model("fast"),
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
            if not json_match:
                return {"error": "ai_failed", "detail": "Failed to parse AI response"}

            data = json.loads(json_match.group())
        except Exception:
            # Fallback to thread subject
            data = {"action_type": "follow_up", "description": (thread.subject or "Follow up")[:60]}

        case_id = thread.case_id

        action = AgentAction(
            organization_id=org_id,
            thread_id=thread_id,
            case_id=case_id,
            customer_id=thread.matched_customer_id,
            customer_name=thread.customer_name,
            action_type=data.get("action_type", "follow_up"),
            description=data.get("description", thread.subject or "Follow up")[:60],
            status="open",
            job_path="customer",
            created_by=created_by,
        )
        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)

        return {"action_id": action.id, "description": action.description, "action_type": action.action_type, "case_id": case_id}

    async def draft_estimate_from_thread(self, org_id: str, thread_id: str, created_by: str) -> dict:
        """AI reads conversation and drafts an estimate with line items."""
        thread = (await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Check for existing estimate linked to this thread via a job
        from src.models.invoice import Invoice
        from src.models.job_invoice import JobInvoice
        existing = (await self.db.execute(
            select(Invoice)
            .join(JobInvoice, JobInvoice.invoice_id == Invoice.id)
            .join(AgentAction, AgentAction.id == JobInvoice.action_id)
            .where(
                AgentAction.thread_id == thread_id,
                Invoice.document_type == "estimate",
            )
        )).scalar_one_or_none()
        if existing:
            return {
                "invoice_id": existing.id,
                "invoice_number": existing.invoice_number,
                "subject": existing.subject,
                "total": float(existing.total or 0),
                "line_items": [],
                "existing": True,
            }

        msgs = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id).order_by(AgentMessage.received_at)
        )).scalars().all()

        convo = ""
        for m in msgs:
            who = "Client" if m.direction == "inbound" else "Us"
            convo += f"\n[{who}]: {(m.body or '')[:300]}"

        # Get org billing rate
        from src.models.org_cost_settings import OrgCostSettings
        settings_result = await self.db.execute(
            select(OrgCostSettings).where(OrgCostSettings.organization_id == org_id)
        )
        settings = settings_result.scalar_one_or_none()
        labor_rate = settings.billable_labor_rate if settings and hasattr(settings, "billable_labor_rate") else 125.0

        prompt = f"""You are a pool service estimator. Read this conversation and create estimate line items.

Conversation with {thread.customer_name or thread.contact_email}:
Subject: {thread.subject}
{convo}

Create line items for an estimate. Include labor, parts, and materials as separate line items.
Labor rate: ${labor_rate:.2f}/hour. Use this exact rate for all labor line items.
Parts pricing: use realistic market prices for pool equipment and parts.

Respond with JSON:
{{"subject": "short estimate title", "line_items": [{{"description": "what", "quantity": 1, "unit_price": 100.00}}]}}

Rules:
- Subject: short description of the work. NEVER include pricing language like "Price TBD", "TBD", "TBA", or dollar amounts in the subject.
- Descriptions: professional, no addresses, no customer names in line items.
- Every line item MUST have a real price. If unsure, use a reasonable market estimate. Never use $0 or placeholder pricing."""

        try:
            client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
            response = await client.messages.create(
                model=await get_model("fast"),
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
            if not json_match:
                return {"error": "ai_failed", "detail": "Failed to parse AI response"}

            data = json.loads(json_match.group())
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

        # Create the estimate via InvoiceService
        from src.services.invoice_service import InvoiceService

        line_items = data.get("line_items", [])
        if not line_items:
            return {"error": "no_items", "detail": "AI could not extract line items from conversation"}

        inv_svc = InvoiceService(self.db)
        invoice = await inv_svc.create(
            org_id,
            customer_id=thread.matched_customer_id,
            line_items_data=[{
                "description": li.get("description", "Service"),
                "quantity": li.get("quantity", 1),
                "unit_price": li.get("unit_price", 0),
            } for li in line_items],
            document_type="estimate",
            subject=data.get("subject", thread.subject or "Service Estimate"),
            issue_date=date_type.today(),
            status="draft",
        )

        # Find best job to link: thread match first, then customer match
        from src.services.job_invoice_service import link_job_invoice

        existing_job = None
        # 1. Try thread-linked jobs
        thread_jobs = (await self.db.execute(
            select(AgentAction).where(
                AgentAction.thread_id == thread_id,
                AgentAction.organization_id == org_id,
                AgentAction.status.in_(("open", "in_progress", "pending_approval")),
            )
        )).scalars().all()
        if thread_jobs:
            # Prefer repair/site_visit over follow_up/bid
            preferred = [j for j in thread_jobs if j.action_type in ("repair", "site_visit")]
            existing_job = preferred[0] if preferred else thread_jobs[0]

        # 2. Fall back to customer-matched open jobs (for manually-created jobs)
        if not existing_job and thread.matched_customer_id:
            cust_jobs = (await self.db.execute(
                select(AgentAction).where(
                    AgentAction.organization_id == org_id,
                    AgentAction.customer_id == thread.matched_customer_id,
                    AgentAction.status.in_(("open", "in_progress", "pending_approval")),
                ).order_by(desc(AgentAction.created_at))
            )).scalars().all()
            if cust_jobs:
                preferred = [j for j in cust_jobs if j.action_type in ("repair", "site_visit")]
                existing_job = preferred[0] if preferred else cust_jobs[0]

        if existing_job:
            await link_job_invoice(self.db, existing_job.id, invoice.id, linked_by=created_by)
        else:
            job = AgentAction(
                organization_id=org_id,
                thread_id=thread_id,
                customer_id=thread.matched_customer_id,
                customer_name=thread.customer_name,
                action_type="bid",
                description=data.get("subject", thread.subject or "Service Estimate")[:60],
                status="open",
                job_path="customer",
                created_by=created_by,
            )
            self.db.add(job)
            await self.db.flush()
            await link_job_invoice(self.db, job.id, invoice.id, linked_by=created_by)

        await self.db.commit()

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subject": invoice.subject,
            "total": float(invoice.total or 0),
            "line_items": [{
                "description": li.get("description"),
                "quantity": li.get("quantity"),
                "unit_price": li.get("unit_price"),
            } for li in line_items],
        }
