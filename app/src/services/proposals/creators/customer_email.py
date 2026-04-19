"""Proposal creator: `customer_email` entity_type.

Used by DeepBlue's `draft_customer_email` tool — one-off email to a
specific customer. Delegates to `EmailService.send_agent_reply` (the
canonical outbound-customer-email path per CLAUDE.md "Single Exit Points").

UX note: the ProposalCard renderer displays the recipient (customer
name + email) prominently; the action button labels as "Send to
{customer name}" so the commit is informed-consent at click-time.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.models.customer import Customer
from src.services.email_service import EmailService
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


class CustomerEmailProposalPayload(BaseModel):
    customer_id: str
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)


@register("customer_email", schema=CustomerEmailProposalPayload)
async def create_customer_email_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    # Verify customer is in this org and has a resolvable recipient.
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
    if not cust.email:
        raise ValidationError(
            f"{cust.display_name} has no email address on file — can't send."
        )

    # Delegate to canonical outbound path so the Postmark/Gmail routing,
    # signature, and from-name logic all apply.
    svc = EmailService(db)
    result = await svc.send_agent_reply(
        org_id=org_id,
        to=cust.email,
        subject=payload["subject"],
        body_text=payload["body"],
        is_new=True,
    )
    return result
