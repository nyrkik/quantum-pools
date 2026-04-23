"""Proposal creator: `customer_match_suggestion` entity_type.

Used by the Phase 5 customer_matcher migration. The matcher's trusted
methods (email / contact_email / previous_match / sender_name) still
auto-apply — high-confidence matches are deterministic join logic, not
AI commitment. Low-confidence Claude-verified matches go through this
creator instead: stage a proposal, human reviews in `/inbox/matches`.

Accept sets `AgentThread.matched_customer_id` + `customer_name` (display
cache). Reject records the correction so the matcher learns not to
propose this (thread, candidate) pair again.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


class CustomerMatchSuggestionPayload(BaseModel):
    thread_id: str
    candidate_customer_id: str
    # Human-readable reason, e.g. "Claude matched by body mention of 'Coventry Park'"
    reason: str = Field(..., min_length=1, max_length=300)
    # High is never proposed — it auto-applies. Low/medium only.
    confidence: Literal["low", "medium"]
    # Optional: what the matcher found that made it uncertain
    note: Optional[str] = Field(default=None, max_length=1000)


@register("customer_match_suggestion", schema=CustomerMatchSuggestionPayload)
async def create_customer_match_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    """Runs in ProposalService.accept's transaction. Applies the match."""
    cust = (await db.execute(
        select(Customer).where(
            Customer.id == payload["candidate_customer_id"],
            Customer.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if cust is None:
        raise NotFoundError(
            f"Candidate customer {payload['candidate_customer_id']} not in org {org_id}"
        )

    thread = (await db.execute(
        select(AgentThread).where(
            AgentThread.id == payload["thread_id"],
            AgentThread.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if thread is None:
        raise NotFoundError(
            f"Thread {payload['thread_id']} not in org {org_id}"
        )

    thread.matched_customer_id = cust.id
    # Display cache — follow the same pattern as orchestrator's match handler.
    parts = [p for p in (cust.first_name, cust.last_name) if p]
    thread.customer_name = " ".join(parts) if parts else (cust.email or None)
    await db.flush()
    return thread
