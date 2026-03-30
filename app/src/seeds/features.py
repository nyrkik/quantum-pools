"""Seed feature catalog and EMD tiers."""

import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_context
from src.models.feature import Feature, FeatureTier
from src.models.org_subscription import OrgSubscription
from src.models.organization import Organization

FEATURES = [
    {
        "slug": "core_operations",
        "name": "Core Operations",
        "description": "Customers, properties, bodies of water, technicians, visits, chemical readings, dashboard.",
        "category": "operations",
        "is_base": True,
        "price_cents": 0,
        "billing_type": "included",
        "sort_order": 0,
    },
    {
        "slug": "route_optimization",
        "name": "Route Optimization",
        "description": "OR-Tools VRP route optimization, Leaflet maps, drag-drop route management.",
        "category": "operations",
        "is_base": False,
        "price_cents": 1999,
        "billing_type": "recurring",
        "sort_order": 10,
    },
    {
        "slug": "invoicing",
        "name": "Invoicing & Billing",
        "description": "Invoice generation, payments, billing schedules, AutoPay.",
        "category": "operations",
        "is_base": False,
        "price_cents": 2999,
        "billing_type": "recurring",
        "sort_order": 20,
    },
    {
        "slug": "profitability",
        "name": "Profitability Analysis",
        "description": "Difficulty scoring, cost breakdown, margin analysis, whale curve, pricing suggestions.",
        "category": "analytics",
        "is_base": False,
        "price_cents": 1499,
        "billing_type": "recurring",
        "sort_order": 30,
    },
    {
        "slug": "satellite_analysis",
        "name": "Satellite Analysis",
        "description": "Google Maps satellite imagery, Claude Vision pool detection, vegetation analysis.",
        "category": "intelligence",
        "is_base": False,
        "price_cents": 999,
        "billing_type": "recurring",
        "sort_order": 40,
    },
    {
        "slug": "pool_measurement",
        "name": "Pool Measurement",
        "description": "Tech photo upload, Claude Vision dimension extraction, volume calculation.",
        "category": "intelligence",
        "is_base": False,
        "price_cents": 999,
        "billing_type": "recurring",
        "sort_order": 50,
    },
    {
        "slug": "inspection_intelligence",
        "name": "Inspection Intelligence",
        "description": "Sacramento County health department inspection data, violation tracking, PDF extraction.",
        "category": "intelligence",
        "is_base": False,
        "price_cents": 0,
        "billing_type": "recurring",
        "sort_order": 60,
    },
    {
        "slug": "chemical_costs",
        "name": "Chemical Cost Engine",
        "description": "Chemical pricing, dosing calculations, cost profiles per body of water.",
        "category": "analytics",
        "is_base": False,
        "price_cents": 999,
        "billing_type": "recurring",
        "sort_order": 70,
    },
    {
        "slug": "customer_portal",
        "name": "Customer Portal",
        "description": "Customer-facing login, service history, invoice payments, service requests.",
        "category": "operations",
        "is_base": False,
        "price_cents": 1999,
        "billing_type": "recurring",
        "sort_order": 80,
    },
]

INSPECTION_TIERS = [
    {
        "slug": "my_inspections",
        "name": "My Inspections",
        "price_cents": 999,
        "billing_type": "recurring",
        "sort_order": 0,
    },
    {
        "slug": "full_research",
        "name": "Full Research",
        "price_cents": 2499,
        "billing_type": "recurring",
        "sort_order": 10,
    },
    {
        "slug": "single_lookup",
        "name": "Single Lookup",
        "price_cents": 99,
        "billing_type": "metered",
        "sort_order": 20,
    },
]


async def seed_features():
    """Insert feature catalog if not already seeded."""
    async with get_db_context() as db:
        result = await db.execute(select(Feature).limit(1))
        if result.scalar_one_or_none():
            print("Features already seeded.")
            return

        feature_map = {}
        for f in FEATURES:
            feature = Feature(id=str(uuid.uuid4()), **f)
            db.add(feature)
            feature_map[f["slug"]] = feature

        await db.flush()

        # EMD tiers
        inspection_feature = feature_map["inspection_intelligence"]
        for t in INSPECTION_TIERS:
            tier = FeatureTier(id=str(uuid.uuid4()), feature_id=inspection_feature.id, **t)
            db.add(tier)

        await db.flush()
        print(f"Seeded {len(FEATURES)} features + {len(INSPECTION_TIERS)} EMD tiers.")


async def grandfather_existing_orgs():
    """Give all existing orgs subscriptions to ALL features (grandfathered)."""
    async with get_db_context() as db:
        # Check if any subscriptions exist
        result = await db.execute(select(OrgSubscription).limit(1))
        if result.scalar_one_or_none():
            print("Org subscriptions already exist — skipping grandfather.")
            return

        # Get all orgs
        result = await db.execute(select(Organization))
        orgs = result.scalars().all()
        if not orgs:
            print("No organizations found.")
            return

        # Get all features
        result = await db.execute(select(Feature))
        features = result.scalars().all()

        # Get EMD tiers (grandfather full_research)
        result = await db.execute(
            select(FeatureTier).where(FeatureTier.slug == "full_research")
        )
        full_research_tier = result.scalar_one_or_none()

        count = 0
        for org in orgs:
            for feature in features:
                if feature.slug == "inspection_intelligence":
                    # Grandfather EMD at full_research tier
                    if full_research_tier:
                        db.add(OrgSubscription(
                            id=str(uuid.uuid4()),
                            organization_id=org.id,
                            feature_id=feature.id,
                            feature_tier_id=full_research_tier.id,
                            stripe_status="active",
                        ))
                        count += 1
                else:
                    db.add(OrgSubscription(
                        id=str(uuid.uuid4()),
                        organization_id=org.id,
                        feature_id=feature.id,
                        stripe_status="active",
                    ))
                    count += 1

        await db.flush()
        print(f"Grandfathered {count} subscriptions across {len(orgs)} org(s).")


async def seed_all():
    """Seed features then grandfather existing orgs."""
    await seed_features()
    await grandfather_existing_orgs()


if __name__ == "__main__":
    asyncio.run(seed_all())
