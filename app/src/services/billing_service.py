"""Billing service — recurring invoice generation, autopay orchestration, dunning retries."""

import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from email.utils import getaddresses
from dateutil.relativedelta import relativedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.autopay_attempt import AutopayAttempt, AutopayAttemptStatus
from src.models.customer import Customer, BillingFrequency
from src.models.invoice import Invoice
from src.models.property import Property
from src.models.property_hold import PropertyHold
from src.services.invoice_service import InvoiceService
from src.services.stripe_service import StripeService

logger = logging.getLogger(__name__)

# Retry schedule: attempt 1 (immediate), attempt 2 (+3 days), attempt 3 (+7 days)
MAX_RETRIES = 3

# Dunning sequence cadence — days past due that trigger each step.
# Indexed 1..4 because step 0 means "no dunning sent yet."
DUNNING_DAYS_PAST_DUE = {1: 0, 2: 3, 3: 7, 4: 14}
DUNNING_FINAL_STEP = 4
# Eligible invoice statuses. Excludes draft, paid, void, written_off.
DUNNING_ELIGIBLE_STATUSES = ("sent", "viewed", "revised", "overdue")

# Quick syntactic email check. Real customer data is messy: trailing
# commas, multi-address fields, "Name <addr>" forms, garbage. We use
# stdlib `getaddresses` to split + parse, then this regex to filter
# obvious junk. Not RFC 5322 — it's a pragmatic guard against sending
# to addresses that would just bounce.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _parse_recipients(raw: str | None) -> list[str]:
    """Split a possibly-multi-address contact field into clean addresses.

    Handles: trailing commas, comma-separated lists, "Name <addr>" forms,
    semicolon separators, accidental whitespace. Drops anything that
    doesn't pass the syntactic check. Deduplicates case-insensitively.

    Pre-splits on `,` / `;` BEFORE calling stdlib `getaddresses` because
    getaddresses misparses `"foo@x.com,"` (trailing comma) — a common
    real-world data pattern. Each piece is parsed independently so a
    single bad token can't break the whole field.
    """
    if not raw:
        return []
    pieces = re.split(r"[,;]", raw)
    out: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        # getaddresses still useful per-piece for "Name <addr>" forms.
        for _name, addr in getaddresses([piece]):
            clean = (addr or "").strip()
            if not clean or not _EMAIL_RE.match(clean):
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(clean)
    return out


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
        skipped_on_hold = 0
        errors = []

        for customer in customers:
            try:
                # Phase 8 — skip customers whose every property is on a
                # service hold covering the billing period start. Single-
                # property customers (typical residential) skip cleanly;
                # multi-property customers still bill if at least one
                # property is active. Per-property line-item exclusion
                # arrives with Phase 6 (consolidated billing).
                period_start, _ = self._billing_period(customer, today)
                if await self._all_properties_held(customer.id, period_start):
                    self._advance_billing_date(customer)
                    await self.db.commit()
                    skipped_on_hold += 1
                    logger.info(
                        f"Recurring billing: skipped {customer.display_name} "
                        f"({customer.id}) — all properties on hold for {period_start}"
                    )
                    continue
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
            "skipped_on_hold": skipped_on_hold,
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

    async def preview_dunning_sequence(self, org_id: str) -> dict:
        """Dry-run version of run_dunning_sequence: returns what WOULD be
        sent without sending anything or advancing state. Use to review
        the backlog before enabling automatic dunning."""
        from src.models.invoice import InvoiceStatus

        today = date.today()
        invoices = (await self.db.execute(
            select(Invoice).where(
                Invoice.organization_id == org_id,
                Invoice.status.in_(DUNNING_ELIGIBLE_STATUSES),
                Invoice.document_type == "invoice",
                Invoice.balance > 0,
                Invoice.last_dunning_step_sent < DUNNING_FINAL_STEP,
                # PSS-imported invoices are excluded — they may not be legit
                # and need manual review before being dunned. Brian's
                # explicit rule, 2026-04-28.
                Invoice.pss_invoice_id.is_(None),
            )
        )).scalars().all()

        would_send: list[dict] = []
        not_due_yet: list[dict] = []

        for inv in invoices:
            effective_due = inv.due_date or inv.issue_date
            days_past_due = (today - effective_due).days
            next_step = (inv.last_dunning_step_sent or 0) + 1
            if next_step > DUNNING_FINAL_STEP:
                continue

            recipients = await self._resolve_dunning_recipients(inv)
            row = {
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "customer_id": inv.customer_id,
                "balance": float(inv.balance or 0),
                "days_past_due": days_past_due,
                "next_step": next_step,
                # Joined display string + raw list — UI can pick which to show.
                "recipient_email": ", ".join(recipients) if recipients else None,
                "recipients": recipients,
                "recipient_count": len(recipients),
                "has_recipient": bool(recipients),
            }

            if days_past_due >= DUNNING_DAYS_PAST_DUE[next_step]:
                would_send.append(row)
            else:
                not_due_yet.append(row)

        # Sort would-send by step asc, then by days_past_due desc so the
        # oldest stuff bubbles up first.
        would_send.sort(key=lambda r: (r["next_step"], -r["days_past_due"]))

        return {
            "as_of": today.isoformat(),
            "eligible": len(invoices),
            "would_send_count": len(would_send),
            "would_send": would_send,
            "not_due_yet_count": len(not_due_yet),
            "missing_recipient_count": sum(1 for r in would_send if not r["has_recipient"]),
        }

    async def run_dunning_sequence(
        self, org_id: str, invoice_ids: list[str] | None = None
    ) -> dict:
        """Advance every eligible invoice through the next dunning step.

        Eligibility: status in DUNNING_ELIGIBLE_STATUSES, document_type=invoice,
        balance > 0, has a due_date (or issue_date as fallback) that's old
        enough to qualify for the next step.

        When `invoice_ids` is provided, the eligibility set is restricted
        to those IDs (intersected with the standard filter). Used for
        selective send from the UI when the user picks specific rows.

        Idempotency: only sends step N if last_dunning_step_sent < N AND
        days_past_due >= DUNNING_DAYS_PAST_DUE[N]. Calling multiple times
        per day is safe — at most one email per invoice per call.

        Customer pays / drops balance to zero between steps → invoice
        falls out of the eligibility filter, sequence stops naturally.
        """
        from src.models.invoice import InvoiceStatus

        today = date.today()
        query = select(Invoice).where(
            Invoice.organization_id == org_id,
            Invoice.status.in_(DUNNING_ELIGIBLE_STATUSES),
            Invoice.document_type == "invoice",
            Invoice.balance > 0,
            Invoice.last_dunning_step_sent < DUNNING_FINAL_STEP,
            # PSS-imported invoices are excluded — they may not be legit
            # and need manual review before being dunned. Brian's
            # explicit rule, 2026-04-28.
            Invoice.pss_invoice_id.is_(None),
        )
        if invoice_ids is not None:
            if not invoice_ids:
                return {
                    "eligible": 0,
                    "sent": 0,
                    "skipped_not_due_yet": 0,
                    "errors": [],
                }
            query = query.where(Invoice.id.in_(invoice_ids))
        invoices = (await self.db.execute(query)).scalars().all()

        sent_count = 0
        skipped_count = 0
        errors: list[str] = []

        for inv in invoices:
            effective_due = inv.due_date or inv.issue_date
            days_past_due = (today - effective_due).days
            next_step = (inv.last_dunning_step_sent or 0) + 1

            if next_step > DUNNING_FINAL_STEP:
                continue
            if days_past_due < DUNNING_DAYS_PAST_DUE[next_step]:
                skipped_count += 1
                continue

            try:
                await self.send_dunning_email(inv, next_step, days_past_due)
                sent_count += 1
            except Exception as e:
                errors.append(f"invoice {inv.id}: {e}")
                logger.error(f"Dunning send failed for invoice {inv.id}: {e}")

        await self.db.commit()
        summary = {
            "eligible": len(invoices),
            "sent": sent_count,
            "skipped_not_due_yet": skipped_count,
            "errors": errors,
        }
        logger.info(f"Dunning run complete for org {org_id}: {summary}")
        return summary

    async def send_dunning_email(
        self, invoice: Invoice, step: int, days_past_due: int
    ) -> None:
        """Send a dunning email to every clean recipient on an invoice.

        Multi-recipient invoices (typical for property-managed accounts:
        billing@ + accounting@ on the same customer) get one email each,
        matching the convention from `EstimateWorkflowService`.

        Advances `last_dunning_step_sent` only if AT LEAST one send
        succeeded — so a single bad address doesn't block the whole row,
        but a fully-broken send leaves state alone for tomorrow's retry.
        """
        from src.models.organization import Organization
        from src.services.email_service import EmailService, EmailMessage
        from src.services.email_templates import dunning_email_template
        from src.core.config import settings

        if not (1 <= step <= DUNNING_FINAL_STEP):
            raise ValueError(f"Invalid dunning step {step}")

        recipients = await self._resolve_dunning_recipients(invoice)
        if not recipients:
            logger.warning(f"No dunning recipients for invoice {invoice.id} — skipping send")
            raise RuntimeError("No deliverable recipients")

        org = (await self.db.execute(
            select(Organization).where(Organization.id == invoice.organization_id)
        )).scalar_one_or_none()
        org_name = org.name if org else "Quantum Pools"
        branding_color = getattr(org, "branding_color", None) if org else None
        branding_color = branding_color or "#1a1a2e"

        customer_display = invoice.billing_name or "there"
        if invoice.customer_id:
            customer = (await self.db.execute(
                select(Customer).where(Customer.id == invoice.customer_id)
            )).scalar_one_or_none()
            if customer:
                customer_display = customer.display_name or customer_display

        balance_str = f"${float(invoice.balance):,.2f}"
        pay_url = f"{settings.frontend_url.rstrip('/')}/pay/{invoice.payment_token}"

        # Phase 8: surface an upcoming-late-fee warning on the final-
        # notice email when the org has late fees enabled and the
        # customer hasn't opted out of them. Computed deterministically
        # so the warning amount in the email matches what `run_late_fees`
        # would actually charge.
        late_fee_warning: str | None = None
        if step >= DUNNING_FINAL_STEP and org and org.late_fee_enabled:
            customer_obj = None
            if invoice.customer_id:
                customer_obj = (await self.db.execute(
                    select(Customer).where(Customer.id == invoice.customer_id)
                )).scalar_one_or_none()
            if self._customer_late_fee_eligible(customer_obj, org):
                fee = self._compute_late_fee(org, invoice)
                grace = int(org.late_fee_grace_days or 30)
                if fee > 0:
                    if days_past_due >= grace:
                        late_fee_warning = (
                            f"A late fee of ${fee:,.2f} applies to past-due "
                            f"invoices over {grace} days. Pay now to avoid it."
                        )
                    else:
                        late_fee_warning = (
                            f"A late fee of ${fee:,.2f} will be added to this "
                            f"invoice if it remains unpaid {grace} days past due."
                        )

        subject, text, html = dunning_email_template(
            step=step,
            org_name=org_name,
            customer_name=customer_display,
            invoice_number=invoice.invoice_number or invoice.id[:8],
            balance=balance_str,
            days_past_due=days_past_due,
            pay_url=pay_url,
            branding_color=branding_color,
            late_fee_warning=late_fee_warning,
        )

        email_svc = EmailService(self.db)
        sent_to: list[str] = []
        errors: list[str] = []
        for recipient in recipients:
            msg = EmailMessage(to=recipient, subject=subject, text_body=text, html_body=html)
            result = await email_svc.send_email(invoice.organization_id, msg)
            if getattr(result, "success", False):
                sent_to.append(recipient)
            else:
                err = getattr(result, "error", "unknown error")
                errors.append(f"{recipient}: {err}")

        if not sent_to:
            raise RuntimeError(
                f"All dunning sends failed: {'; '.join(errors) if errors else 'unknown'}"
            )

        invoice.last_dunning_step_sent = step
        invoice.last_dunning_sent_at = datetime.now(timezone.utc)
        logger.info(
            f"Dunning step {step} sent for invoice {invoice.invoice_number} "
            f"({invoice.id}) → {len(sent_to)} recipient(s) ({', '.join(sent_to)}), "
            f"{days_past_due}d past due"
        )
        if errors:
            logger.warning(
                f"Dunning step {step} for invoice {invoice.id}: partial failure — "
                f"{len(errors)} recipient(s) failed: {'; '.join(errors)}"
            )

    async def _resolve_dunning_recipients(self, invoice: Invoice) -> list[str]:
        """Resolve clean, validated recipient addresses for an invoice.

        Walks the same priority chain InvoiceService uses for outbound
        invoice email, but each candidate field is parsed via
        `_parse_recipients` to handle multi-address values, "Name <addr>"
        forms, trailing commas, and similar messy data.

        Priority (first source that yields ANY clean address wins —
        falling through on empty so a junk billing field doesn't mask a
        valid customer.email):
        1. customer_contacts where receives_invoices=True (primary first).
        2. customer_contacts where is_primary=True (regardless of flags).
        3. customers.email (legacy fallback).
        4. invoice.billing_email (non-client invoices).
        """
        from src.models.customer_contact import CustomerContact

        if invoice.customer_id:
            primary_billing = (await self.db.execute(
                select(CustomerContact).where(
                    CustomerContact.customer_id == invoice.customer_id,
                    CustomerContact.receives_invoices == True,  # noqa: E712
                ).order_by(
                    CustomerContact.is_primary.desc(),
                    CustomerContact.created_at.asc(),
                )
            )).scalars().first()
            if primary_billing:
                addrs = _parse_recipients(primary_billing.email)
                if addrs:
                    return addrs

            primary_any = (await self.db.execute(
                select(CustomerContact).where(
                    CustomerContact.customer_id == invoice.customer_id,
                    CustomerContact.is_primary == True,  # noqa: E712
                )
            )).scalars().first()
            if primary_any:
                addrs = _parse_recipients(primary_any.email)
                if addrs:
                    return addrs

            customer = (await self.db.execute(
                select(Customer).where(Customer.id == invoice.customer_id)
            )).scalar_one_or_none()
            if customer:
                addrs = _parse_recipients(customer.email)
                if addrs:
                    return addrs

        return _parse_recipients(invoice.billing_email)

    # ── Late fees (Phase 8) ────────────────────────────────────────────

    @staticmethod
    def _compute_late_fee(org, invoice: Invoice) -> float:
        """Org-policy late fee for an invoice. Returns 0 if disabled or
        misconfigured. Percent type is floored by `late_fee_minimum`."""
        if not org or not org.late_fee_enabled:
            return 0.0
        amount = float(org.late_fee_amount or 0)
        if amount <= 0:
            return 0.0
        if (org.late_fee_type or "flat") == "flat":
            return round(amount, 2)
        invoice_total = float(invoice.total or 0)
        fee = round(invoice_total * amount / 100.0, 2)
        floor = float(org.late_fee_minimum or 0)
        return max(fee, floor) if floor else fee

    @staticmethod
    def _customer_late_fee_eligible(customer: Customer | None, org) -> bool:
        """Per-customer override: NULL → inherit org; True/False → force."""
        if not org or not org.late_fee_enabled:
            return False
        if not customer:
            return True  # non-client invoice — org policy applies
        override = customer.late_fee_override_enabled
        if override is None:
            return True
        return bool(override)

    @staticmethod
    def _has_late_fee_line_item(invoice: Invoice) -> bool:
        """Idempotency check — late fees mark themselves with a description
        prefix and a NULL service_id. Cheap, no schema change."""
        for li in (invoice.line_items or []):
            if li.service_id is None and (li.description or "").startswith("Late fee"):
                return True
        return False

    async def preview_late_fees(self, org_id: str) -> dict:
        """Dry-run version of `run_late_fees`. Returns what WOULD be added
        (one row per past-due, eligible invoice) without writing anything."""
        from src.models.organization import Organization

        org = (await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        today = date.today()

        if not org or not org.late_fee_enabled:
            return {
                "as_of": today.isoformat(),
                "enabled": False,
                "would_apply_count": 0,
                "would_apply": [],
            }

        grace_days = int(org.late_fee_grace_days or 30)
        from sqlalchemy.orm import selectinload
        invoices = (await self.db.execute(
            select(Invoice)
            .where(
                Invoice.organization_id == org_id,
                Invoice.status.in_(DUNNING_ELIGIBLE_STATUSES),
                Invoice.document_type == "invoice",
                Invoice.balance > 0,
                Invoice.pss_invoice_id.is_(None),
            )
            .options(selectinload(Invoice.line_items))
        )).scalars().all()

        would_apply: list[dict] = []
        for inv in invoices:
            effective_due = inv.due_date or inv.issue_date
            days_past_due = (today - effective_due).days
            if days_past_due < grace_days:
                continue
            if self._has_late_fee_line_item(inv):
                continue
            customer = None
            if inv.customer_id:
                customer = (await self.db.execute(
                    select(Customer).where(Customer.id == inv.customer_id)
                )).scalar_one_or_none()
            if not self._customer_late_fee_eligible(customer, org):
                continue
            fee = self._compute_late_fee(org, inv)
            if fee <= 0:
                continue
            would_apply.append({
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "customer_id": inv.customer_id,
                "customer_name": (customer.display_name if customer else inv.billing_name) or "—",
                "balance": round(float(inv.balance or 0), 2),
                "days_past_due": days_past_due,
                "fee": fee,
            })

        would_apply.sort(key=lambda r: -r["days_past_due"])
        return {
            "as_of": today.isoformat(),
            "enabled": True,
            "grace_days": grace_days,
            "fee_type": org.late_fee_type or "flat",
            "fee_amount": float(org.late_fee_amount or 0),
            "fee_minimum": float(org.late_fee_minimum or 0) if org.late_fee_minimum else None,
            "would_apply_count": len(would_apply),
            "would_apply": would_apply,
        }

    async def run_late_fees(
        self, org_id: str, invoice_ids: list[str] | None = None
    ) -> dict:
        """Apply org-policy late fees to past-due, eligible invoices.

        Adds one InvoiceLineItem (description prefixed "Late fee — past
        due since YYYY-MM-DD", service_id NULL) per eligible invoice and
        recomputes totals. Idempotent: invoices that already have a
        late-fee line item are skipped.

        When `invoice_ids` is provided, applies only to that subset
        (intersected with the eligibility filter). Used for selective
        run from the preview UI.
        """
        from src.models.invoice import InvoiceLineItem
        from src.models.organization import Organization
        from sqlalchemy.orm import selectinload

        org = (await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        today = date.today()

        if not org or not org.late_fee_enabled:
            return {
                "as_of": today.isoformat(),
                "enabled": False,
                "applied": 0,
                "skipped": 0,
                "errors": [],
            }

        grace_days = int(org.late_fee_grace_days or 30)
        query = (
            select(Invoice)
            .where(
                Invoice.organization_id == org_id,
                Invoice.status.in_(DUNNING_ELIGIBLE_STATUSES),
                Invoice.document_type == "invoice",
                Invoice.balance > 0,
                Invoice.pss_invoice_id.is_(None),
            )
            .options(selectinload(Invoice.line_items))
        )
        if invoice_ids is not None:
            if not invoice_ids:
                return {
                    "as_of": today.isoformat(),
                    "enabled": True,
                    "applied": 0,
                    "skipped": 0,
                    "errors": [],
                }
            query = query.where(Invoice.id.in_(invoice_ids))
        invoices = (await self.db.execute(query)).scalars().all()

        applied = 0
        skipped = 0
        errors: list[str] = []
        inv_svc = InvoiceService(self.db)

        for inv in invoices:
            effective_due = inv.due_date or inv.issue_date
            days_past_due = (today - effective_due).days
            if days_past_due < grace_days:
                skipped += 1
                continue
            if self._has_late_fee_line_item(inv):
                skipped += 1
                continue
            customer = None
            if inv.customer_id:
                customer = (await self.db.execute(
                    select(Customer).where(Customer.id == inv.customer_id)
                )).scalar_one_or_none()
            if not self._customer_late_fee_eligible(customer, org):
                skipped += 1
                continue
            fee = self._compute_late_fee(org, inv)
            if fee <= 0:
                skipped += 1
                continue

            try:
                next_sort = max(
                    (li.sort_order or 0 for li in inv.line_items),
                    default=0,
                ) + 1
                line = InvoiceLineItem(
                    invoice_id=inv.id,
                    description=f"Late fee — past due since {effective_due.isoformat()}",
                    quantity=1.0,
                    unit_price=fee,
                    amount=fee,
                    is_taxed=False,
                    sort_order=next_sort,
                )
                self.db.add(line)
                inv.line_items.append(line)
                inv_svc._recalculate_totals(inv, list(inv.line_items))
                applied += 1
                logger.info(
                    f"Late fee ${fee:.2f} applied to invoice {inv.invoice_number} "
                    f"({inv.id}), {days_past_due}d past due"
                )
            except Exception as e:
                errors.append(f"invoice {inv.id}: {e}")
                logger.error(f"Late fee apply failed for invoice {inv.id}: {e}")

        await self.db.commit()
        return {
            "as_of": today.isoformat(),
            "enabled": True,
            "applied": applied,
            "skipped": skipped,
            "errors": errors,
        }

    async def get_ar_aging(self, org_id: str) -> dict:
        """A/R aging — outstanding invoices grouped by customer, bucketed by
        days past due (current / 1-30 / 31-60 / 61-90 / 90+).

        Outstanding = status in (sent, revised, viewed, overdue) AND balance > 0.
        Excludes estimates, drafts, paid, written-off, voided.

        Falls back to issue_date when due_date is null. Non-client invoices
        (no customer_id) group under their billing_name.
        """
        from src.models.invoice import InvoiceStatus

        OUTSTANDING_STATUSES = (
            InvoiceStatus.sent.value,
            InvoiceStatus.revised.value,
            InvoiceStatus.viewed.value,
            InvoiceStatus.overdue.value,
        )
        today = date.today()

        invoices = (await self.db.execute(
            select(Invoice).where(
                Invoice.organization_id == org_id,
                Invoice.status.in_(OUTSTANDING_STATUSES),
                Invoice.document_type == "invoice",
                Invoice.balance > 0,
            )
        )).scalars().all()

        # Group by customer_id (or by billing_name for non-client)
        by_key: dict[str, dict] = {}
        for inv in invoices:
            effective_due = inv.due_date or inv.issue_date
            age_days = (today - effective_due).days
            balance = float(inv.balance or 0)

            if age_days <= 0:
                bucket = "current"
            elif age_days <= 30:
                bucket = "days_30"
            elif age_days <= 60:
                bucket = "days_60"
            elif age_days <= 90:
                bucket = "days_90"
            else:
                bucket = "over_90"

            key = inv.customer_id or f"_billing:{inv.billing_name or 'Unknown'}"
            row = by_key.setdefault(key, {
                "customer_id": inv.customer_id,
                "customer_name": None,
                "current": 0.0,
                "days_30": 0.0,
                "days_60": 0.0,
                "days_90": 0.0,
                "over_90": 0.0,
                "total_owed": 0.0,
                "invoice_count": 0,
                "oldest_invoice_age_days": 0,
            })
            row[bucket] += balance
            row["total_owed"] += balance
            row["invoice_count"] += 1
            if age_days > row["oldest_invoice_age_days"]:
                row["oldest_invoice_age_days"] = age_days

        # Resolve customer names in one query
        customer_ids = [k for k in by_key if not k.startswith("_billing:")]
        if customer_ids:
            customers = (await self.db.execute(
                select(Customer).where(Customer.id.in_(customer_ids))
            )).scalars().all()
            name_map = {c.id: c.display_name for c in customers}
            for cid in customer_ids:
                by_key[cid]["customer_name"] = name_map.get(cid, "(deleted customer)")

        for k, row in by_key.items():
            if k.startswith("_billing:"):
                row["customer_name"] = k[len("_billing:"):]

        # Round bucket values to cents and sort by total desc
        rows = []
        for r in by_key.values():
            for k in ("current", "days_30", "days_60", "days_90", "over_90", "total_owed"):
                r[k] = round(r[k], 2)
            rows.append(r)
        rows.sort(key=lambda x: x["total_owed"], reverse=True)

        totals = {
            k: round(sum(r[k] for r in rows), 2)
            for k in ("current", "days_30", "days_60", "days_90", "over_90", "total_owed")
        }
        totals["invoice_count"] = sum(r["invoice_count"] for r in rows)

        return {
            "as_of": today.isoformat(),
            "rows": rows,
            "totals": totals,
        }

    async def _all_properties_held(self, customer_id: str, on_date: date) -> bool:
        """Return True iff customer has >=1 property and ALL active properties
        are on a service hold covering `on_date`. False for customers with
        no properties (let them bill normally — billing wasn't keyed off
        properties before holds were introduced)."""
        # Pull active property IDs for the customer.
        prop_rows = (await self.db.execute(
            select(Property.id).where(
                Property.customer_id == customer_id,
                Property.is_active == True,  # noqa: E712
            )
        )).all()
        if not prop_rows:
            return False
        prop_ids = [r[0] for r in prop_rows]
        held_count = (await self.db.execute(
            select(PropertyHold.property_id).where(
                PropertyHold.property_id.in_(prop_ids),
                PropertyHold.start_date <= on_date,
                PropertyHold.end_date >= on_date,
            ).distinct()
        )).all()
        return len(held_count) >= len(prop_ids)

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
