"""InboxSummarizerService — Phase 3 agent.

Reads an AgentThread + messages + related state, calls Claude Haiku
to produce a structured summary + zero-or-more staged proposals.
Caches the summary payload on agent_threads.ai_summary_*.

Designed to be side-effect-clean: a failing run emits `agent.error`
and `thread.summarized` (with error field), leaves the existing
cached payload intact, and returns. The trigger layer will retry.

Trigger paths:
- Inbound-message hook sets ai_summary_debounce_until = NOW() + 30s
  on the thread. The APScheduler sweep (Step 4) picks up ready rows
  and calls this service.
- Stale-sweep job reruns threads with ai_summary_generated_at > 7 days.

See docs/ai-platform-phase-3.md §4-§6.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.invoice import Invoice
from src.models.service_case import ServiceCase
from src.services.agent_learning_service import (
    AGENT_INBOX_SUMMARIZER,
    AgentLearningService,
)
from src.services.events.actor_factory import actor_agent
from src.services.events.platform_event_service import PlatformEventService
from src.services.proposals import ProposalService

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SUMMARY_SCHEMA_VERSION = 1
# Threads shorter than this (character count of all inbound+outbound
# body text combined) skip summarization — a "thanks!" reply doesn't
# need a triage card.
SHORT_THREAD_CHAR_THRESHOLD = 500
SHORT_THREAD_MSG_THRESHOLD = 2
# Summaries with confidence below this are treated as "not useful enough"
# and the cached payload is left null (frontend falls back to snippet).
CONFIDENCE_FLOOR = 0.4


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class _LinkedRef(BaseModel):
    type: str  # "customer" | "case" | "invoice" | "job"
    id: str
    # Display helpers — surface in the card without a round trip
    label: Optional[str] = None  # e.g. case_number "SC-25-0042"


class _ProposalDraft(BaseModel):
    """Shape the model returns inline. We validate here, then stage via
    ProposalService (which runs its own entity-type schema validation)."""
    entity_type: str
    payload: dict


class InboxSummary(BaseModel):
    version: int = SUMMARY_SCHEMA_VERSION
    ask: Optional[str] = None
    # state is optional now — bullets are primary, state is only populated
    # when no bullets exist (informational-only threads).
    state: Optional[str] = None
    open_items: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    linked_refs: list[_LinkedRef] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    # These aren't sent BY the model — they get populated by the service
    # after proposals are staged.
    proposal_ids: list[str] = Field(default_factory=list)

    @field_validator("state")
    @classmethod
    def _state_trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


# Helper for deciding whether to skip a thread based on size.
def _is_short_thread(messages: list[AgentMessage]) -> bool:
    if len(messages) < SHORT_THREAD_MSG_THRESHOLD:
        return True
    total_chars = sum(len(m.body or "") for m in messages)
    return total_chars < SHORT_THREAD_CHAR_THRESHOLD


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class InboxSummarizerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summarize_thread(self, thread_id: str) -> Optional[InboxSummary]:
        """Produce + cache a summary for the given thread.

        Returns the InboxSummary on success, None if the thread was
        skipped (too short, org opt-out, no messages).
        """
        thread = await self.db.get(AgentThread, thread_id)
        if not thread:
            logger.warning("summarize_thread: thread %s not found", thread_id)
            return None

        # Load messages newest-first but send oldest-first in the prompt.
        messages = (await self.db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id)
            .order_by(AgentMessage.received_at)
        )).scalars().all()

        if not messages:
            return None

        if _is_short_thread(messages):
            # Explicitly clear any prior stale cache + mark the sweep done.
            thread.ai_summary_payload = None
            thread.ai_summary_generated_at = datetime.now(timezone.utc)
            thread.ai_summary_debounce_until = None
            await self.db.flush()
            await self._emit_summarized(thread, skipped_reason="short_thread")
            return None

        # Gather related state for the prompt.
        customer, open_cases, open_invoices = await self._load_context(thread)

        prompt = await self._build_prompt(
            thread=thread, messages=messages,
            customer=customer, open_cases=open_cases,
            open_invoices=open_invoices,
        )

        # Call Claude. Any exception → fail-soft, leave prior cache intact.
        try:
            raw = await self._call_model(prompt)
            summary = self._parse_and_validate(raw)
        except Exception as e:  # noqa: BLE001
            logger.error(
                "summarize_thread failed for %s: %s", thread_id, e,
            )
            await self._emit_error(thread, str(e)[:200])
            return None

        # Stage any proposals the model suggested inline.
        proposal_drafts = self._extract_proposals(raw)
        proposal_ids = await self._stage_proposals(thread, proposal_drafts)
        summary.proposal_ids = proposal_ids

        # Below-confidence → don't cache; no summary is better than a
        # hedged one. Still emit thread.summarized so Sonar sees it ran.
        if summary.confidence < CONFIDENCE_FLOOR:
            thread.ai_summary_payload = None
            thread.ai_summary_generated_at = datetime.now(timezone.utc)
            thread.ai_summary_debounce_until = None
            await self.db.flush()
            await self._emit_summarized(
                thread, skipped_reason="low_confidence",
                confidence=summary.confidence,
            )
            return None

        # Cache on the thread row.
        thread.ai_summary_payload = summary.model_dump(mode="json")
        thread.ai_summary_generated_at = datetime.now(timezone.utc)
        thread.ai_summary_version = SUMMARY_SCHEMA_VERSION
        thread.ai_summary_debounce_until = None
        await self.db.flush()

        await self._emit_summarized(
            thread,
            confidence=summary.confidence,
            proposals_staged=len(proposal_ids),
        )
        return summary

    # -------------------------------------------------------------------
    # Prompt construction
    # -------------------------------------------------------------------

    async def _load_context(
        self, thread: AgentThread,
    ) -> tuple[Optional[Customer], list[ServiceCase], list[Invoice]]:
        customer = None
        if thread.matched_customer_id:
            customer = await self.db.get(Customer, thread.matched_customer_id)

        open_cases: list[ServiceCase] = []
        open_invoices: list[Invoice] = []
        if customer:
            open_cases = (await self.db.execute(
                select(ServiceCase).where(
                    ServiceCase.organization_id == thread.organization_id,
                    ServiceCase.customer_id == customer.id,
                    ServiceCase.status.not_in(["closed", "cancelled"]),
                ).order_by(desc(ServiceCase.updated_at)).limit(5)
            )).scalars().all()
            open_invoices = (await self.db.execute(
                select(Invoice).where(
                    Invoice.organization_id == thread.organization_id,
                    Invoice.customer_id == customer.id,
                    Invoice.status.in_(["sent", "viewed", "overdue"]),
                ).order_by(desc(Invoice.created_at)).limit(5)
            )).scalars().all()
        return customer, list(open_cases), list(open_invoices)

    async def _build_prompt(
        self,
        *,
        thread: AgentThread,
        messages: list[AgentMessage],
        customer: Optional[Customer],
        open_cases: list[ServiceCase],
        open_invoices: list[Invoice],
    ) -> str:
        convo_lines = []
        for m in messages:
            who = "Client" if m.direction == "inbound" else "Us"
            body = (m.body or "")[:800]
            convo_lines.append(f"[{who} @ {m.received_at.isoformat() if m.received_at else '?'}]\n{body}")
        convo = "\n---\n".join(convo_lines)

        cust_name = customer.display_name if customer else (thread.customer_name or thread.contact_email or "unknown")

        cases_line = "(none)"
        if open_cases:
            cases_line = ", ".join(
                f"{c.case_number}: {c.title[:50]} ({c.status})"
                for c in open_cases
            )
        invoices_line = "(none)"
        if open_invoices:
            invoices_line = ", ".join(
                f"{i.invoice_number or 'draft'}: ${(i.balance or 0):.0f} balance, {i.status}"
                for i in open_invoices
            )

        lessons = ""
        try:
            learner = AgentLearningService(self.db)
            lessons_block = await learner.build_lessons_prompt(
                thread.organization_id, AGENT_INBOX_SUMMARIZER,
                category=thread.category,
                customer_id=thread.matched_customer_id,
            )
            if lessons_block:
                lessons = f"\n\nLessons from prior corrections:\n{lessons_block}"
        except Exception:
            pass  # learning is non-blocking

        return f"""You are summarizing a pool service email thread for the business owner.
