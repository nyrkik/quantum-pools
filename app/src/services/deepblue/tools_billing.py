"""DeepBlue tools — Billing domain."""

import logging

from sqlalchemy import select, desc

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_get_billing_documents(inp: dict, ctx: ToolContext) -> dict:
    """List invoices and/or estimates for a customer or the org."""
    from src.models.invoice import Invoice

    doc_type = inp.get("document_type", "invoice")

    query = select(Invoice).where(Invoice.organization_id == ctx.org_id)
    if doc_type != "all":
        query = query.where(Invoice.document_type == doc_type)

    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(Invoice.customer_id == cust_id)
    if inp.get("status"):
        query = query.where(Invoice.status == inp["status"])
    query = query.order_by(desc(Invoice.issue_date)).limit(inp.get("limit", 10))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "results": [
            {
                "id": r.id,
                "number": r.invoice_number,
                "type": r.document_type,
                "status": r.status,
                "subject": r.subject,
                "total": float(r.total or 0),
                "balance": float(r.balance or 0),
                "issue_date": r.issue_date.isoformat() if r.issue_date else None,
                "due_date": r.due_date.isoformat() if r.due_date else None,
            }
            for r in rows
        ],
    }


async def _exec_get_billing_terms(inp: dict, ctx: ToolContext) -> dict:
    from src.models.org_cost_settings import OrgCostSettings
    from src.models.organization import Organization
    from src.services.billing_service import BillingService

    settings = (await ctx.db.execute(
        select(OrgCostSettings).where(OrgCostSettings.organization_id == ctx.org_id)
    )).scalar_one_or_none()
    if not settings:
        return {"error": "No billing settings configured"}

    org = (await ctx.db.execute(
        select(Organization).where(Organization.id == ctx.org_id)
    )).scalar_one_or_none()

    return {
        "payment_terms_days": settings.payment_terms_days,
        "estimate_validity_days": settings.estimate_validity_days,
        "late_fee_clause": BillingService.late_fee_clause(org),
        "late_fee_enabled": bool(org and org.late_fee_enabled),
        "warranty_days": settings.warranty_days,
        "billable_labor_rate": float(settings.billable_labor_rate or 0),
        "default_parts_markup_pct": float(settings.default_parts_markup_pct or 0),
        "auto_approve_threshold": float(settings.auto_approve_threshold or 0),
        "separate_invoice_threshold": float(settings.separate_invoice_threshold or 0),
        "estimate_terms": settings.estimate_terms,
    }


async def _exec_get_service_tiers(inp: dict, ctx: ToolContext) -> dict:
    from src.models.service_tier import ServiceTier

    rows = (await ctx.db.execute(
        select(ServiceTier).where(
            ServiceTier.organization_id == ctx.org_id,
            ServiceTier.is_active == True,
        ).order_by(ServiceTier.sort_order)
    )).scalars().all()
    return {
        "tiers": [
            {
                "name": t.name,
                "base_rate": float(t.base_rate or 0),
                "estimated_minutes": t.estimated_minutes,
                "is_default": t.is_default,
                "description": t.description,
                "includes": [
                    k.replace("includes_", "")
                    for k in ("includes_chems", "includes_skim", "includes_baskets",
                              "includes_vacuum", "includes_brush", "includes_equipment_check")
                    if getattr(t, k, False)
                ],
            }
            for t in rows
        ],
    }


async def _exec_get_payments(inp: dict, ctx: ToolContext) -> dict:
    from src.models.payment import Payment

    query = select(Payment).where(Payment.organization_id == ctx.org_id)
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(Payment.customer_id == cust_id)
    query = query.order_by(desc(Payment.payment_date)).limit(inp.get("limit", 10))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "payments": [
            {
                "amount": float(r.amount or 0),
                "method": r.payment_method,
                "date": r.payment_date.isoformat() if r.payment_date else None,
                "status": r.status,
                "reference": r.reference_number,
                "invoice_id": r.invoice_id,
            }
            for r in rows
        ],
    }


EXECUTORS = {
    "get_billing_documents": _exec_get_billing_documents,
    "get_billing_terms": _exec_get_billing_terms,
    "get_service_tiers": _exec_get_service_tiers,
    "get_payments": _exec_get_payments,
}
