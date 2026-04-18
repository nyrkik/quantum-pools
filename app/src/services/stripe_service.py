"""Stripe payment service — checkout sessions, saved cards, autopay, webhook handling.

Single-business mode: uses STRIPE_SECRET_KEY directly.
SaaS mode (future): adds stripe_account parameter from org.stripe_connected_account_id.
"""

import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.autopay_attempt import AutopayAttempt, AutopayAttemptStatus
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

    # ── Checkout (existing one-time payment flow) ─────────────────────

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

        # Use balance (not total) so partially-paid invoices show remaining amount
        amount_due = invoice.balance or invoice.total or 0
        if amount_due <= 0:
            raise ValueError("Nothing to pay — invoice balance is zero")

        stripe_line_items = [{
            "price_data": {
                "currency": "usd",
                "unit_amount": int(round(amount_due * 100)),
                "product_data": {
                    "name": f"Invoice {invoice.invoice_number}",
                    "description": invoice.subject or "Pool Service",
                },
            },
            "quantity": 1,
        }]

        stripe_customer_id = await self._ensure_stripe_customer(customer, invoice.organization_id)
        customer_email = (customer.email if customer else invoice.billing_email)

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

    # ── Saved Payment Methods (SetupIntent) ───────────────────────────

    async def create_setup_intent(self, customer: Customer) -> dict:
        """Create a Stripe SetupIntent for saving a card. Returns client_secret + token."""
        s = _get_stripe()
        stripe_customer_id = await self._ensure_stripe_customer(customer, customer.organization_id)
        if not stripe_customer_id:
            raise ValueError("Could not create Stripe customer")

        si = s.SetupIntent.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
            metadata={
                "qp_customer_id": customer.id,
                "qp_org_id": customer.organization_id,
            },
        )

        # Generate a public token for the card setup page
        if not customer.card_setup_token:
            customer.card_setup_token = secrets.token_urlsafe(32)
            await self.db.flush()

        return {
            "client_secret": si.client_secret,
            "setup_intent_id": si.id,
            "card_setup_token": customer.card_setup_token,
        }

    async def save_payment_method(self, customer: Customer, payment_method_id: str) -> None:
        """Save a payment method to a customer after SetupIntent succeeds."""
        s = _get_stripe()

        # Retrieve payment method details from Stripe
        pm = s.PaymentMethod.retrieve(payment_method_id)

        customer.stripe_payment_method_id = payment_method_id
        if pm.card:
            customer.stripe_card_last4 = pm.card.last4
            customer.stripe_card_brand = pm.card.brand
            customer.stripe_card_exp_month = pm.card.exp_month
            customer.stripe_card_exp_year = pm.card.exp_year

        # Reset dunning state when card is updated
        customer.autopay_failure_count = 0
        customer.autopay_last_failed_at = None

        await self.db.flush()
        logger.info(f"Saved payment method {pm.card.brand} ****{pm.card.last4} for customer {customer.id}")

    async def detach_payment_method(self, customer: Customer) -> None:
        """Remove saved payment method from customer."""
        s = _get_stripe()

        if customer.stripe_payment_method_id:
            try:
                s.PaymentMethod.detach(customer.stripe_payment_method_id)
            except Exception as e:
                logger.warning(f"Failed to detach payment method from Stripe: {e}")

        customer.stripe_payment_method_id = None
        customer.stripe_card_last4 = None
        customer.stripe_card_brand = None
        customer.stripe_card_exp_month = None
        customer.stripe_card_exp_year = None
        customer.autopay_enabled = False
        await self.db.flush()

    # ── AutoPay (off-session charging) ────────────────────────────────

    async def charge_autopay(self, customer: Customer, invoice: Invoice) -> AutopayAttempt:
        """Charge a customer's saved card for an invoice. Returns the attempt record."""
        s = _get_stripe()

        if not customer.stripe_customer_id or not customer.stripe_payment_method_id:
            raise ValueError("Customer has no saved payment method")

        amount_cents = int(round(invoice.balance * 100))
        if amount_cents <= 0:
            raise ValueError("Nothing to charge — invoice balance is zero")

        # Count existing attempts for this invoice
        existing = (await self.db.execute(
            select(AutopayAttempt).where(
                AutopayAttempt.invoice_id == invoice.id,
            )
        )).scalars().all()
        attempt_number = len(existing) + 1

        attempt = AutopayAttempt(
            id=str(uuid.uuid4()),
            organization_id=invoice.organization_id,
            customer_id=customer.id,
            invoice_id=invoice.id,
            attempt_number=attempt_number,
            amount=invoice.balance,
            status=AutopayAttemptStatus.pending.value,
        )
        self.db.add(attempt)

        try:
            pi = s.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                customer=customer.stripe_customer_id,
                payment_method=customer.stripe_payment_method_id,
                off_session=True,
                confirm=True,
                metadata={
                    "qp_invoice_id": invoice.id,
                    "qp_org_id": invoice.organization_id,
                    "qp_customer_id": customer.id,
                    "is_autopay": "true",
                },
            )
            attempt.stripe_payment_intent_id = pi.id

            if pi.status == "succeeded":
                attempt.status = AutopayAttemptStatus.succeeded.value
                await self._record_autopay_payment(customer, invoice, pi)
                logger.info(f"Autopay succeeded: ${invoice.balance:.2f} for invoice {invoice.invoice_number}")
            else:
                # requires_action or other non-success — treat as failure for off-session
                attempt.status = AutopayAttemptStatus.failed.value
                attempt.failure_reason = f"Payment requires action: {pi.status}"
                attempt.failure_code = "requires_action"
                attempt.next_retry_at = self._next_retry_time(attempt_number)
                self._update_customer_dunning(customer)

        except stripe.CardError as e:
            attempt.status = AutopayAttemptStatus.failed.value
            attempt.failure_reason = str(e.user_message or e)
            attempt.failure_code = e.code
            if hasattr(e, 'payment_intent') and e.payment_intent:
                attempt.stripe_payment_intent_id = e.payment_intent.get("id")
            attempt.next_retry_at = self._next_retry_time(attempt_number)
            self._update_customer_dunning(customer)
            logger.warning(f"Autopay failed for invoice {invoice.invoice_number}: {e.code} — {e.user_message}")

        except Exception as e:
            attempt.status = AutopayAttemptStatus.failed.value
            attempt.failure_reason = str(e)
            attempt.failure_code = "unknown"
            attempt.next_retry_at = self._next_retry_time(attempt_number)
            self._update_customer_dunning(customer)
            logger.error(f"Autopay error for invoice {invoice.invoice_number}: {e}")

        await self.db.flush()
        return attempt

    # ── Webhook Handlers ──────────────────────────────────────────────

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
        if payment_intent_id and await self._payment_exists(payment_intent_id):
            return

        amount_total = session.get("amount_total", 0) / 100

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

        inv_svc = InvoiceService(self.db)
        await inv_svc.record_payment(invoice, amount_total)

        # Activation funnel — first-payment-received (via Stripe Checkout)
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_payment_received",
            organization_id=org_id,
            entity_refs={"customer_id": invoice.customer_id, "invoice_id": invoice.id},
            source="stripe_checkout",
        )

        await self.db.commit()
        logger.info(f"Payment recorded: ${amount_total:.2f} for invoice {invoice.invoice_number} (intent: {payment_intent_id})")

    async def handle_payment_intent_succeeded(self, data: dict) -> None:
        """Handle payment_intent.succeeded — primarily for autopay confirmations."""
        payment_intent_id = data.get("id")
        metadata = data.get("metadata", {})

        # Only process autopay payments (checkout payments handled by handle_checkout_completed)
        if metadata.get("is_autopay") != "true":
            return

        if await self._payment_exists(payment_intent_id):
            return

        invoice_id = metadata.get("qp_invoice_id")
        if not invoice_id:
            return

        invoice = (await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )).scalar_one_or_none()
        if not invoice:
            logger.error(f"Invoice {invoice_id} not found for autopay intent {payment_intent_id}")
            return

        customer = None
        if invoice.customer_id:
            customer = (await self.db.execute(
                select(Customer).where(Customer.id == invoice.customer_id)
            )).scalar_one_or_none()

        amount = data.get("amount_received", data.get("amount", 0)) / 100

        payment = Payment(
            id=str(uuid.uuid4()),
            organization_id=invoice.organization_id,
            customer_id=invoice.customer_id,
            invoice_id=invoice.id,
            amount=amount,
            payment_method="card",
            payment_date=date.today(),
            status=PaymentStatus.completed.value,
            stripe_payment_intent_id=payment_intent_id,
            is_autopay=True,
            recorded_by="stripe_autopay",
        )
        self.db.add(payment)

        inv_svc = InvoiceService(self.db)
        await inv_svc.record_payment(invoice, amount)

        # Activation funnel — first-payment-received (via Stripe AutoPay webhook)
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_payment_received",
            organization_id=invoice.organization_id,
            entity_refs={"customer_id": invoice.customer_id, "invoice_id": invoice.id},
            source="stripe_autopay_webhook",
        )

        # Update autopay attempt record
        attempt = (await self.db.execute(
            select(AutopayAttempt).where(
                AutopayAttempt.stripe_payment_intent_id == payment_intent_id
            )
        )).scalar_one_or_none()
        if attempt:
            attempt.status = AutopayAttemptStatus.succeeded.value

        # Reset dunning on customer
        if customer:
            customer.autopay_failure_count = 0
            customer.autopay_last_failed_at = None

        await self.db.commit()
        logger.info(f"Autopay payment confirmed: ${amount:.2f} for invoice {invoice.invoice_number}")

    async def handle_payment_intent_failed(self, data: dict) -> None:
        """Handle payment_intent.payment_failed — update attempt, trigger dunning."""
        payment_intent_id = data.get("id")
        metadata = data.get("metadata", {})

        if metadata.get("is_autopay") != "true":
            return

        attempt = (await self.db.execute(
            select(AutopayAttempt).where(
                AutopayAttempt.stripe_payment_intent_id == payment_intent_id
            )
        )).scalar_one_or_none()
        if not attempt:
            return

        last_error = data.get("last_payment_error", {})
        attempt.status = AutopayAttemptStatus.failed.value
        attempt.failure_reason = last_error.get("message", "Payment failed")
        attempt.failure_code = last_error.get("decline_code") or last_error.get("code")
        attempt.next_retry_at = self._next_retry_time(attempt.attempt_number)

        customer = (await self.db.execute(
            select(Customer).where(Customer.id == attempt.customer_id)
        )).scalar_one_or_none()
        if customer:
            self._update_customer_dunning(customer)

        await self.db.commit()
        logger.warning(f"Autopay failed via webhook for invoice attempt {attempt.id}: {attempt.failure_code}")

    async def handle_setup_intent_succeeded(self, data: dict) -> None:
        """Handle setup_intent.succeeded — save payment method to customer."""
        metadata = data.get("metadata", {})
        customer_id = metadata.get("qp_customer_id")
        if not customer_id:
            return

        customer = (await self.db.execute(
            select(Customer).where(Customer.id == customer_id)
        )).scalar_one_or_none()
        if not customer:
            logger.error(f"Customer {customer_id} not found for setup intent {data.get('id')}")
            return

        payment_method_id = data.get("payment_method")
        if payment_method_id:
            await self.save_payment_method(customer, payment_method_id)
            await self.db.commit()
            logger.info(f"Card saved via webhook for customer {customer_id}")

    async def handle_charge_refunded(self, data: dict) -> None:
        """Handle charge.refunded — log refund for tracking."""
        payment_intent_id = data.get("payment_intent")
        if not payment_intent_id:
            return

        payment = (await self.db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
        )).scalar_one_or_none()
        if payment:
            refund_amount = data.get("amount_refunded", 0) / 100
            payment.status = PaymentStatus.refunded.value
            payment.notes = f"Refunded ${refund_amount:.2f} via Stripe"

            # Update invoice balance
            if payment.invoice_id:
                invoice = (await self.db.execute(
                    select(Invoice).where(Invoice.id == payment.invoice_id)
                )).scalar_one_or_none()
                if invoice:
                    invoice.amount_paid = round(invoice.amount_paid - refund_amount, 2)
                    invoice.balance = round(invoice.total - invoice.amount_paid, 2)
                    if invoice.balance > 0 and invoice.status == "paid":
                        invoice.status = "sent"
                        invoice.paid_date = None

            await self.db.commit()
            logger.info(f"Refund recorded for payment intent {payment_intent_id}")

    # ── Helpers ───────────────────────────────────────────────────────

    async def _ensure_stripe_customer(self, customer: Customer | None, org_id: str) -> str | None:
        """Create or return existing Stripe customer ID."""
        if not customer:
            return None
        if customer.stripe_customer_id:
            return customer.stripe_customer_id

        s = _get_stripe()
        try:
            sc = s.Customer.create(
                email=customer.email,
                name=customer.display_name,
                metadata={"qp_customer_id": customer.id, "qp_org_id": org_id},
            )
            customer.stripe_customer_id = sc.id
            await self.db.flush()
            return sc.id
        except Exception as e:
            logger.warning(f"Failed to create Stripe customer: {e}")
            return None

    async def _payment_exists(self, payment_intent_id: str) -> bool:
        """Check if a payment has already been recorded for this intent."""
        existing = (await self.db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
        )).scalar_one_or_none()
        if existing:
            logger.info(f"Payment already recorded for intent {payment_intent_id}")
            return True
        return False

    async def _record_autopay_payment(self, customer: Customer, invoice: Invoice, pi) -> None:
        """Record payment from a successful autopay PaymentIntent."""
        amount = pi.amount_received / 100 if hasattr(pi, 'amount_received') else pi.amount / 100

        payment = Payment(
            id=str(uuid.uuid4()),
            organization_id=invoice.organization_id,
            customer_id=customer.id,
            invoice_id=invoice.id,
            amount=amount,
            payment_method="card",
            payment_date=date.today(),
            status=PaymentStatus.completed.value,
            stripe_payment_intent_id=pi.id,
            is_autopay=True,
            recorded_by="stripe_autopay",
        )
        self.db.add(payment)

        inv_svc = InvoiceService(self.db)
        await inv_svc.record_payment(invoice, amount)

        # Activation funnel — first-payment-received (via _record_autopay_payment)
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_payment_received",
            organization_id=invoice.organization_id,
            entity_refs={"customer_id": customer.id, "invoice_id": invoice.id},
            source="stripe_autopay_internal",
        )

        # Reset dunning
        customer.autopay_failure_count = 0
        customer.autopay_last_failed_at = None

    def _update_customer_dunning(self, customer: Customer) -> None:
        """Update customer dunning state after a failed payment."""
        customer.autopay_failure_count = (customer.autopay_failure_count or 0) + 1
        customer.autopay_last_failed_at = datetime.now(timezone.utc)

    @staticmethod
    def _next_retry_time(attempt_number: int) -> datetime | None:
        """Calculate next retry time. 3 attempts: immediate, +3 days, +7 days. None after 3."""
        if attempt_number >= 3:
            return None  # No more retries
        delays = {1: 3, 2: 7}
        days = delays.get(attempt_number, 7)
        return datetime.now(timezone.utc) + timedelta(days=days)
