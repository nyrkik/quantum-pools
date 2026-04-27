"""Payment reconciliation API — Phase 1.

Three list endpoints + three action endpoints, all gated by
`invoices.create` (the same permission that lets a user record a
manual payment elsewhere in the product).

GET  /v1/reconciliation/pending-checks      — Payments with status=pending
GET  /v1/reconciliation/needs-review        — ParsedPayments with match_status=proposed
GET  /v1/reconciliation/unmatched           — ParsedPayments with match_status=unmatched
GET  /v1/reconciliation/recent-auto-matches — last 30d auto_matched audit (read-only)

POST /v1/reconciliation/payments/{payment_id}/mark-received
POST /v1/reconciliation/parsed/{parsed_id}/match     body: {invoice_id}
POST /v1/reconciliation/parsed/{parsed_id}/dismiss
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import OrgUserContext, require_permissions
from src.core.database import get_db
from src.core.exceptions import NotFoundError, ValidationError
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.invoice import Invoice, InvoiceStatus
from src.models.parsed_payment import ParsedPayment, ParsedPaymentStatus
from src.models.payment import Payment, PaymentStatus
from src.services.payment_service import PaymentService


router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _payment_summary(p: Payment, customer_name: str | None) -> dict:
    return {
        "id": p.id,
        "amount": float(p.amount),
        "payment_method": p.payment_method,
        "payment_date": p.payment_date.isoformat() if p.payment_date else None,
        "status": p.status,
        "reference_number": p.reference_number,
        "notes": p.notes,
        "source_message_id": p.source_message_id,
        "customer_id": p.customer_id,
        "customer_name": customer_name,
        "invoice_id": p.invoice_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _parsed_summary(pp: ParsedPayment, *, candidate_invoice: Invoice | None = None,
                    thread_id: str | None = None) -> dict:
    return {
        "id": pp.id,
        "processor": pp.processor,
        "amount": float(pp.amount) if pp.amount is not None else None,
        "payer_name": pp.payer_name,
        "property_hint": pp.property_hint,
        "invoice_hint": pp.invoice_hint,
        "payment_method": pp.payment_method,
        "payment_date": pp.payment_date.isoformat() if pp.payment_date else None,
        "reference_number": pp.reference_number,
        "agent_message_id": pp.agent_message_id,
        "thread_id": thread_id,
        "match_status": pp.match_status,
        "match_confidence": pp.match_confidence,
        "match_reasoning": pp.match_reasoning,
        "candidate_invoice_id": candidate_invoice.id if candidate_invoice else None,
        "candidate_invoice_number": candidate_invoice.invoice_number if candidate_invoice else None,
        "candidate_invoice_total": float(candidate_invoice.total) if candidate_invoice else None,
        "created_at": pp.created_at.isoformat() if pp.created_at else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _customer_name_map(db: AsyncSession, org_id: str, customer_ids: list[str]) -> dict[str, str]:
    if not customer_ids:
        return {}
    rows = (await db.execute(
        select(Customer.id, Customer.first_name, Customer.last_name, Customer.company_name)
        .where(
            Customer.organization_id == org_id,
            Customer.id.in_(set(customer_ids)),
        )
    )).all()
    out: dict[str, str] = {}
    for cid, fn, ln, company in rows:
        out[cid] = company or f"{fn or ''} {ln or ''}".strip() or "(unknown)"
    return out


async def _thread_id_for_messages(db: AsyncSession, message_ids: list[str]) -> dict[str, str]:
    if not message_ids:
        return {}
    rows = (await db.execute(
        select(AgentMessage.id, AgentMessage.thread_id)
        .where(AgentMessage.id.in_(set(message_ids)))
    )).all()
    return {mid: tid for mid, tid in rows if tid}


# ---------------------------------------------------------------------------
# List endpoints
# ---------------------------------------------------------------------------


@router.get("/pending-checks")
async def list_pending_checks(
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (await db.execute(
        select(Payment)
        .where(
            Payment.organization_id == ctx.organization_id,
            Payment.status == PaymentStatus.pending.value,
        )
        .order_by(desc(Payment.payment_date), desc(Payment.created_at))
        .limit(200)
    )).scalars().all()
    name_map = await _customer_name_map(db, ctx.organization_id, [p.customer_id for p in rows if p.customer_id])
    return {"items": [_payment_summary(p, name_map.get(p.customer_id or "")) for p in rows]}


@router.get("/needs-review")
async def list_needs_review(
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (await db.execute(
        select(ParsedPayment, Invoice)
        .outerjoin(Invoice, Invoice.id == ParsedPayment.matched_invoice_id)
        .where(
            ParsedPayment.organization_id == ctx.organization_id,
            ParsedPayment.match_status == ParsedPaymentStatus.proposed.value,
        )
        .order_by(desc(ParsedPayment.match_confidence), desc(ParsedPayment.created_at))
        .limit(200)
    )).all()
    msg_to_thread = await _thread_id_for_messages(db, [pp.agent_message_id for pp, _ in rows])
    return {
        "items": [
            _parsed_summary(pp, candidate_invoice=inv, thread_id=msg_to_thread.get(pp.agent_message_id))
            for pp, inv in rows
        ],
    }


@router.get("/unmatched")
async def list_unmatched(
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (await db.execute(
        select(ParsedPayment)
        .where(
            ParsedPayment.organization_id == ctx.organization_id,
            ParsedPayment.match_status == ParsedPaymentStatus.unmatched.value,
        )
        .order_by(desc(ParsedPayment.created_at))
        .limit(200)
    )).scalars().all()
    msg_to_thread = await _thread_id_for_messages(db, [pp.agent_message_id for pp in rows])
    return {
        "items": [
            _parsed_summary(pp, thread_id=msg_to_thread.get(pp.agent_message_id))
            for pp in rows
        ],
    }


@router.get("/recent-auto-matches")
async def list_recent_auto_matches(
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = (await db.execute(
        select(ParsedPayment, Invoice)
        .outerjoin(Invoice, Invoice.id == ParsedPayment.matched_invoice_id)
        .where(
            ParsedPayment.organization_id == ctx.organization_id,
            ParsedPayment.match_status == ParsedPaymentStatus.auto_matched.value,
            ParsedPayment.created_at >= cutoff,
        )
        .order_by(desc(ParsedPayment.created_at))
        .limit(200)
    )).all()
    msg_to_thread = await _thread_id_for_messages(db, [pp.agent_message_id for pp, _ in rows])
    return {
        "items": [
            _parsed_summary(pp, candidate_invoice=inv, thread_id=msg_to_thread.get(pp.agent_message_id))
            for pp, inv in rows
        ],
    }


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------


class ManualMatchBody(BaseModel):
    invoice_id: str = Field(min_length=36, max_length=36)


@router.post("/payments/{payment_id}/mark-received")
async def mark_payment_received(
    payment_id: str,
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pending check arrived — flip Payment to completed, bump invoice.
    Idempotent on already-completed payments."""
    try:
        payment = await PaymentService(db).mark_received(
            org_id=ctx.organization_id, payment_id=payment_id,
        )
    except NotFoundError:
        raise HTTPException(404, "payment not found")
    except ValidationError as e:
        raise HTTPException(409, str(e))
    await db.commit()
    name_map = await _customer_name_map(db, ctx.organization_id, [payment.customer_id] if payment.customer_id else [])
    return _payment_summary(payment, name_map.get(payment.customer_id or ""))


