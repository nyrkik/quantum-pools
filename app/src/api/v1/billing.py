"""Billing and subscription endpoints."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.services.feature_service import FeatureService
from src.services.billing_service import BillingService
from src.schemas.billing import (
    FeatureResponse,
    FeatureTierResponse,
    OrgSubscriptionResponse,
    SubscriptionSummaryResponse,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/features", response_model=list[FeatureResponse])
async def list_features(db: AsyncSession = Depends(get_db)):
    """Public endpoint — feature catalog."""
    service = FeatureService(db)
    features = await service.get_feature_catalog()
    result = []
    for f in features:
        tiers = [
            FeatureTierResponse.model_validate(t)
            for t in sorted(f.tiers, key=lambda t: t.sort_order)
        ] if f.tiers else []
        result.append(FeatureResponse(
            id=f.id,
            slug=f.slug,
            name=f.name,
            description=f.description,
            category=f.category,
            is_base=f.is_base,
            price_cents=f.price_cents,
            billing_type=f.billing_type,
            sort_order=f.sort_order,
            tiers=tiers,
        ))
    return result


@router.get("/subscription", response_model=SubscriptionSummaryResponse)
async def get_subscription(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get org's current subscriptions."""
    service = FeatureService(db)
    subs = await service.get_org_subscriptions(ctx.organization_id)
    slugs = await service.get_org_active_feature_slugs(ctx.organization_id)

    items = []
    total = 0
    for s in subs:
        feature = s.feature
        tier = s.feature_tier
        if feature and s.stripe_status in ("active", "trialing", "past_due"):
            if tier:
                total += tier.price_cents
            else:
                total += feature.price_cents

        items.append(OrgSubscriptionResponse(
            id=s.id,
            feature_id=s.feature_id,
            feature_slug=feature.slug if feature else "",
            feature_name=feature.name if feature else "",
            feature_tier_id=s.feature_tier_id,
            tier_slug=tier.slug if tier else None,
            tier_name=tier.name if tier else None,
            stripe_status=s.stripe_status,
            current_period_start=s.current_period_start,
            current_period_end=s.current_period_end,
            canceled_at=s.canceled_at,
        ))

    return SubscriptionSummaryResponse(
        subscriptions=items,
        feature_slugs=slugs,
        total_monthly_cents=total,
    )


# ── Recurring Billing Admin Endpoints ─────────────────────────────


@router.get("/stats")
async def get_billing_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Billing dashboard stats."""
    svc = BillingService(db)
    return await svc.get_billing_stats(ctx.organization_id)


@router.get("/upcoming")
async def get_upcoming_billing(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Customers due for billing in the next 7 days."""
    svc = BillingService(db)
    return await svc.get_upcoming_billing(ctx.organization_id)


@router.get("/failed-payments")
async def get_failed_payments(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Recent failed autopay attempts."""
    svc = BillingService(db)
    return await svc.get_failed_payments(ctx.organization_id)


@router.post("/generate")
async def trigger_billing_cycle(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger billing cycle for the org. Owner only."""
    svc = BillingService(db)
    result = await svc.generate_recurring_invoices(ctx.organization_id)
    return result


@router.post("/retry-payments")
async def trigger_payment_retries(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger payment retries. Owner only."""
    svc = BillingService(db)
    result = await svc.retry_failed_payments(ctx.organization_id)
    return result


class DunningRunBody(BaseModel):
    invoice_ids: list[str] | None = None


@router.post("/dunning/run")
async def trigger_dunning(
    dry_run: bool = True,
    body: DunningRunBody | None = None,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the dunning sequence for this org. Owner only.

    Defaults to ?dry_run=true — returns what WOULD be sent without
    sending or advancing state. Pass ?dry_run=false to actually fire
    the emails.

    Body `{invoice_ids: [...]}` restricts the run to those invoices
    (intersected with the standard eligibility filter). Omit to act
    on all eligible.

    The daily auto-scheduler in agent_poller is intentionally
    commented out — review this endpoint's dry-run output before
    enabling automatic dunning.
    """
    svc = BillingService(db)
    invoice_ids = body.invoice_ids if body else None
    if dry_run:
        return {"mode": "dry_run", **await svc.preview_dunning_sequence(ctx.organization_id)}
    return {
        "mode": "live",
        **await svc.run_dunning_sequence(ctx.organization_id, invoice_ids=invoice_ids),
    }


@router.get("/ar-aging")
async def get_ar_aging(
    format: str = "json",
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """A/R aging — outstanding invoices grouped by customer, bucketed by
    days past due. ?format=csv returns a downloadable CSV."""
    svc = BillingService(db)
    data = await svc.get_ar_aging(ctx.organization_id)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Customer", "Current", "1-30", "31-60", "61-90", "90+",
            "Total Owed", "Invoices", "Oldest (days)",
        ])
        for r in data["rows"]:
            writer.writerow([
                r["customer_name"],
                f"{r['current']:.2f}",
                f"{r['days_30']:.2f}",
                f"{r['days_60']:.2f}",
                f"{r['days_90']:.2f}",
                f"{r['over_90']:.2f}",
                f"{r['total_owed']:.2f}",
                r["invoice_count"],
                r["oldest_invoice_age_days"],
            ])
        t = data["totals"]
        writer.writerow([
            "TOTAL",
            f"{t['current']:.2f}",
            f"{t['days_30']:.2f}",
            f"{t['days_60']:.2f}",
            f"{t['days_90']:.2f}",
            f"{t['over_90']:.2f}",
            f"{t['total_owed']:.2f}",
            t["invoice_count"],
            "",
        ])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.read()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=ar-aging-{data['as_of']}.csv"
                ),
            },
        )

    return data
