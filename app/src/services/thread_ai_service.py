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

        # Inject lessons from prior corrections (DNA rule: every agent learns).
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

        # Inject lessons from prior corrections (DNA rule: every agent learns).
        try:
            from src.services.agent_learning_service import AgentLearningService, AGENT_JOB_EVALUATOR
            learner = AgentLearningService(self.db)
            lessons = await learner.build_lessons_prompt(
                org_id, AGENT_JOB_EVALUATOR,
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

        from src.services.agent_action_service import AgentActionService
        from src.services.events.actor_factory import actor_agent
        action = await AgentActionService(self.db).add_job(
            org_id=org_id,
            action_type=data.get("action_type", "follow_up"),
            description=data.get("description", thread.subject or "Follow up")[:60],
            source="thread_ai",
            actor=actor_agent("email_drafter"),
            case_id=case_id,
            thread_id=thread_id,
            customer_id=thread.matched_customer_id,
            customer_name=thread.customer_name,
            job_path="customer",
            created_by=created_by,
        )

        await self.db.commit()
        await self.db.refresh(action)

        return {"action_id": action.id, "description": action.description, "action_type": action.action_type, "case_id": case_id}

    async def draft_estimate_from_thread(self, org_id: str, thread_id: str, created_by: str) -> dict:
        """AI reads conversation and drafts an estimate — staged as a proposal.

        Phase 5 migration: drafting stages an `estimate` proposal via
        `ProposalService.stage`. The Invoice row (and job link) only
        materialize when a human accepts via `POST /v1/proposals/{id}/accept`.
        DNA rule 5 — AI never commits to the customer — is enforced by
        the proposal boundary.
        """
        thread = (await self.db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == org_id)
        )).scalar_one_or_none()
        if not thread:
            return {"error": "not_found", "detail": "Thread not found"}

        # Short-circuit: if an estimate is already linked to this thread via a job, return it.
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

        # Also short-circuit if a staged estimate proposal already exists for this thread.
        from src.models.agent_proposal import AgentProposal, STATUS_STAGED
        existing_proposal = (await self.db.execute(
            select(AgentProposal).where(
                AgentProposal.organization_id == org_id,
                AgentProposal.entity_type == "estimate",
                AgentProposal.source_type == "thread",
                AgentProposal.source_id == thread_id,
                AgentProposal.status == STATUS_STAGED,
            )
        )).scalar_one_or_none()
        if existing_proposal:
            return {
                "proposal_id": existing_proposal.id,
                "status": "staged",
                "subject": existing_proposal.proposed_payload.get("subject"),
                "line_items": existing_proposal.proposed_payload.get("line_items", []),
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

        # Inject lessons from prior corrections (DNA rule: every agent learns).
        try:
            from src.services.agent_learning_service import AgentLearningService, AGENT_ESTIMATE_GENERATOR
            learner = AgentLearningService(self.db)
            lessons = await learner.build_lessons_prompt(
                org_id, AGENT_ESTIMATE_GENERATOR,
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
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
            if not json_match:
                return {"error": "ai_failed", "detail": "Failed to parse AI response"}

            data = json.loads(json_match.group())
        except Exception as e:
            return {"error": "ai_failed", "detail": f"Failed: {str(e)}"}

        line_items = data.get("line_items", [])
        if not line_items:
            return {"error": "no_items", "detail": "AI could not extract line items from conversation"}

        # Stage the estimate as a proposal. The creator handles InvoiceService.create
        # + job-linking inside ProposalService.accept's transaction when a human accepts.
        from src.services.events.actor_factory import actor_agent
        from src.services.proposals import ProposalService

        subject = data.get("subject", thread.subject or "Service Estimate")
        proposal = await ProposalService(self.db).stage(
            org_id=org_id,
            agent_type="estimate_generator",
            entity_type="estimate",
            source_type="thread",
            source_id=thread_id,
            proposed_payload={
                "customer_id": thread.matched_customer_id,
                "thread_id": thread_id,
                "case_id": thread.case_id,
                "subject": subject,
                "issue_date": date_type.today().isoformat(),
                "line_items": [{
                    "description": li.get("description", "Service"),
                    "quantity": li.get("quantity", 1),
                    "unit_price": li.get("unit_price", 0),
                } for li in line_items],
            },
            input_context=f"Drafted by {created_by} from thread {thread.subject!r}",
            actor=actor_agent("estimate_generator"),
        )
        await self.db.commit()

        return {
            "proposal_id": proposal.id,
            "status": "staged",
            "subject": subject,
            "line_items": [{
                "description": li.get("description"),
                "quantity": li.get("quantity"),
                "unit_price": li.get("unit_price"),
            } for li in line_items],
        }
