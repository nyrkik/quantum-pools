"""PaymentMatcher — Phase 1 payment reconciliation.

Score each ParsedPayment against the org's open invoices, decide
auto-match | propose | leave-unmatched, and (on auto-match) create the
Payment via PaymentService with the right pending/completed status.

Scoring rules (see `docs/payment-reconciliation-spec.md` §3.5):

  invoice# match (parser supplied invoice_hint == Invoice.invoice_number) → 1.0
  amount exact + customer fuzzy ≥85, single candidate                    → 0.95
  amount exact + customer fuzzy ≥85, multiple candidates                 → 0.70
  amount within $0.01 + property hint matches Property.name              → 0.90
  amount only                                                            → 0.50

Decision threshold: confidence ≥ 0.90 AND only one candidate at that
top score → auto-match. Anything else gets `proposed` status (for
ambiguous, score ∈ [0.50, 0.90)) or `unmatched` (no candidate ≥ 0.50).

Pending vs completed: `payment_method == "check"` → Payment.status =
pending (funds in transit; user clicks "Mark received" later).
Anything else → completed immediately.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.invoice import Invoice, InvoiceStatus
from src.models.parsed_payment import ParsedPayment, ParsedPaymentStatus
from src.models.payment import PaymentStatus
from src.models.property import Property
from src.models.customer import Customer
from src.services.payment_service import PaymentService

logger = logging.getLogger(__name__)


AUTO_MATCH_FLOOR = 0.90
PROPOSE_FLOOR = 0.50
FUZZY_NAME_THRESHOLD = 85  # rapidfuzz token_set_ratio 0-100


_OPEN_STATUSES = (
    InvoiceStatus.sent.value,
    InvoiceStatus.viewed.value,
    InvoiceStatus.overdue.value,
    InvoiceStatus.revised.value,
)


@dataclass
class MatchCandidate:
    invoice: Invoice
    confidence: float
    reasoning: str


async def match_parsed_payments(
    db: AsyncSession,
    *,
    parsed_payments: list[ParsedPayment],
) -> None:
    """Score, decide, and execute auto-matches for the given parsed
    payments. Mutates parsed_payments rows in-place; commits via the
    caller's transaction."""
    if not parsed_payments:
        return
    org_id = parsed_payments[0].organization_id

    open_invoices = await _load_open_invoices(db, org_id)
    if not open_invoices:
        # No open invoices to match against — leave all rows unmatched.
        for pp in parsed_payments:
            pp.match_status = ParsedPaymentStatus.unmatched.value
        await db.flush()
        return

    properties_by_id = await _load_properties(
        db, org_id, customer_ids=[inv.customer_id for inv in open_invoices if inv.customer_id],
    )
    customers_by_id = await _load_customers(
        db, org_id, customer_ids=list({inv.customer_id for inv in open_invoices if inv.customer_id}),
    )

    for pp in parsed_payments:
        candidates = _score_candidates(
            pp,
            invoices=open_invoices,
            properties=properties_by_id,
            customers=customers_by_id,
        )
        await _apply_decision(db, pp, candidates)
    await db.flush()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _load_open_invoices(db: AsyncSession, org_id: str) -> list[Invoice]:
    rows = (await db.execute(
        select(Invoice).where(
            Invoice.organization_id == org_id,
            Invoice.status.in_(_OPEN_STATUSES),
            Invoice.balance > 0,
        )
    )).scalars().all()
    return list(rows)


async def _load_properties(
    db: AsyncSession, org_id: str, *, customer_ids: list[str],
) -> dict[str, list[Property]]:
    if not customer_ids:
        return {}
    rows = (await db.execute(
        select(Property).where(
            Property.organization_id == org_id,
            Property.customer_id.in_(set(customer_ids)),
        )
    )).scalars().all()
    out: dict[str, list[Property]] = {}
    for p in rows:
        out.setdefault(p.customer_id, []).append(p)
    return out


async def _load_customers(
    db: AsyncSession, org_id: str, *, customer_ids: list[str],
) -> dict[str, Customer]:
    if not customer_ids:
        return {}
    rows = (await db.execute(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.id.in_(set(customer_ids)),
        )
    )).scalars().all()
    return {c.id: c for c in rows}


def _customer_haystacks(c: Customer) -> list[str]:
    """All viable string representations of a customer, lowercased.

    Sapphire's customer shape stores the property name in `first_name`
    (e.g. company_name="AIR", first_name="Slate Creek Apartments") so a
    fuzzy match against ONLY `company_name` would miss every payment
    where Entrata's `payer_name` is the property. We score the parsed
    hint against every representation and take the max — robust to:
      - B2B with property in first_name (Sapphire's shape)
      - B2B with the contact person in first_name
      - residential where company_name is empty
    """
    bits = []
    if c.company_name:
        bits.append(c.company_name.lower())
    fn = (c.first_name or "").strip().lower()
    ln = (c.last_name or "").strip().lower()
    if fn:
        bits.append(fn)
    if ln:
        bits.append(ln)
    if fn and ln:
        bits.append(f"{fn} {ln}")
    if c.company_name and fn:
        bits.append(f"{c.company_name.lower()} {fn}")
    return bits


def _best_fuzzy_score(needle: str, haystacks: list[str]) -> int:
    if not needle or not haystacks:
        return 0
    return max((fuzz.token_set_ratio(needle, h) for h in haystacks), default=0)


