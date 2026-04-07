"""DeepBlue tools — Service Narrator / Communication domain."""

import logging

from sqlalchemy import select

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_broadcast(inp: dict, ctx: ToolContext) -> dict:
    """Draft a broadcast email — returns preview. Does NOT send yet."""
    from src.services.broadcast_service import BroadcastService
    from src.models.customer import Customer

    subject = inp.get("subject", "")
    body = inp.get("body", "")
    filter_type = inp.get("filter_type", "all_active")
    customer_ids = inp.get("customer_ids") or []
    test_recipient = inp.get("test_recipient")

    if not subject or not body:
        return {"error": "Subject and body are required."}

    # Test send — single recipient preview
    if filter_type == "test":
        return {
            "action": "broadcast_email",
            "requires_confirmation": True,
            "preview": {
                "subject": subject,
                "body": body,
                "filter_type": "test",
                "filter_label": f"Test send to {test_recipient or 'your email'}",
                "test_recipient": test_recipient,
                "recipient_count": 1,
                "customer_names": [test_recipient or "you"],
            },
        }

    # Custom list — validate and resolve names
    if filter_type == "custom":
        if not customer_ids:
            return {"error": "customer_ids required when filter_type is 'custom'"}
        customers = (await ctx.db.execute(
            select(Customer).where(
                Customer.id.in_(customer_ids),
                Customer.organization_id == ctx.org_id,
                Customer.is_active == True,
            )
        )).scalars().all()
        names = [c.display_name for c in customers]
        return {
            "action": "broadcast_email",
            "requires_confirmation": True,
            "preview": {
                "subject": subject,
                "body": body,
                "filter_type": "custom",
                "filter_label": f"{len(customers)} selected customer{'s' if len(customers) != 1 else ''}",
                "customer_ids": [c.id for c in customers],
                "customer_names": names,
                "recipient_count": len(customers),
            },
        }

    # Standard segment filters
    svc = BroadcastService(ctx.db)
    count = await svc.get_recipient_count(ctx.org_id, filter_type)

    filter_labels = {
        "all_active": "all active customers",
        "commercial": "commercial customers",
        "residential": "residential customers",
    }

    return {
        "action": "broadcast_email",
        "requires_confirmation": True,
        "preview": {
            "subject": subject,
            "body": body,
            "filter_type": filter_type,
            "filter_label": filter_labels.get(filter_type, filter_type),
            "recipient_count": count,
        },
    }


async def _exec_draft_customer_email(inp: dict, ctx: ToolContext) -> dict:
    """Draft an email to a specific customer for review."""
    from src.models.customer import Customer

    subject = inp.get("subject", "").strip()
    body = inp.get("body", "").strip()
    if not subject or not body:
        return {"error": "Subject and body are required."}

    customer_id = inp.get("customer_id") or ctx.customer_id
    if not customer_id:
        return {"error": "No customer in context. Navigate to a customer or case first."}

    customer = (await ctx.db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == ctx.org_id)
    )).scalar_one_or_none()
    if not customer:
        return {"error": "Customer not found."}

    email = customer.email
    if not email:
        return {"error": f"{customer.display_name} has no email address on file."}

    return {
        "requires_confirmation": True,
        "preview": {
            "type": "customer_email",
            "subject": subject,
            "body": body,
            "customer_id": customer_id,
            "customer_name": customer.display_name,
            "to_email": email,
        },
    }


EXECUTORS = {
    "draft_broadcast_email": _exec_broadcast,
    "draft_customer_email": _exec_draft_customer_email,
}
