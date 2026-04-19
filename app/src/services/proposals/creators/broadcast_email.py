"""Proposal creator: `broadcast_email` entity_type.

Used by DeepBlue's `draft_broadcast_email` tool. Delegates to
`BroadcastService.create_broadcast` which handles recipient resolution,
AgentMessage creation, and async send.

The ProposalCard for this entity_type (frontend) displays recipient
count + subject prominently and labels the action button "Send to {N}
customers" so the commit is informed-consent at click-time (spec §14.4).

Atomicity note: BroadcastService.create_broadcast internally commits
between broadcast-row insert and the per-customer send loop, so the
"accept proposal + send broadcast" transaction is not strictly atomic.
If a send fails mid-loop, the proposal is still marked accepted (the
USER's decision-commitment moment was the click). BroadcastService's
own sent/failed counters track per-recipient outcomes for visibility.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.broadcast_service import BroadcastService
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


class BroadcastEmailProposalPayload(BaseModel):
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    filter_type: str = Field(..., description="all_active | commercial | residential | custom | test")
    customer_ids: Optional[list[str]] = None  # required when filter_type='custom'
    test_recipient: Optional[str] = None       # required when filter_type='test'


@register("broadcast_email", schema=BroadcastEmailProposalPayload)
async def create_broadcast_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    created_by = (
        f"user:{actor.user_id}" if actor and actor.actor_type == "user" and actor.user_id
        else "proposal_accepted"
    )
    # filter_data carries customer_ids (comma-joined) for 'custom' or test email for 'test'
    filter_data = None
    if payload["filter_type"] == "custom" and payload.get("customer_ids"):
        filter_data = ",".join(payload["customer_ids"])
    return await BroadcastService(db).create_broadcast(
        org_id=org_id,
        subject=payload["subject"],
        body=payload["body"],
        filter_type=payload["filter_type"],
        filter_data=filter_data,
        created_by=created_by,
        test_recipient=payload.get("test_recipient"),
    )
