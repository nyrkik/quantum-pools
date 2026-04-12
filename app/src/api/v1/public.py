"""Public endpoints — no authentication required. Token-gated access."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.database import get_db
from src.models.invoice import Invoice, InvoiceLineItem
from src.models.estimate_approval import EstimateApproval
from src.models.agent_action import AgentAction
from src.models.organization import Organization
from src.models.org_cost_settings import OrgCostSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])


class ApproveRequest(BaseModel):
    name: str
    email: str | None = None
    signature: str | None = None
    user_agent: str | None = None
    notes: str | None = None


@router.get("/estimate/{token}")
async def view_estimate(token: str, db: AsyncSession = Depends(get_db)):
    """Public estimate view — customer clicks link from email."""
    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found or link expired")

    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == approval.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Estimate not found")

    org_result = await db.execute(
        select(Organization).where(Organization.id == invoice.organization_id)
    )
    org = org_result.scalar_one_or_none()

    items_result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.invoice_id == invoice.id
        ).order_by(InvoiceLineItem.sort_order)
    )
    items = [
        {
            "description": li.description,
            "quantity": float(li.quantity),
            "unit_price": float(li.unit_price),
            "total": float(li.amount or li.quantity * li.unit_price),
        }
        for li in items_result.scalars().all()
    ]

    customer_name = None
    customer_email = None
    if invoice.customer_id:
        from src.models.customer import Customer
        cust_result = await db.execute(
            select(Customer).where(Customer.id == invoice.customer_id)
        )
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_name = f"{cust.first_name} {cust.last_name}".strip()
            customer_email = cust.email

    # Get org terms settings
    settings_result = await db.execute(
        select(OrgCostSettings).where(OrgCostSettings.organization_id == invoice.organization_id)
    )
    settings = settings_result.scalar_one_or_none()

    if not invoice.viewed_at:
        invoice.viewed_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "estimate_number": invoice.invoice_number,
        "subject": invoice.subject,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "org_name": org.name if org else None,
        "org_logo_url": org.logo_url if org and hasattr(org, "logo_url") else None,
        "org_color": org.brand_color if org and hasattr(org, "brand_color") else None,
        "line_items": items,
        "total": float(invoice.total or 0),
        "recipient_name": approval.recipient_name,
        "terms": {
            "payment_terms_days": settings.payment_terms_days if settings else 30,
            "estimate_validity_days": settings.estimate_validity_days if settings else 30,
            "late_fee_pct": settings.late_fee_pct if settings else 1.5,
            "warranty_days": settings.warranty_days if settings else 30,
            "custom_terms": settings.estimate_terms if settings else None,
        },
        "status": "approved" if approval.approved_by_type and approval.approved_by_type != "pending" else "pending",
        "approved_at": approval.approved_at.isoformat() if approval.approved_by_type and approval.approved_by_type != "pending" else None,
        "approval_evidence": {
            "signed_by": approval.approved_by_name,
            "signature": approval.signature_data,
            "sent_to_email": approval.recipient_email,
            "ip_address": approval.client_ip,
            "method": approval.approval_method,
            "timestamp": approval.approved_at.isoformat() if approval.approved_at else None,
        } if approval.approved_by_type and approval.approved_by_type != "pending" else None,
        "revision_count": invoice.revision_count or 0,
        "revised_at": invoice.revised_at.isoformat() if invoice.revised_at else None,
    }


@router.post("/estimate/{token}/approve")
async def approve_estimate(
    token: str,
    body: ApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Customer approves an estimate — single step: name + typed signature + consent."""
    from src.services.estimate_workflow_service import EstimateWorkflowService
    wf = EstimateWorkflowService(db)
    result = await wf.approve_by_customer(
        token=token,
        name=body.name,
        email=body.email,
        signature=body.signature,
        user_agent=body.user_agent,
        notes=body.notes,
        client_ip=request.client.host if request.client else None,
    )
    if "error" in result:
        code = {"not_found": 404, "validation": 400}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.get("/estimate/{token}/pdf")