def _score_candidates(
    pp: ParsedPayment,
    *,
    invoices: list[Invoice],
    properties: dict[str, list[Property]],
    customers: dict[str, Customer],
) -> list[MatchCandidate]:
    """Returns scored candidates sorted descending. Empty list when
    nothing scored above PROPOSE_FLOOR."""
    candidates: list[MatchCandidate] = []
    parsed_amount = float(pp.amount) if pp.amount is not None else None
    payer_lower = (pp.payer_name or "").lower().strip()
    property_lower = (pp.property_hint or "").lower().strip()

    for inv in invoices:
        score = 0.0
        reasoning_parts: list[str] = []

        # Invoice number exact match
        if pp.invoice_hint and inv.invoice_number and pp.invoice_hint == inv.invoice_number:
            score = 1.0
            reasoning_parts.append(f"invoice# {pp.invoice_hint} exact")

        # Amount + customer/property fuzzy
        if parsed_amount is not None and abs(parsed_amount - (inv.total or 0)) < 0.01:
            customer = customers.get(inv.customer_id)
            haystacks = _customer_haystacks(customer) if customer else []

            # Score parser's payer + property hints against EVERY customer
            # representation. Sapphire stores property names in
            # Customer.first_name; standard SaaS shape has them in
            # Customer.company_name. We don't care which — best score wins.
            payer_score = _best_fuzzy_score(payer_lower, haystacks)
            property_score = _best_fuzzy_score(property_lower, haystacks)
            best_customer_score = max(payer_score, property_score)

            if best_customer_score >= FUZZY_NAME_THRESHOLD:
                if score < 0.95:
                    score = 0.95
                    reasoning_parts.append(
                        f"amount=${parsed_amount:.2f} + customer fuzzy={best_customer_score}"
                    )

            # Amount + named-Property fuzzy (separate path for orgs that
            # actually use Property.name — currently rare in Sapphire, but
            # the right architecture for the 1,000th customer).
            if property_lower:
                props = properties.get(inv.customer_id, [])
                best_prop_score = 0
                for p in props:
                    if not p.name:
                        continue
                    s = fuzz.token_set_ratio(property_lower, p.name.lower())
                    if s > best_prop_score:
                        best_prop_score = s
                if best_prop_score >= FUZZY_NAME_THRESHOLD and score < 0.90:
                    score = 0.90
                    reasoning_parts.append(
                        f"amount + property fuzzy={best_prop_score}"
                    )

            # Amount only — never auto-match, but rank as a propose candidate
            if score < 0.50:
                score = 0.50
                reasoning_parts.append(f"amount only=${parsed_amount:.2f}")

        if score >= PROPOSE_FLOOR:
            candidates.append(MatchCandidate(
                invoice=inv,
                confidence=score,
                reasoning="; ".join(reasoning_parts),
            ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


async def _apply_decision(
    db: AsyncSession,
    pp: ParsedPayment,
    candidates: list[MatchCandidate],
) -> None:
    if not candidates:
        pp.match_status = ParsedPaymentStatus.unmatched.value
        return

    top = candidates[0]
    # Auto-match condition: top score ≥ floor AND no second candidate
    # tied/close at the same level (multiple-candidates dilution).
    second_close = (
        len(candidates) > 1
        and candidates[1].confidence >= AUTO_MATCH_FLOOR
    )
    if top.confidence >= AUTO_MATCH_FLOOR and not second_close:
        await _auto_match(db, pp, top)
    elif top.confidence >= PROPOSE_FLOOR:
        pp.match_status = ParsedPaymentStatus.proposed.value
        pp.matched_invoice_id = top.invoice.id
        pp.match_confidence = top.confidence
        pp.match_reasoning = top.reasoning
    else:
        pp.match_status = ParsedPaymentStatus.unmatched.value


async def _auto_match(
    db: AsyncSession,
    pp: ParsedPayment,
    candidate: MatchCandidate,
) -> None:
    invoice = candidate.invoice
    if pp.amount is None:
        # Defensive — auto_match shouldn't fire without an amount, but bail.
        pp.match_status = ParsedPaymentStatus.proposed.value
        pp.matched_invoice_id = invoice.id
        pp.match_confidence = candidate.confidence
        pp.match_reasoning = candidate.reasoning
        return

    is_check = (pp.payment_method or "").lower() == "check"
    payment_status = (
        PaymentStatus.pending.value if is_check else PaymentStatus.completed.value
    )

    payment_date = pp.payment_date or date.today()
    notes = (
        f"Auto-matched from {pp.processor} payment "
        f"#{pp.reference_number or '?'} ({pp.property_hint or pp.payer_name or '?'})."
    )

    payment = await PaymentService(db).create(
        org_id=pp.organization_id,
        customer_id=invoice.customer_id,
        invoice_id=invoice.id,
        amount=float(pp.amount),
        payment_method=pp.payment_method or "other",
        payment_date=payment_date,
        status=payment_status,
        reference_number=pp.reference_number,
        notes=notes,
        recorded_by=f"workflow:payment_match:{pp.processor}",
        source_message_id=pp.agent_message_id,
    )

    pp.match_status = ParsedPaymentStatus.auto_matched.value
    pp.matched_invoice_id = invoice.id
    pp.payment_id = payment.id
    pp.match_confidence = candidate.confidence
    pp.match_reasoning = candidate.reasoning
    pp.updated_at = datetime.now(timezone.utc)

    # Notification — Brian wants to stay aware of auto-matches without
    # checking the surface daily. Non-blocking.
    try:
        from src.utils.notify import send_ntfy
        send_ntfy(
            title="Payment auto-matched",
            body=(
                f"${float(pp.amount):,.2f} from "
                f"{pp.payer_name or pp.property_hint or 'unknown'} "
                f"→ {invoice.invoice_number or invoice.id[:8]} "
                f"({'pending check' if is_check else 'received'})"
            ),
            priority="default",
            tags="moneybag",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("payment auto-match ntfy failed: %s", e)
