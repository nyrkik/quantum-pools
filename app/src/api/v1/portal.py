"""Customer-facing portal API.

Cookie-authenticated endpoints for `customer_contacts` to sign in via
magic link and manage their own account: view invoices, payment history,
download receipts. Distinct from the staff JWT auth path.

Cookie name: `qp_portal_session`. Validated on every request via
`CustomerPortalService.get_session` (which slides expiry forward when
the session has been idle ≥ 5 min).
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.models.customer import Customer
from src.models.customer_contact import CustomerContact
from src.models.customer_portal import CustomerPortalSession
from src.models.invoice import Invoice, InvoiceStatus
from src.models.organization import Organization
from src.models.payment import Payment, PaymentStatus
from src.services.customer_portal_service import (
    CustomerPortalService,
    SESSION_TTL_DAYS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal", tags=["portal"])

PORTAL_COOKIE_NAME = "qp_portal_session"

OUTSTANDING_STATUSES = (
    InvoiceStatus.sent.value,
    InvoiceStatus.revised.value,
    InvoiceStatus.viewed.value,
    InvoiceStatus.overdue.value,
)


# ── Cookie helpers ─────────────────────────────────────────────────────


def _set_portal_cookie(
    response: Response, token: str, request: Request | None = None
) -> None:
    is_tunnel = False
    if request:
        host = request.headers.get("host", "")
        origin = request.headers.get("origin", "")
        is_tunnel = (
            "quantumpoolspro.com" in host or "quantumpoolspro.com" in origin
        )

    if is_tunnel:
        secure = True
        domain = settings.cookie_domain
        samesite: Literal["lax", "strict", "none"] = "lax"
    else:
        secure = False
        domain = None
        samesite = "lax"

    response.set_cookie(
        key=PORTAL_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=SESSION_TTL_DAYS * 86400,
        path="/",
        domain=domain,
    )


def _clear_portal_cookie(response: Response, request: Request | None = None) -> None:
    domain = (
        settings.cookie_domain
        if request
        and "quantumpoolspro.com"
        in (request.headers.get("host", "") + request.headers.get("origin", ""))
        else None
    )
    response.delete_cookie(key=PORTAL_COOKIE_NAME, path="/", domain=domain)


# ── Auth dependency ────────────────────────────────────────────────────


async def get_portal_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CustomerPortalSession:
    """Read portal cookie, validate, slide expiry. 401 if missing/invalid."""
    token = request.cookies.get(PORTAL_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
        )

    svc = CustomerPortalService(db)
    ip = request.client.host if request.client else None
    session = await svc.get_session(token, refresh=True, ip=ip)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    return session


# ── Public endpoints (no auth required) ────────────────────────────────


class RequestLinkBody(BaseModel):
    email: EmailStr


@router.post("/request-link", status_code=status.HTTP_200_OK)
async def request_link(
    body: RequestLinkBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Email a sign-in link to the address. ALWAYS returns {ok: true},
    regardless of whether the email matches a contact — prevents email
    enumeration. Caller-side rate-limiting recommended."""
    svc = CustomerPortalService(db)
    ip = request.client.host if request.client else None
    await svc.request_magic_link(body.email, requested_ip=ip)
    return {"ok": True}


class ConsumeBody(BaseModel):
    token: str


