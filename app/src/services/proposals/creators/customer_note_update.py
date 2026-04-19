"""Proposal creator: `customer_note_update` entity_type.

Appends text to an existing Customer.notes field. Not a "new entity"
creator in the strict sense — modifies an existing row — but fits the
proposal pattern cleanly: user reviews the proposed append, accepts
or rejects.

Emits `customer.edited` so Sonar can see the change with fields_changed=["notes"]
per taxonomy §8.* conventions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.customer import Customer
from src.services.events.actor_factory import actor_system
from src.services.events.platform_event_service import Actor, PlatformEventService
from src.services.proposals.registry import register


class CustomerNoteUpdatePayload(BaseModel):
    """Fields a proposal can commit to a customer_note_update."""

    customer_id: str
    note_text: str = Field(..., min_length=1, max_length=4000)


@register("customer_note_update", schema=CustomerNoteUpdatePayload)
async def create_customer_note_update_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    cust = (await db.execute(
        select(Customer).where(
            Customer.id == payload["customer_id"],
            Customer.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if cust is None:
        raise NotFoundError(
            f"Customer {payload['customer_id']} not found in org {org_id}"
        )

    current = cust.notes or ""
    cust.notes = (current + "\n\n" + payload["note_text"]).strip() if current else payload["note_text"]
    await db.flush()

    await PlatformEventService.emit(
        db=db,
        event_type="customer.edited",
        level=("user_action" if actor and actor.actor_type == "user"
               else "agent_action" if actor and actor.actor_type == "agent"
               else "system_action"),
        actor=actor or actor_system(),
        organization_id=org_id,
        entity_refs={"customer_id": cust.id},
        payload={"fields_changed": ["notes"], "source": "proposal_accepted"},
    )
    return cust
