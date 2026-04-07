"""Stripe payment service — checkout sessions, webhook handling, payment recording.

Single-business mode: uses STRIPE_SECRET_KEY directly.
SaaS mode (future): adds stripe_account parameter from org.stripe_connected_account_id.
"""

import logging
import uuid
from datetime import date, datetime, timezone

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.customer import Customer
from src.models.invoice import Invoice
from src.models.payment import Payment, PaymentStatus
from src.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)


def _get_stripe():
    """Get configured Stripe module."""
    stripe.api_key = settings.stripe_secret_key
    return stripe


class StripeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_checkout_session(
        self, invoice: Invoice, success_url: str, cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout Session for an invoice. Returns the checkout URL."""
        s = _get_stripe()

        customer = None
        if invoice.customer_id:
            customer = (await self.db.execute(
                select(Customer).where(Customer.id == invoice.customer_id)
            )).scalar_one_or_none()

        if not customer and not invoice.billing_email:
            raise ValueError("Invoice has no customer or billing email")

        # Build line items from invoice
        from src.models.invoice import InvoiceLineItem
        items = (await self.db.execute(
            select(InvoiceLineItem)
            .where(InvoiceLineItem.invoice_id == invoice.id)
            .order_by(InvoiceLineItem.sort_order)
        )).scalars().all()

        if not items:
            raise ValueError("Invoice has no line items")

        # Use balance (not total) so partially-paid invoices show remaining amount
        amount_due = invoice.balance or invoice.total or 0
        if amount_due <= 0:
            raise ValueError("Nothing to pay — invoice balance is zero")

        # Single line item with invoice total (Stripe Checkout shows a clean summary)
        stripe_line_items = [{
            "price_data": {
                "currency": "usd",
                "unit_amount": int(round(amount_due * 100)),  # cents
                "product_data": {
                    "name": f"Invoice {invoice.invoice_number}",
                    "description": invoice.subject or "Pool Service",
                },
            },
            "quantity": 1,
        }]

        # Create or reuse Stripe customer
        stripe_customer_id = None
        customer_email = None
        if customer:
            customer_email = customer.email
            if customer.stripe_customer_id:
                stripe_customer_id = customer.stripe_customer_id
            else:
                try:
                    sc = s.Customer.create(
                        email=customer.email,
                        name=customer.display_name,
                        metadata={"qp_customer_id": customer.id, "qp_org_id": invoice.organization_id},
                    )
                    stripe_customer_id = sc.id
                    customer.stripe_customer_id = sc.id
                    await self.db.flush()
                except Exception as e:
                    logger.warning(f"Failed to create Stripe customer: {e}")
        else:
            customer_email = invoice.billing_email

        session_params = {
            "payment_method_types": ["card"],
            "line_items": stripe_line_items,
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {
                "qp_invoice_id": invoice.id,
                "qp_org_id": invoice.organization_id,
                "qp_customer_id": invoice.customer_id or "",
            },
            "payment_intent_data": {
                "metadata": {
                    "qp_invoice_id": invoice.id,
                    "qp_org_id": invoice.organization_id,
                },
            },
        }
        if stripe_customer_id:
            session_params["customer"] = stripe_customer_id
        else:
            session_params["customer_email"] = customer_email

        session = s.checkout.Session.create(**session_params)
        return session.url

    async def handle_checkout_completed(self, session: dict) -> None:
        """Process a completed checkout session — record payment, update invoice."""
        metadata = session.get("metadata", {})
        invoice_id = metadata.get("qp_invoice_id")
        org_id = metadata.get("qp_org_id")

        if not invoice_id or not org_id:
            logger.warning(f"Stripe checkout session missing metadata: {session.get('id')}")
            return

        invoice = (await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )).scalar_one_or_none()
        if not invoice:
            logger.error(f"Invoice {invoice_id} not found for Stripe session {session.get('id')}")
            return

        # Avoid duplicate processing
        payment_intent_id = session.get("payment_intent")
        if payment_intent_id:
            existing = (await self.db.execute(
                select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
            )).scalar_one_or_none()
            if existing:
                logger.info(f"Payment already recorded for intent {payment_intent_id}")
                return

        amount_total = session.get("amount_total", 0) / 100  # cents → dollars

        payment = Payment(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            customer_id=invoice.customer_id,
            invoice_id=invoice.id,
            amount=amount_total,
            payment_method="card",
            payment_date=date.today(),
            status=PaymentStatus.completed.value,
            stripe_payment_intent_id=payment_intent_id,
            reference_number=payment_intent_id,
            recorded_by="stripe_checkout",
        )
        self.db.add(payment)

        # Update invoice balance and status
        inv_svc = InvoiceService(self.db)
        await inv_svc.record_payment(invoice, amount_total)

        await self.db.commit()
        logger.info(f"Payment recorded: ${amount_total:.2f} for invoice {invoice.invoice_number} (intent: {payment_intent_id})")
