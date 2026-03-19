"""Feature access service — checks org subscriptions and provides feature lists."""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.feature import Feature, FeatureTier
from src.models.org_subscription import OrgSubscription
from src.models.organization import Organization

# Statuses that grant access
ACTIVE_STATUSES = {"active", "trialing", "past_due"}


class FeatureService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_feature_catalog(self) -> list[Feature]:
        """Get all active features with their tiers."""
        result = await self.db.execute(
            select(Feature)
            .options(selectinload(Feature.tiers))
            .where(Feature.is_active == True)
            .order_by(Feature.sort_order)
        )
        return list(result.scalars().unique().all())

    async def get_org_active_feature_slugs(self, organization_id: str) -> list[str]:
        """Get list of active feature slugs for an org. Includes base features."""
        now = datetime.now(timezone.utc)

        # Check if org is in trial
        result = await self.db.execute(
            select(Organization.trial_ends_at).where(Organization.id == organization_id)
        )
        trial_ends_at = result.scalar_one_or_none()
        if trial_ends_at and trial_ends_at > now:
            # During trial, all active features are available
            result = await self.db.execute(
                select(Feature.slug).where(Feature.is_active == True)
            )
            return list(result.scalars().all())

        # Base features always included
        result = await self.db.execute(
            select(Feature.slug).where(Feature.is_base == True, Feature.is_active == True)
        )
        slugs = list(result.scalars().all())

        # Add subscribed features
        result = await self.db.execute(
            select(Feature.slug)
            .join(OrgSubscription, OrgSubscription.feature_id == Feature.id)
            .where(
                OrgSubscription.organization_id == organization_id,
                OrgSubscription.stripe_status.in_(ACTIVE_STATUSES),
                Feature.is_active == True,
            )
        )
        slugs.extend(result.scalars().all())
        return list(set(slugs))

    async def org_has_feature(
        self, organization_id: str, feature_slug: str, tier_slug: str | None = None
    ) -> bool:
        """Check if an org has access to a specific feature (and optionally tier)."""
        now = datetime.now(timezone.utc)

        # Base features always pass
        result = await self.db.execute(
            select(Feature).where(Feature.slug == feature_slug, Feature.is_active == True)
        )
        feature = result.scalar_one_or_none()
        if not feature:
            return False
        if feature.is_base:
            return True

        # Trial check
        result = await self.db.execute(
            select(Organization.trial_ends_at).where(Organization.id == organization_id)
        )
        trial_ends_at = result.scalar_one_or_none()
        if trial_ends_at and trial_ends_at > now:
            return True

        # Subscription check
        query = (
            select(OrgSubscription)
            .where(
                OrgSubscription.organization_id == organization_id,
                OrgSubscription.feature_id == feature.id,
                OrgSubscription.stripe_status.in_(ACTIVE_STATUSES),
            )
        )

        if tier_slug:
            # Must have specific tier or higher
            result = await self.db.execute(
                select(FeatureTier).where(
                    FeatureTier.feature_id == feature.id,
                    FeatureTier.slug == tier_slug,
                )
            )
            tier = result.scalar_one_or_none()
            if not tier:
                return False

            # Check for this tier or a higher tier (lower sort_order = higher tier for EMD)
            result = await self.db.execute(
                select(FeatureTier.id).where(
                    FeatureTier.feature_id == feature.id,
                    FeatureTier.sort_order <= tier.sort_order,
                    FeatureTier.billing_type == "recurring",
                )
            )
            valid_tier_ids = list(result.scalars().all())
            # Also include the exact tier requested
            valid_tier_ids.append(tier.id)

            query = query.where(OrgSubscription.feature_tier_id.in_(valid_tier_ids))

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_org_emd_tier(self, organization_id: str) -> str | None:
        """Get the org's active EMD tier slug. Returns 'full_research', 'my_inspections', or None."""
        now = datetime.now(timezone.utc)

        # Trial → full access
        result = await self.db.execute(
            select(Organization.trial_ends_at).where(Organization.id == organization_id)
        )
        trial_ends_at = result.scalar_one_or_none()
        if trial_ends_at and trial_ends_at > now:
            return "full_research"

        # Find emd_intelligence feature
        result = await self.db.execute(
            select(Feature).where(Feature.slug == "emd_intelligence", Feature.is_active == True)
        )
        feature = result.scalar_one_or_none()
        if not feature:
            return None

        # Get active subscription with tier info
        result = await self.db.execute(
            select(OrgSubscription, FeatureTier)
            .outerjoin(FeatureTier, OrgSubscription.feature_tier_id == FeatureTier.id)
            .where(
                OrgSubscription.organization_id == organization_id,
                OrgSubscription.feature_id == feature.id,
                OrgSubscription.stripe_status.in_(ACTIVE_STATUSES),
                FeatureTier.billing_type == "recurring",
            )
            .order_by(FeatureTier.sort_order)
            .limit(1)
        )
        row = result.first()
        if row and row[1]:
            return row[1].slug
        return None

    async def get_org_subscriptions(self, organization_id: str) -> list[OrgSubscription]:
        """Get all subscriptions for an org with feature details."""
        result = await self.db.execute(
            select(OrgSubscription)
            .options(
                selectinload(OrgSubscription.feature),
                selectinload(OrgSubscription.feature_tier),
            )
            .where(OrgSubscription.organization_id == organization_id)
        )
        return list(result.scalars().unique().all())
