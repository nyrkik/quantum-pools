"""Proposal creator: `job` entity_type.

Delegates to `AgentActionService.add_job()` — the canonical
job-creation path. All fields the payload can carry correspond to
fields `add_job()` accepts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.agent_action_service import AgentActionService
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


class JobProposalPayload(BaseModel):
    """Fields a proposal can commit to a job. Matches AgentActionService.add_job()
    signature, minus plumbing args the service provides (org_id, actor)."""

    action_type: str = Field(
        ...,
        description="One of: repair, follow_up, bid, site_visit, callback, "
                    "schedule_change, equipment, other",
    )
    description: str = Field(..., max_length=80, description="8-word verb+what+location")
    case_id: Optional[str] = None
    thread_id: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    property_address: Optional[str] = None
    notes: Optional[str] = None
    job_path: str = Field(default="internal", description="internal | customer")


@register("job", schema=JobProposalPayload)
async def create_job_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    """Runs in the caller's (ProposalService.accept) transaction. If
    this raises, the proposal stays `staged` via rollback."""
    return await AgentActionService(db).add_job(
        org_id=org_id,
        actor=actor,
        source="proposal_accepted",
        action_type=payload["action_type"],
        description=payload["description"],
        case_id=payload.get("case_id"),
        thread_id=payload.get("thread_id"),
        customer_id=payload.get("customer_id"),
        customer_name=payload.get("customer_name"),
        assigned_to=payload.get("assigned_to"),
        due_date=payload.get("due_date"),
        property_address=payload.get("property_address"),
        notes=payload.get("notes"),
        job_path=payload.get("job_path", "internal"),
    )