@router.post("/parsed/{parsed_id}/match")
async def manual_match(
    parsed_id: str,
    body: ManualMatchBody,
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """User picked an invoice for an unmatched/proposed parsed payment.
    Creates the Payment with the same pending/completed lifecycle the
    matcher would have used. Marks the row manual_matched."""
    pp = await db.get(ParsedPayment, parsed_id)
    if pp is None or pp.organization_id != ctx.organization_id:
        raise HTTPException(404, "parsed payment not found")
    if pp.match_status not in (
        ParsedPaymentStatus.unmatched.value,
        ParsedPaymentStatus.proposed.value,
    ):
        raise HTTPException(409, f"parsed payment is in terminal status {pp.match_status!r}")

    invoice = await db.get(Invoice, body.invoice_id)
    if invoice is None or invoice.organization_id != ctx.organization_id:
        raise HTTPException(404, "invoice not found")
    if pp.amount is None:
        raise HTTPException(422, "parsed payment has no amount — cannot create Payment")

    is_check = (pp.payment_method or "").lower() == "check"
    payment_status = PaymentStatus.pending.value if is_check else PaymentStatus.completed.value

    from datetime import date as _date
    payment = await PaymentService(db).create(
        org_id=ctx.organization_id,
        customer_id=invoice.customer_id,
        invoice_id=invoice.id,
        amount=float(pp.amount),
        payment_method=pp.payment_method or "other",
        payment_date=pp.payment_date or _date.today(),
        status=payment_status,
        reference_number=pp.reference_number,
        notes=(
            f"Manual match from {pp.processor} payment "
            f"#{pp.reference_number or '?'} ({pp.property_hint or pp.payer_name or '?'})."
        ),
        recorded_by=f"manual:{ctx.user.first_name or ctx.user.email}",
        source_message_id=pp.agent_message_id,
    )

    pp.match_status = ParsedPaymentStatus.manual_matched.value
    pp.matched_invoice_id = invoice.id
    pp.payment_id = payment.id
    pp.match_reasoning = (pp.match_reasoning or "") + f" | manual by {ctx.user.email}"
    pp.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"parsed_payment_id": pp.id, "payment_id": payment.id, "status": payment.status}


@router.post("/parsed/{parsed_id}/dismiss")
async def dismiss_parsed(
    parsed_id: str,
    ctx: OrgUserContext = Depends(require_permissions("invoices.create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """User dismissed an unmatched/proposed parsed payment — won't
    surface again."""
    pp = await db.get(ParsedPayment, parsed_id)
    if pp is None or pp.organization_id != ctx.organization_id:
        raise HTTPException(404, "parsed payment not found")
    if pp.match_status not in (
        ParsedPaymentStatus.unmatched.value,
        ParsedPaymentStatus.proposed.value,
    ):
        raise HTTPException(409, f"parsed payment is in terminal status {pp.match_status!r}")
    pp.match_status = ParsedPaymentStatus.ignored.value
    pp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"parsed_payment_id": pp.id, "match_status": pp.match_status}
