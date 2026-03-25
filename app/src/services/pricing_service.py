"""Pricing service — whale curve analysis, pricing suggestions, rate recommendations."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.org_cost_settings import OrgCostSettings
from src.models.customer import Customer
from src.schemas.profitability import (
    WhaleCurvePoint,
    PricingSuggestion,
)


class PricingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_whale_curve(self, org_id: str) -> list[WhaleCurvePoint]:
        from src.services.profitability_service import ProfitabilityService
        prof_svc = ProfitabilityService(self.db)
        overview = await prof_svc.get_overview(org_id)
        # Sort by profit descending
        sorted_accounts = sorted(overview.accounts, key=lambda a: a.cost_breakdown.profit, reverse=True)

        total_profit = sum(a.cost_breakdown.profit for a in sorted_accounts)
        if total_profit == 0:
            return []

        cumulative = 0.0
        points = []
        for i, account in enumerate(sorted_accounts):
            cumulative += account.cost_breakdown.profit
            points.append(WhaleCurvePoint(
                rank=i + 1,
                customer_name=account.customer_name,
                customer_id=account.customer_id,
                cumulative_profit_pct=round(cumulative / abs(total_profit) * 100, 1),
                individual_profit=account.cost_breakdown.profit,
            ))
        return points

    async def get_suggestions(self, org_id: str) -> list[PricingSuggestion]:
        from src.services.profitability_service import ProfitabilityService
        prof_svc = ProfitabilityService(self.db)
        overview = await prof_svc.get_overview(org_id)
        suggestions = []
        for account in overview.accounts:
            if account.cost_breakdown.rate_gap > 0:
                suggestions.append(PricingSuggestion(
                    customer_id=account.customer_id,
                    customer_name=account.customer_name,
                    property_address=account.property_address,
                    current_rate=account.monthly_rate,
                    suggested_rate=account.cost_breakdown.suggested_rate,
                    rate_gap=account.cost_breakdown.rate_gap,
                    current_margin_pct=account.margin_pct,
                    target_margin_pct=overview.target_margin_pct,
                    difficulty_score=account.difficulty_score,
                ))
        # Sort by rate gap descending
        suggestions.sort(key=lambda s: s.rate_gap, reverse=True)
        return suggestions

    @staticmethod
    def _billing_options(monthly_rate: float, settings: OrgCostSettings) -> dict:
        """Calculate semi-annual and annual pricing with discounts."""
        def apply_discount(monthly: float, months: int, dtype: str, dval: float) -> dict:
            total_no_discount = monthly * months
            if dtype == "percent":
                discount = total_no_discount * (dval / 100.0)
            else:
                discount = dval * months
            total = total_no_discount - discount
            effective_monthly = total / months
            return {
                "total": round(total, 2),
                "discount": round(discount, 2),
                "effective_monthly": round(effective_monthly, 2),
                "savings_pct": round((discount / total_no_discount * 100) if total_no_discount > 0 else 0, 1),
            }

        return {
            "monthly": round(monthly_rate, 2),
            "semi_annual": apply_discount(monthly_rate, 6, settings.semi_annual_discount_type, settings.semi_annual_discount_value),
            "annual": apply_discount(monthly_rate, 12, settings.annual_discount_type, settings.annual_discount_value),
        }

    async def suggest_rate(
        self, org_id: str, gallons: int, water_type: str = "pool",
        service_minutes: int = 30, difficulty_score: float = 2.5,
        customer_type: str = "residential", tier_id: str | None = None,
    ) -> dict:
        """Suggest a rate for a WF.

        Residential: tier base_rate × difficulty_multiplier × volume_factor
        Commercial: cost-based calculation with target margin
        """
        from src.services.profitability_service import ProfitabilityService
        prof_svc = ProfitabilityService(self.db)
        settings = await prof_svc.get_or_create_settings(org_id)

        from src.services.difficulty_service import DifficultyService
        diff_svc = DifficultyService(self.db)
        multiplier = diff_svc.difficulty_to_multiplier(difficulty_score)

        # Residential: tier-based pricing
        if customer_type == "residential":
            from src.models.service_tier import ServiceTier

            tier = None
            if tier_id:
                result = await self.db.execute(
                    select(ServiceTier).where(ServiceTier.id == tier_id, ServiceTier.organization_id == org_id)
                )
                tier = result.scalar_one_or_none()

            # Fall back to default tier
            if not tier:
                result = await self.db.execute(
                    select(ServiceTier).where(
                        ServiceTier.organization_id == org_id,
                        ServiceTier.is_default == True,
                        ServiceTier.is_active == True,
                    )
                )
                tier = result.scalar_one_or_none()

            if tier:
                # Volume factor: ratio vs typical 15k gallon pool
                typical_gallons = 15000
                volume_factor = max(0.7, min(1.5, (gallons / typical_gallons) ** 0.5)) if gallons > 0 else 1.0

                # Residential: no multiplier, use dollar adjustments
                # difficulty_score is not used for residential pricing — adjustments come from
                # the res_* fields on PropertyDifficulty, applied after rate is set
                suggested_rate = tier.base_rate * volume_factor

                # Load all tiers for comparison
                result = await self.db.execute(
                    select(ServiceTier)
                    .where(ServiceTier.organization_id == org_id, ServiceTier.is_active == True)
                    .order_by(ServiceTier.sort_order)
                )
                all_tiers = result.scalars().all()
                tier_options = []
                for t in all_tiers:
                    tier_rate = t.base_rate * volume_factor
                    tier_options.append({
                        "tier_id": t.id,
                        "tier_name": t.name,
                        "tier_slug": t.slug,
                        "base_rate": t.base_rate,
                        "suggested_rate": round(tier_rate, 2),
                        "is_selected": t.id == tier.id,
                    })

                return {
                    "suggested_rate": round(suggested_rate, 2),
                    "method": "tier",
                    "tier_id": tier.id,
                    "tier_name": tier.name,
                    "base_rate": tier.base_rate,
                    "volume_factor": round(volume_factor, 2),
                    "gallons": gallons,
                    "water_type": water_type,
                    "note": "Difficulty adjustments (tree debris, dog, etc.) are added per-visit after rate is set",
                    "tier_options": tier_options,
                    "billing_options": self._billing_options(suggested_rate, settings),
                }

        # Commercial: cost-based
        from sqlalchemy import func
        count_result = await self.db.execute(
            select(func.count(Customer.id)).where(Customer.organization_id == org_id, Customer.is_active == True)
        )
        total_accounts = count_result.scalar() or 1
        visits = settings.visits_per_month

        chemical_cost = (gallons / 10000.0) * settings.chemical_cost_per_gallon * multiplier * visits
        labor_cost = (service_minutes / 60.0) * settings.burdened_labor_rate * visits * multiplier
        travel_cost = ((settings.avg_drive_minutes / 60.0) * settings.burdened_labor_rate + settings.avg_drive_miles * settings.vehicle_cost_per_mile) * visits
        overhead_cost = settings.commercial_overhead_per_account if customer_type == "commercial" else settings.residential_overhead_per_account

        total_cost = chemical_cost + labor_cost + travel_cost + overhead_cost
        target_margin = settings.target_margin_pct / 100.0
        suggested_rate = total_cost / (1 - target_margin) if target_margin < 1 else total_cost * 2

        return {
            "suggested_rate": round(suggested_rate, 2),
            "method": "cost",
            "total_cost": round(total_cost, 2),
            "chemical_cost": round(chemical_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "travel_cost": round(travel_cost, 2),
            "overhead_cost": round(overhead_cost, 2),
            "target_margin_pct": settings.target_margin_pct,
            "gallons": gallons,
            "water_type": water_type,
            "service_minutes": service_minutes,
            "difficulty_score": round(difficulty_score, 2),
            "billing_options": self._billing_options(suggested_rate, settings),
        }