async def download_estimate_pdf(token: str, db: AsyncSession = Depends(get_db)):
    """Public PDF download — customer can download estimate without auth."""
    from src.models.customer import Customer
    from src.services.pdf_service import generate_invoice_pdf
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(EstimateApproval).where(EstimateApproval.approval_token == token)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Estimate not found or link expired")

    invoice_result = await db.execute(
        select(Invoice).where(Invoice.id == approval.invoice_id).options(selectinload(Invoice.line_items))
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Estimate not found")

    org_result = await db.execute(select(Organization).where(Organization.id == invoice.organization_id))
    org = org_result.scalar_one_or_none()

    customer_data = {}
    if invoice.customer_id:
        cust_result = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_data = {
                "display_name": cust.display_name,
                "company_name": cust.company_name,
                "email": cust.email,
                "billing_address": cust.billing_address,
            }

    org_data = {
        "name": org.name if org else "",
        "phone": org.phone if org else None,
        "email": org.email if org else None,
        "address": org.address if org else None,
        "city": org.city if org else None,
        "state": org.state if org else None,
        "zip_code": org.zip_code if org else None,
        "primary_color": org.primary_color if org else None,
    }

    invoice_data = {
        "invoice_number": invoice.invoice_number,
        "document_type": invoice.document_type,
        "subject": invoice.subject,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "subtotal": float(invoice.subtotal or 0),
        "discount": float(invoice.discount or 0),
        "tax_rate": float(invoice.tax_rate or 0),
        "tax_amount": float(invoice.tax_amount or 0),
        "total": float(invoice.total or 0),
        "amount_paid": float(invoice.amount_paid or 0),
        "balance": float(invoice.balance or 0),
        "notes": invoice.notes,
    }

    line_items_data = [
        {
            "description": li.description,
            "quantity": float(li.quantity),
            "unit_price": float(li.unit_price),
            "amount": float(li.amount or li.quantity * li.unit_price),
            "is_taxed": li.is_taxed if hasattr(li, "is_taxed") else False,
        }
        for li in (invoice.line_items or [])
    ]

    pdf_bytes = generate_invoice_pdf(org_data, invoice_data, customer_data, line_items_data)
    number = invoice.invoice_number or "draft"
    filename = f"estimate_{number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Public Invoice View & Payment ──────────────────────────────────


@router.get("/invoice/{token}")
async def view_invoice(token: str, db: AsyncSession = Depends(get_db)):
    """Public invoice view — customer clicks link from email to view and pay."""
    invoice = (await db.execute(
        select(Invoice).where(Invoice.payment_token == token)
    )).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or link expired")

    org = (await db.execute(
        select(Organization).where(Organization.id == invoice.organization_id)
    )).scalar_one_or_none()

    items = (await db.execute(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id).order_by(InvoiceLineItem.sort_order)
    )).scalars().all()

    customer_name = invoice.billing_name
    if invoice.customer_id:
        from src.models.customer import Customer
        cust = (await db.execute(select(Customer).where(Customer.id == invoice.customer_id))).scalar_one_or_none()
        if cust:
            customer_name = cust.display_name

    # Mark as viewed
    if not invoice.viewed_at:
        invoice.viewed_at = datetime.now(timezone.utc)
        if invoice.status == "sent":
            invoice.status = "viewed"
        await db.commit()

    return {
        "invoice_number": invoice.invoice_number,
        "document_type": invoice.document_type,
        "subject": invoice.subject,
        "customer_name": customer_name,
        "org_name": org.name if org else None,
        "org_color": getattr(org, "primary_color", None) if org else None,
        "status": invoice.status,
        "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "line_items": [
            {"description": li.description, "quantity": float(li.quantity),
             "unit_price": float(li.unit_price), "total": float(li.amount or li.quantity * li.unit_price)}
            for li in items
        ],
        "subtotal": float(invoice.subtotal or 0),
        "tax_amount": float(invoice.tax_amount or 0),
        "discount": float(invoice.discount or 0),
        "total": float(invoice.total or 0),
        "amount_paid": float(invoice.amount_paid or 0),
        "balance": float(invoice.balance or 0),
        "paid_date": invoice.paid_date.isoformat() if invoice.paid_date else None,
        "notes": invoice.notes,
    }


