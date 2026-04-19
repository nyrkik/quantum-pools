"""DeepBlue tools — Service Narrator / Communication domain."""

import logging

from sqlalchemy import select

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_broadcast(inp: dict, ctx: ToolContext) -> dict:
    """Stage a broadcast_email proposal. Phase 2 Step 9 migration."""
    from src.services.broadcast_service import BroadcastService
    from src.services.proposals import ProposalService
    from src.models.customer import Customer

    subject = inp.get("subject", "")
    body = inp.get("body", "")
    filter_type = inp.get("filter_type", "all_active")
    customer_ids = inp.get("customer_ids") or []
    test_recipient = inp.get("test_recipient")

    if not subject or not body:
        return {"error": "Subject and body are required."}

    async def _stage(payload: dict, preview_extras: dict) -> dict:
        try:
            proposal = await ProposalService(ctx.db).stage(
                org_id=ctx.org_id,
                agent_type="deepblue_responder",
                entity_type="broadcast_email",
                source_type="deepblue_conversation",
                source_id=getattr(ctx, "conversation_id", None),
                proposed_payload=payload,
            )
            await ctx.db.commit()
        except Exception as e:  # noqa: BLE001
            return {"error": f"Could not stage broadcast proposal: {e}"}
        return {
            "action": "broadcast_email",
            "proposal_id": proposal.id,
            "preview": {
                "subject": subject,
                "body": body,
                "filter_type": filter_type,
                **preview_extras,
                "proposal_id": proposal.id,
            },
        }

    # Test send — single recipient
    if filter_type == "test":
        return await _stage(
            payload={
                "subject": subject, "body": body,
                "filter_type": "test", "test_recipient": test_recipient,
            },
            preview_extras={
                "filter_label": f"Test send to {test_recipient or 'your email'}",
                "test_recipient": test_recipient,
                "recipient_count": 1,
                "customer_names": [test_recipient or "you"],
            },
        )

    # Custom list
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
        return await _stage(
            payload={
                "subject": subject, "body": body,
                "filter_type": "custom",
                "customer_ids": [c.id for c in customers],
            },
            preview_extras={
                "filter_label": f"{len(customers)} selected customer{'s' if len(customers) != 1 else ''}",
                "customer_ids": [c.id for c in customers],
                "customer_names": names,
                "recipient_count": len(customers),
            },
        )

    # Standard segment filter (all_active / commercial / residential)
    svc = BroadcastService(ctx.db)
    count = await svc.get_recipient_count(ctx.org_id, filter_type)
    filter_labels = {
        "all_active": "all active customers",
        "commercial": "commercial customers",
        "residential": "residential customers",
    }
    return await _stage(
        payload={"subject": subject, "body": body, "filter_type": filter_type},
        preview_extras={
            "filter_label": filter_labels.get(filter_type, filter_type),
            "recipient_count": count,
        },
    )


async def _exec_draft_customer_email(inp: dict, ctx: ToolContext) -> dict:
    """Stage a customer_email proposal. Phase 2 Step 9 migration."""
    from src.models.customer import Customer
    from src.services.proposals import ProposalService

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

    try:
        proposal = await ProposalService(ctx.db).stage(
            org_id=ctx.org_id,
            agent_type="deepblue_responder",
            entity_type="customer_email",
            source_type="deepblue_conversation",
            source_id=getattr(ctx, "conversation_id", None),
            proposed_payload={
                "customer_id": customer_id,
                "subject": subject,
                "body": body,
            },
        )
        await ctx.db.commit()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not stage customer-email proposal: {e}"}

    return {
        "proposal_id": proposal.id,
        "preview": {
            "type": "customer_email",
            "subject": subject,
            "body": body,
            "customer_id": customer_id,
            "customer_name": customer.display_name,
            "to_email": email,
            "proposal_id": proposal.id,
        },
    }


EXECUTORS = {
    "draft_broadcast_email": _exec_broadcast,
    "draft_customer_email": _exec_draft_customer_email,
}
