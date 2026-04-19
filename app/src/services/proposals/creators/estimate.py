"""Proposal creator: `estimate` entity_type.

Delegates to `InvoiceService.create(document_type="estimate")` — the
canonical invoice/estimate creation path.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor
from src.services.invoice_service import InvoiceService
from src.services.proposals.registry import register


class EstimateLineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    is_taxed: bool = False
    service_id: Optional[str] = None


class EstimateProposalPayload(BaseModel):
    """Fields a proposal can commit to an estimate.

    `customer_id` is optional ONLY when `billing_name` is provided
    (one-off / non-DB customer). `line_items` must be non-empty — a
    $0 estimate has no useful meaning.
    """

    customer_id: Optional[str] = None
    billing_name: Optional[str] = None
    subject: Optional[str] = None
    notes: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    case_id: Optional[str] = None
    line_items: list[EstimateLineItem] = Field(..., min_length=1)


@register("estimate", schema=EstimateProposalPayload)
async def create_estimate_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    """Runs in ProposalService.accept's transaction."""
    from datetime import date as _date
    return await InvoiceService(db).create(
        org_id=org_id,
        customer_id=payload.get("customer_id"),
        actor=actor,
        source="proposal_accepted",
        line_items_data=payload["line_items"],
        document_type="estimate",
        subject=payload.get("subject"),
        notes=payload.get("notes"),
        issue_date=payload.get("issue_date") or _date.today(),
        due_date=payload.get("due_date"),
        case_id=payload.get("case_id"),
        billing_name=payload.get("billing_name"),
    )