@router.post("/consume", status_code=status.HTTP_200_OK)
async def consume_link(
    body: ConsumeBody,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Trade a magic-link token for a session cookie."""
    svc = CustomerPortalService(db)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session = await svc.consume_magic_link(body.token, ip=ip, user_agent=ua)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in link is invalid or expired",
        )
    _set_portal_cookie(response, session.token, request)
    return {"ok": True}


# ── Auth-required endpoints ────────────────────────────────────────────


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: CustomerPortalSession = Depends(get_portal_session),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current session and clear the cookie."""
    svc = CustomerPortalService(db)
    await svc.revoke_session(session.token)
    _clear_portal_cookie(response, request)
    return {"ok": True}


@router.get("/me")
async def me(
    session: CustomerPortalSession = Depends(get_portal_session),
    db: AsyncSession = Depends(get_db),
):
    """Customer + contact + org summary for portal landing."""
    customer = (await db.execute(
        select(Customer).where(Customer.id == session.customer_id)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    contact = (await db.execute(
        select(CustomerContact).where(CustomerContact.id == session.contact_id)
    )).scalar_one_or_none()

    org = (await db.execute(
        select(Organization).where(Organization.id == session.organization_id)
    )).scalar_one_or_none()

    open_invoice_count = (await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.customer_id == customer.id,
            Invoice.status.in_(OUTSTANDING_STATUSES),
            Invoice.balance > 0,
            Invoice.document_type == "invoice",
        )
    )).scalar() or 0

    open_balance = (await db.execute(
        select(func.coalesce(func.sum(Invoice.balance), 0.0)).where(
            Invoice.customer_id == customer.id,
            Invoice.status.in_(OUTSTANDING_STATUSES),
            Invoice.balance > 0,
            Invoice.document_type == "invoice",
        )
    )).scalar() or 0.0

    return {
        "contact": {
            "id": contact.id if contact else None,
            "first_name": contact.first_name if contact else None,
            "last_name": contact.last_name if contact else None,
            "email": contact.email if contact else None,
        },
        "customer": {
            "id": customer.id,
            "display_name": customer.display_name,
            "company_name": customer.company_name,
        },
        "org": {
            "id": org.id if org else None,
            "name": org.name if org else "Quantum Pools",
            "branding_color": getattr(org, "branding_color", None) if org else None,
            "logo_url": getattr(org, "logo_url", None) if org else None,
        },
        "open_invoice_count": open_invoice_count,
        "open_balance": round(float(open_balance), 2),
        "has_card_on_file": bool(customer.stripe_payment_method_id),
        "card_last4": customer.stripe_card_last4,
        "card_brand": customer.stripe_card_brand,
        "autopay_enabled": customer.autopay_enabled,
    }


@router.get("/invoices")
async def list_invoices(
    status_filter: Literal["open", "paid", "all"] = "open",
    session: CustomerPortalSession = Depends(get_portal_session),
    db: AsyncSession = Depends(get_db),
):
    """List invoices for this customer."""
    query = select(Invoice).where(
        Invoice.customer_id == session.customer_id,
        Invoice.document_type == "invoice",
    )
    if status_filter == "open":
        query = query.where(
            Invoice.status.in_(OUTSTANDING_STATUSES),
            Invoice.balance > 0,
        )
    elif status_filter == "paid":
        query = query.where(Invoice.status == InvoiceStatus.paid.value)

    rows = (await db.execute(
        query.order_by(Invoice.issue_date.desc())
    )).scalars().all()

    return {
        "items": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "subject": inv.subject,
                "status": inv.status,
                "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "paid_date": inv.paid_date.isoformat() if inv.paid_date else None,
                "total": float(inv.total or 0),
                "amount_paid": float(inv.amount_paid or 0),
                "balance": float(inv.balance or 0),
                "po_number": inv.po_number,
                # payment_token lets the portal "Pay" button link directly to
                # the existing /pay/{token} page without minting a new flow.
                "payment_token": inv.payment_token,
            }
            for inv in rows
        ]
    }


class AutopayBody(BaseModel):
    enabled: bool


@router.put("/autopay")
async def set_autopay(
    body: AutopayBody,
    session: CustomerPortalSession = Depends(get_portal_session),
    db: AsyncSession = Depends(get_db),
):
    """Toggle autopay on this customer.

    Refuses to enable autopay when no payment method is on file — the
    setting would be misleading (existing customers had this exact bug
    pre-2026-04-13). Enable a method first via the portal Methods tab.
    """
    customer = (await db.execute(
        select(Customer).where(Customer.id == session.customer_id)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if body.enabled and not customer.stripe_payment_method_id:
        raise HTTPException(
            status_code=400,
            detail="Add a payment method before enabling autopay.",
        )
    customer.autopay_enabled = body.enabled
    await db.commit()
    return {"autopay_enabled": customer.autopay_enabled}


@router.get("/payments")
async def list_payments(
    session: CustomerPortalSession = Depends(get_portal_session),
    db: AsyncSession = Depends(get_db),
):
    """Payment history for this customer."""
    rows = (await db.execute(
        select(Payment).where(
            Payment.customer_id == session.customer_id,
            Payment.status == PaymentStatus.completed.value,
        ).order_by(Payment.payment_date.desc(), Payment.created_at.desc())
    )).scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "amount": float(p.amount or 0),
                "payment_method": p.payment_method,
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                "reference_number": p.reference_number,
                "is_autopay": p.is_autopay,
                "invoice_id": p.invoice_id,
            }
            for p in rows
        ]
    }
