"""Proposal creator: `case_link` entity_type.

Used by Phase 3's inbox_summarizer agent to propose "this thread
belongs to existing case X" — linking without creating a new case.
Delegates to `ServiceCaseService.set_entity_case`, the canonical
entity-linking path.

Idempotent: if the thread is already linked to the target case,
set_entity_case returns the no-op transition and the proposal resolves
as `accepted` without double-linking. This makes re-accepting a
superseded proposal safe.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register
from src.services.service_case_service import ServiceCaseService


class CaseLinkProposalPayload(BaseModel):
    """Link a specific source entity to a specific case.

    Phase 3 primarily uses entity_type='thread' (link an AgentThread to
    a ServiceCase). Future summarizers could propose linking other
    LINKABLE_MODELS (jobs, invoices, etc.) via this same creator.
    """

    entity_type: str  # "thread" | "job" | "invoice" | "internal_thread" | "deepblue_conversation"
    entity_id: str
    case_id: str


@register("case_link", schema=CaseLinkProposalPayload, outcome_entity_type="service_case")
async def create_case_link_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    # set_entity_case handles org-scoping, count refresh, and activity
    # logging. Returns a dict describing the transition.
    svc = ServiceCaseService(db)
    user_name = None  # actor-based; svc handles activity-log attribution
    transition = await svc.set_entity_case(
        org_id=org_id,
        entity_type=payload["entity_type"],
        entity_id=payload["entity_id"],
        new_case_id=payload["case_id"],
        user_name=user_name,
    )
    # Give ProposalService.accept something with a `.id` so outcome
    # stamping works. The linked case_id is the most useful pointer.
    return _LinkResult(id=payload["case_id"], transition=transition)


class _LinkResult:
    """Lightweight return shape — ProposalService reads .id."""
    __slots__ = ("id", "transition")

    def __init__(self, id: str, transition: dict):
        self.id = id
        self.transition = transition