Output a single JSON object. No prose before or after. Schema:
{{
  "version": 1,
  "ask": "<one sentence what the customer wants, or null>",
  "state": "<one sentence what we need to do next; never null>",
  "open_items": ["short imperative phrase", ...],
  "red_flags": ["urgency, complaint, legal, 3rd escalation"],
  "linked_refs": [{{"type": "case", "id": "...", "label": "SC-25-..."}}, ...],
  "confidence": 0.0-1.0,
  "proposals": [
    {{"entity_type": "job" | "estimate" | "case_link", "payload": {{...}}}}
  ]
}}

Thread:
- Customer: {cust_name}
- Subject: {thread.subject or '(no subject)'}
- Category: {thread.category or 'uncategorized'}
- Message count: {len(messages)}

Conversation (oldest → newest):
{convo}

Related state for this customer:
- Open cases: {cases_line}
- Outstanding invoices: {invoices_line}

Rules:
- The UI ALREADY shows: customer name, contact person, and property
  address. NEVER repeat these in any summary field. The customer's name
  is redundant; the address is redundant. Writing "Marty Reed approved
  filter cleaning at 7210 Crocker Road" is WRONG — write "Filter
  cleaning — Approved" instead.
- `ask`: null unless the customer is posing a direct question we owe an
  answer on. Null if they're approving, declining, informing, or thanking.
