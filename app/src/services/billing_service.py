"""Billing service — recurring invoice generation, autopay orchestration, dunning retries."""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.autopay_attempt import AutopayAttempt, AutopayAttemptStatus
from src.models.customer import Customer, BillingFrequency
from src.models.invoice import Invoice
from src.services.invoice_service import InvoiceService
from src.services.stripe_service import StripeService

logger = logging.getLogger(__name__)

# Retry schedule: attempt 1 (immediate), attempt 2 (+3 days), attempt 3 (+7 days)
MAX_RETRIES = 3


class BillingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_recurring_invoices(self, org_id: str) -> dict:
        """Generate recurring invoices for all customers due today. Returns summary."""
        today = date.today()
        customers = await self._get_customers_due(org_id, today)

        generated = 0
        autopay_attempted = 0
        autopay_succeeded = 0
        errors = []

        for customer in customers:
            try:
                invoice = await self._generate_invoice_for_customer(customer, org_id, today)
                generated += 1

                if customer.autopay_enabled and customer.stripe_payment_method_id:
                    attempt = await self._process_autopay(customer, invoice)
                    autopay_attempted += 1
                    if attempt.status == AutopayAttemptStatus.succeeded.value:
                        autopay_succeeded += 1
                        await self._send_autopay_receipt(customer, invoice)
                    else:
                        await self._send_payment_failed_email(customer, invoice, attempt)

                # Advance billing date
                self._advance_billing_date(customer)
                await self.db.commit()

            except Exception as e:
                await self.db.rollback()
                errors.append({"customer_id": customer.id, "name": customer.display_name, "error": str(e)})
                logger.error(f"Billing failed for customer {customer.id}: {e}")

        summary = {
            "date": today.isoformat(),
            "generated": generated,
            "autopay_attempted": autopay_attempted,
            "autopay_succeeded": autopay_succeeded,
            "errors": errors,
        }
        logger.info(f"Billing cycle complete: {summary}")
        return summary

    async def retry_failed_payments(self, org_id: str) -> dict:
        """Retry failed autopay attempts that are due for retry."""
        now = datetime.now(timezone.utc)

        attempts = (await self.db.execute(
            select(AutopayAttempt).where(
                AutopayAttempt.organization_id == org_id,
                AutopayAttempt.status == AutopayAttemptStatus.failed.value,
                AutopayAttempt.next_retry_at.isnot(None),
                AutopayAttempt.next_retry_at <= now,
                AutopayAttempt.attempt_number < MAX_RETRIES,
            )
        )).scalars().all()

        retried = 0
        succeeded = 0

        for attempt in attempts:
            try:
                customer = (await self.db.execute(
                    select(Customer).where(Customer.id == attempt.customer_id)
                )).scalar_one_or_none()
                invoice = (await self.db.execute(
                    select(Invoice).where(Invoice.id == attempt.invoice_id)
                )).scalar_one_or_none()

                if not customer or not invoice:
                    continue
                if invoice.status == "paid":
                    attempt.next_retry_at = None
                    continue
                if not customer.stripe_payment_method_id:
                    attempt.next_retry_at = None
                    continue

                # Create new attempt via StripeService
                stripe_svc = StripeService(self.db)
                new_attempt = await stripe_svc.charge_autopay(customer, invoice)
                retried += 1

                if new_attempt.status == AutopayAttemptStatus.succeeded.value:
                    succeeded += 1
                    await self._send_autopay_receipt(customer, invoice)
                else:
                    await self._send_payment_failed_email(customer, invoice, new_attempt)

                # Clear the old attempt's retry
                attempt.next_retry_at = None
                await self.db.commit()

            except Exception as e:
                await self.db.rollback()
                logger.error(f"Retry failed for attempt {attempt.id}: {e}")

        summary = {"retried": retried, "succeeded": succeeded}
        logger.info(f"Payment retries complete: {summary}")
        return summary

    async def get_upcoming_billing(self, org_id: str) -> list[dict]:
        """Get customers due for billing in the next 7 days."""
        today = date.today()
        window = today + timedelta(days=7)

        customers = (await self.db.execute(
            select(Customer).where(
                Customer.organization_id == org_id,
                Customer.status == "active",
                Customer.monthly_rate > 0,
                Customer.next_billing_date.isnot(None),
                Customer.next_billing_date <= window,
            ).order_by(Customer.next_billing_date)
        )).scalars().all()

        return [
            {
                "id": c.id,
                "display_name": c.display_name,
                "monthly_rate": c.monthly_rate,
                "billing_frequency": c.billing_frequency,
                "next_billing_date": c.next_billing_date.isoformat() if c.next_billing_date else None,
                "autopay_enabled": c.autopay_enabled,
                "has_payment_method": c.has_payment_method,
            }
            for c in customers
        ]

    async def get_failed_payments(self, org_id: str) -> list[dict]:
        """Get recent failed autopay attempts needing attention."""
        attempts = (await self.db.execute(
            select(AutopayAttempt).where(
                AutopayAttempt.organization_id == org_id,
                AutopayAttempt.status == AutopayAttemptStatus.failed.value,
            ).order_by(AutopayAttempt.created_at.desc()).limit(50)
        )).scalars().all()

        results = []
        for a in attempts:
            customer = (await self.db.execute(
                select(Customer).where(Customer.id == a.customer_id)
            )).scalar_one_or_none()
            results.append({
                "id": a.id,
                "customer_id": a.customer_id,
                "customer_name": customer.display_name if customer else "Unknown",
                "invoice_id": a.invoice_id,
                "amount": a.amount,
                "attempt_number": a.attempt_number,
                "failure_reason": a.failure_reason,
                "failure_code": a.failure_code,
                "next_retry_at": a.next_retry_at.isoformat() if a.next_retry_at else None,
                "created_at": a.created_at.isoformat(),
            })
        return results

    async def get_billing_stats(self, org_id: str) -> dict:
        """Dashboard stats for billing overview."""
        from sqlalchemy import func

        today = date.today()
        first_of_month = today.replace(day=1)
        next_month = first_of_month + relativedelta(months=1)

        # Active customers with rates
        billable = (await self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.organization_id == org_id,
                Customer.status == "active",
                Customer.monthly_rate > 0,
            )
        )).scalar() or 0

        # Autopay enrolled
        autopay_enrolled = (await self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.organization_id == org_id,
                Customer.status == "active",
                Customer.autopay_enabled == True,
                Customer.stripe_payment_method_id.isnot(None),
            )
        )).scalar() or 0

        # Projected monthly revenue
        projected = (await self.db.execute(
            select(func.coalesce(func.sum(Customer.monthly_rate), 0.0)).where(
                Customer.organization_id == org_id,
                Customer.status == "active",
                Customer.monthly_rate > 0,
            )
        )).scalar() or 0.0

        # Failed payments (unresolved)
        failed_count = (await self.db.execute(
            select(func.count(AutopayAttempt.id)).where(
                AutopayAttempt.organization_id == org_id,
                AutopayAttempt.status == AutopayAttemptStatus.failed.value,
                AutopayAttempt.next_retry_at.isnot(None),
            )
        )).scalar() or 0

        return {
            "billable_customers": billable,
            "autopay_enrolled": autopay_enrolled,
            "projected_monthly_revenue": round(projected, 2),
            "failed_payments_pending": failed_count,
        }

    # ── Internal Helpers ──────────────────────────────────────────────

    async def _get_customers_due(self, org_id: str, billing_date: date) -> list[Customer]:
        """Get active customers whose next_billing_date <= today."""
        return list((await self.db.execute(
            select(Customer).where(
                Customer.organization_id == org_id,
                Customer.status == "active",
                Customer.monthly_rate > 0,
                Customer.next_billing_date.isnot(None),
                Customer.next_billing_date <= billing_date,
            )
        )).scalars().all())

    async def _generate_invoice_for_customer(
        self, customer: Customer, org_id: str, billing_date: date
    ) -> Invoice:
        """Create a recurring invoice from customer's monthly rate."""
        period_start, period_end = self._billing_period(customer, billing_date)

        # Build line item description
        freq_label = customer.billing_frequency.replace("_", " ").title()
        period_label = f"{period_start.strftime('%b %d')} – {period_end.strftime('%b %d, %Y')}"

        inv_svc = InvoiceService(self.db)
        invoice = await inv_svc.create(
            org_id=org_id,
            customer_id=customer.id,
            issue_date=billing_date,
            due_date=billing_date + timedelta(days=customer.payment_terms_days or 30),
            subject=f"{freq_label} Pool Service — {period_label}",
            is_recurring=True,
            generation_source="recurring",
            billing_period_start=period_start,
            billing_period_end=period_end,
            line_items_data=[{
                "description": f"Pool Service — {period_label}",
                "quantity": 1.0,
                "unit_price": customer.monthly_rate,
            }],
        )

        # Auto-assign number and mark as sent
        invoice = await inv_svc.send(org_id, invoice.id, sent_by="billing_system")
        customer.last_billed_at = datetime.now(timezone.utc)

        logger.info(f"Generated invoice {invoice.invoice_number} for {customer.display_name}: ${customer.monthly_rate:.2f}")
        return invoice

    async def _process_autopay(self, customer: Customer, invoice: Invoice) -> AutopayAttempt:
        """Attempt autopay charge for an invoice."""
        stripe_svc = StripeService(self.db)
        return await stripe_svc.charge_autopay(customer, invoice)

    def _advance_billing_date(self, customer: Customer) -> None:
        """Advance next_billing_date based on billing frequency."""
        if not customer.next_billing_date:
            return

        freq = customer.billing_frequency
        current = customer.next_billing_date

        if freq == BillingFrequency.monthly.value:
            customer.next_billing_date = current + relativedelta(months=1)
        elif freq == BillingFrequency.quarterly.value:
            customer.next_billing_date = current + relativedelta(months=3)
        elif freq == BillingFrequency.annual.value:
            customer.next_billing_date = current + relativedelta(years=1)
        else:
            customer.next_billing_date = current + relativedelta(months=1)

    async def _send_payment_failed_email(
        self, customer: Customer, invoice: Invoice, attempt: AutopayAttempt
    ) -> None:
        """Send payment failure notification email."""
        if not customer.email:
            return
        try:
            from src.services.email_service import EmailService
            from src.core.config import settings as app_settings
            email_svc = EmailService(self.db)
            pay_url = f"{app_settings.frontend_url}/pay/{invoice.payment_token}"
            await email_svc.send_payment_failed_email(
                org_id=invoice.organization_id,
                to=customer.email,
                customer_name=customer.display_name,
                invoice_number=invoice.invoice_number or "N/A",
                amount=invoice.balance,
                pay_url=pay_url,
                attempt_number=attempt.attempt_number,
            )
        except Exception as e:
            logger.error(f"Failed to send payment failure email to {customer.email}: {e}")

    async def _send_autopay_receipt(self, customer: Customer, invoice: Invoice) -> None:
        """Send autopay payment confirmation email."""
        if not customer.email:
            return
        try:
            from src.services.email_service import EmailService
            email_svc = EmailService(self.db)
            await email_svc.send_autopay_receipt(
                org_id=invoice.organization_id,
                to=customer.email,
                customer_name=customer.display_name,
                invoice_number=invoice.invoice_number or "N/A",
                amount=customer.monthly_rate,
            )
        except Exception as e:
            logger.error(f"Failed to send autopay receipt to {customer.email}: {e}")

    @staticmethod
    def _billing_period(customer: Customer, billing_date: date) -> tuple[date, date]:
        """Calculate billing period start/end from customer frequency."""
        freq = customer.billing_frequency
        start = billing_date

        if freq == BillingFrequency.quarterly.value:
            end = start + relativedelta(months=3) - timedelta(days=1)
        elif freq == BillingFrequency.annual.value:
            end = start + relativedelta(years=1) - timedelta(days=1)
        else:
            end = start + relativedelta(months=1) - timedelta(days=1)

        return start, end