@router.post("/invoice/{token}/checkout")
async def create_checkout_session(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout Session for an invoice. Returns checkout URL."""
    from src.core.config import settings
    from src.services.stripe_service import StripeService

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Payments not configured")

    invoice = (await db.execute(
        select(Invoice).where(Invoice.payment_token == token)
    )).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or link expired")

    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="Invoice is already paid")

    base_url = settings.frontend_url
    success_url = f"{base_url}/pay/{token}?status=success"
    cancel_url = f"{base_url}/pay/{token}?status=cancelled"

    svc = StripeService(db)
    try:
        checkout_url = await svc.create_checkout_session(invoice, success_url, cancel_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"checkout_url": checkout_url}


@router.post("/invoice/{token}/verify-payment")
async def verify_payment(token: str, db: AsyncSession = Depends(get_db)):
    """Called when customer returns from Stripe Checkout. Verifies session and records payment."""
    import stripe
    from src.core.config import settings
    from src.services.stripe_service import StripeService

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Payments not configured")

    stripe.api_key = settings.stripe_secret_key

    invoice = (await db.execute(
        select(Invoice).where(Invoice.payment_token == token)
    )).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == "paid":
        return {"status": "already_paid"}

    # Find completed checkout sessions for this invoice
    try:
        sessions = stripe.checkout.Session.list(
            limit=5,
            payment_intent=invoice.stripe_payment_intent_id,
        ) if invoice.stripe_payment_intent_id else None

        # If no payment_intent stored, search by metadata
        if not sessions or not sessions.data:
            sessions = stripe.checkout.Session.list(limit=10)
            sessions.data = [
                s for s in sessions.data
                if s.metadata.get("qp_invoice_id") == invoice.id and s.payment_status == "paid"
            ]

        for session in (sessions.data if sessions else []):
            if session.payment_status == "paid":
                svc = StripeService(db)
                await svc.handle_checkout_completed(session.to_dict() if hasattr(session, 'to_dict') else dict(session))
                return {"status": "paid", "amount": session.amount_total / 100}

    except Exception as e:
        logger.error(f"Stripe payment verification failed: {e}")

    return {"status": "pending"}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Stripe webhook — processes payment events. Signature-verified."""
    import stripe
    from src.core.config import settings
    from src.services.stripe_service import StripeService

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify signature if webhook secret is configured
    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret,
            )
        except stripe.SignatureVerificationError:
            logger.warning("Stripe webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid signature")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
    else:
        # No webhook secret — parse without verification (dev/test only)
        import json
        event = json.loads(payload)

    event_type = event.get("type") if isinstance(event, dict) else event.type
    data = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event.data.object
    data_dict = data if isinstance(data, dict) else data.to_dict()

    svc = StripeService(db)

    handlers = {
        "checkout.session.completed": svc.handle_checkout_completed,
        "payment_intent.succeeded": svc.handle_payment_intent_succeeded,
        "payment_intent.payment_failed": svc.handle_payment_intent_failed,
        "setup_intent.succeeded": svc.handle_setup_intent_succeeded,
        "charge.refunded": svc.handle_charge_refunded,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(data_dict)
        logger.info(f"Stripe {event_type} processed: {data_dict.get('id')}")
    else:
        logger.debug(f"Unhandled Stripe event type: {event_type}")

    return {"received": True}


# ── Public Card Setup ─────────────────────────────────────────────


@router.get("/card/{token}")
async def get_card_status(token: str, db: AsyncSession = Depends(get_db)):
    """Public card setup page — check current saved card status."""
    from src.models.customer import Customer

    customer = (await db.execute(
        select(Customer).where(Customer.card_setup_token == token)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Invalid or expired link")

    org = (await db.execute(
        select(Organization).where(Organization.id == customer.organization_id)
    )).scalar_one_or_none()

    return {
        "customer_name": customer.display_name,
        "org_name": org.name if org else None,
        "org_color": getattr(org, "primary_color", None) if org else None,
        "has_card": bool(customer.stripe_payment_method_id),
        "card_last4": customer.stripe_card_last4,
        "card_brand": customer.stripe_card_brand,
        "card_exp_month": customer.stripe_card_exp_month,
        "card_exp_year": customer.stripe_card_exp_year,
        "autopay_enabled": customer.autopay_enabled,
    }


@router.post("/card/{token}/setup-intent")
async def create_card_setup_intent(token: str, db: AsyncSession = Depends(get_db)):
    """Create a SetupIntent for a customer to save their card (public, token-gated)."""
    from src.models.customer import Customer
    from src.services.stripe_service import StripeService

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Payments not configured")

    customer = (await db.execute(
        select(Customer).where(Customer.card_setup_token == token)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Invalid or expired link")

    svc = StripeService(db)
    result = await svc.create_setup_intent(customer)
    await db.commit()

    return {
        "client_secret": result["client_secret"],
        "publishable_key": settings.stripe_publishable_key,
    }


class EnableAutopayRequest(BaseModel):
    enable: bool = True


@router.post("/card/{token}/autopay")
async def toggle_autopay_public(
    token: str,
    body: EnableAutopayRequest,
    db: AsyncSession = Depends(get_db),
):
    """Customer toggles autopay on/off from the public card page."""
    from src.models.customer import Customer

    customer = (await db.execute(
        select(Customer).where(Customer.card_setup_token == token)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Invalid or expired link")

    if body.enable and not customer.stripe_payment_method_id:
        raise HTTPException(status_code=400, detail="Save a card first before enabling autopay")

    customer.autopay_enabled = body.enable
    await db.commit()

    return {"autopay_enabled": customer.autopay_enabled}