- `state`: null in most cases. Only populate when the thread has no
  discrete items to enumerate (e.g. a single informational reply with
  nothing actionable). Short fragment, no name/address.
- `open_items` is the PRIMARY display field. 3-5 terse bullets in
  `<thing> — <status/action>` form. Each bullet ≤ 55 chars. No person
  names, no addresses, no fluff. One concept per bullet.
  Good examples (follow this form):
    "Filter cleaning — Approved"
    "Pool sweep tail — Approved"
    "$450 heater quote — Declined; wants cheaper"
    "Invoice 4412 — Paid in full"
    "Pump quote — Follow up (6 days silent)"
    "SDS sheet — Resend (delivery failed)"
    "LED fixture type — Awaiting confirmation"
  Bad examples (never do this):
    "Marty Reed approved filter cleaning" (repeats customer name)
    "Filter cleaning at 7210 Crocker Rd" (repeats address)
    "Approved" (too vague — what was approved?)
    "Yes" (raw quote)
    "Customer responded with thanks" (no info)
- `red_flags`: reserved for GENUINE escalation signals ONLY. Examples that
  qualify: explicit legal/attorney/lawsuit mention; threats of chargeback,
  BBB, or public review; a third+ escalation or repeated ignored contact;
  material lost-revenue or safety risk (liability, injury, equipment damage);
  hostile/abusive language; demand for refund beyond routine dispute.
  Examples that DO NOT qualify and must go to open_items: overdue balance,
  AR follow-up, customer waiting on a reply, missed appointment, late quote,
  mild frustration. Empty list is the common case — err toward empty.
- `proposals`: stage actions only when clearly warranted by the thread. Otherwise empty.
- `confidence`: your certainty in the summary itself, 0.0-1.0.
{lessons}"""

    # -------------------------------------------------------------------
    # Model invocation + output parsing
    # -------------------------------------------------------------------

    async def _call_model(self, prompt: str) -> str:
        client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
        response = await client.messages.create(
            model=await get_model("fast"),
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def _parse_and_validate(self, raw: str) -> InboxSummary:
        # Strip fences if the model wraps the JSON.
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(json)?|```$", "", clean, flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            raise ValueError("no JSON object in model output")
        obj = json.loads(match.group())
        # Pydantic validates shape + required fields. Discard `proposals`
        # at this layer — it's staged separately.
        obj.pop("proposals", None)
        return InboxSummary.model_validate(obj)

    def _extract_proposals(self, raw: str) -> list[_ProposalDraft]:
        try:
            match = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
            if not match:
                return []
            obj = json.loads(match.group())
            drafts = obj.get("proposals", []) or []
            return [_ProposalDraft.model_validate(d) for d in drafts if isinstance(d, dict)]
        except (json.JSONDecodeError, ValidationError, ValueError):
            return []

    async def _stage_proposals(
        self, thread: AgentThread, drafts: list[_ProposalDraft],
    ) -> list[str]:
        """Stage each draft via ProposalService. Failures don't block
        the summary cache — a bad proposal shape just doesn't get staged."""
        service = ProposalService(self.db)
        staged: list[str] = []
        for d in drafts:
            try:
                p = await service.stage(
                    org_id=thread.organization_id,
                    agent_type=AGENT_INBOX_SUMMARIZER,
                    entity_type=d.entity_type,
                    source_type="agent_thread",
                    source_id=thread.id,
                    proposed_payload=d.payload,
                )
                staged.append(p.id)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "inbox_summarizer: stage failed for entity_type=%s: %s",
                    d.entity_type, e,
                )
        return staged

    # -------------------------------------------------------------------
    # Event emission
    # -------------------------------------------------------------------

    async def _emit_summarized(
        self,
        thread: AgentThread,
        *,
        confidence: Optional[float] = None,
        proposals_staged: int = 0,
        skipped_reason: Optional[str] = None,
    ) -> None:
        payload = {
            "tokens_in": None,  # populated later when we wire model-usage tracking
            "tokens_out": None,
            "duration_ms": None,
            "confidence": confidence,
            "proposals_staged": proposals_staged,
        }
        if skipped_reason:
            payload["skipped_reason"] = skipped_reason
        await PlatformEventService.emit(
            db=self.db,
            event_type="thread.summarized",
            level="agent_action",
            actor=actor_agent(AGENT_INBOX_SUMMARIZER),
            organization_id=thread.organization_id,
            entity_refs={"thread_id": thread.id},
            payload=payload,
        )

    async def _emit_error(self, thread: AgentThread, error_msg: str) -> None:
        await PlatformEventService.emit(
            db=self.db,
            event_type="agent.error",
            level="error",
            actor=actor_agent(AGENT_INBOX_SUMMARIZER),
            organization_id=thread.organization_id,
            entity_refs={"thread_id": thread.id},
            payload={
                "agent_type": AGENT_INBOX_SUMMARIZER,
                "error_class": "SummarizeFailed",
                "short_error": error_msg,
            },
        )
