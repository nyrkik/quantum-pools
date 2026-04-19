"""Proposal creator: `case` entity_type.

Used by DeepBlue's `create_case` tool. Delegates to
`ServiceCaseService.create` — the canonical case-creation path that
generates the case_number, emits case.created, and stamps manager_user_id
from the actor.

Extra work that the old `/confirm-create-case` endpoint did (linking
the conversation + existing email threads to the new case) remains in
the endpoint — those are post-creation side effects specific to
DeepBlue's conversation model, not inherent to the proposal.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register
from src.services.service_case_service import ServiceCaseService


class CaseProposalPayload(BaseModel):
    """Fields a proposal can commit to a service case."""

    title: str
    customer_id: Optional[str] = None
    billing_name: Optional[str] = None
    priority: str = "normal"
    source: str = "deepblue"


@register("case", schema=CaseProposalPayload)
async def create_case_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    return await ServiceCaseService(db).create(
        org_id=org_id,
        actor=actor,
        title=payload["title"],
        source=payload.get("source", "deepblue"),
        customer_id=payload.get("customer_id"),
        billing_name=payload.get("billing_name"),
        priority=payload.get("priority", "normal"),
        # manager_user_id auto-derives from actor inside ServiceCaseService.create
    )
