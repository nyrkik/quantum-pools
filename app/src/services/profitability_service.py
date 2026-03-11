"""Profitability analysis service — cost breakdown, margins, difficulty scoring."""

import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.models.org_cost_settings import OrgCostSettings
from src.models.property_difficulty import PropertyDifficulty
from src.models.property import Property
from src.models.customer import Customer
from src.schemas.profitability import (
    CostBreakdown,
    ProfitabilityAccount,
    ProfitabilityOverview,
    WhaleCurvePoint,
    PricingSuggestion,
    PropertyDifficultyResponse,
)
from src.core.exceptions import NotFoundError


# Difficulty score weights
WEIGHTS = {
    "pool_gallons": 0.10,
    "pool_sqft": 0.05,
    "water_features": 0.08,
    "equipment_age": 0.07,
    "shade_debris": 0.05,
    "enclosure": 0.05,
    "chemical_demand": 0.12,
    "service_time": 0.18,
    "distance": 0.10,
    "access": 0.08,
    "customer_demands": 0.07,
    "callback": 0.05,
}

# Gallon ranges → score 1-5
GALLON_RANGES = [(10000, 1), (20000, 2), (30000, 3), (40000, 4)]
SQFT_RANGES = [(400, 1), (700, 2), (1000, 3), (1500, 4)]
SERVICE_TIME_RANGES = [(20, 1), (30, 2), (45, 3), (60, 4)]
EQUIPMENT_AGE_RANGES = [(3, 1), (6, 2), (10, 3), (15, 4)]


def _range_score(value: Optional[float], ranges: list[tuple]) -> float:
    if value is None:
        return 1.0
    for threshold, score in ranges:
        if value <= threshold:
            return float(score)
    return 5.0


def _shade_score(shade: Optional[str]) -> float:
    return {"full_sun": 1.0, "partial_shade": 3.0, "full_shade": 5.0}.get(shade or "", 1.0)


def _debris_score(debris: Optional[str]) -> float:
    return {"none": 1.0, "low": 2.0, "moderate": 3.5, "heavy": 5.0}.get(debris or "", 1.0)


def _enclosure_score(enclosure: Optional[str]) -> float:
    return {"indoor": 1.0, "screened": 2.0, "open": 3.5}.get(enclosure or "", 3.5)


class ProfitabilityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_settings(self, org_id: str) -> OrgCostSettings:
        result = await self.db.execute(
            select(OrgCostSettings).where(OrgCostSettings.organization_id == org_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            settings = OrgCostSettings(id=str(uuid.uuid4()), organization_id=org_id)
            self.db.add(settings)
            await self.db.flush()
            await self.db.refresh(settings)
        return settings

    async def update_settings(self, org_id: str, **kwargs) -> OrgCostSettings:
        settings = await self.get_or_create_settings(org_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(settings, key, value)
        await self.db.flush()
        await self.db.refresh(settings)
        return settings

    async def get_or_create_difficulty(self, org_id: str, property_id: str) -> PropertyDifficulty:
        result = await self.db.execute(
            select(PropertyDifficulty).where(
                PropertyDifficulty.property_id == property_id,
                PropertyDifficulty.organization_id == org_id,
            )
        )
        diff = result.scalar_one_or_none()
        if not diff:
            diff = PropertyDifficulty(
                id=str(uuid.uuid4()),
                property_id=property_id,
                organization_id=org_id,
            )
            self.db.add(diff)
            await self.db.flush()
            await self.db.refresh(diff)
        return diff

    async def update_difficulty(self, org_id: str, property_id: str, **kwargs) -> PropertyDifficulty:
        diff = await self.get_or_create_difficulty(org_id, property_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(diff, key, value)
        await self.db.flush()
        await self.db.refresh(diff)
        return diff

    def compute_composite_score(
        self, prop: Property, diff: Optional[PropertyDifficulty]
    ) -> float:
        if diff and diff.override_composite is not None:
            return diff.override_composite

        scores = {}

        # Measured factors
        scores["pool_gallons"] = _range_score(prop.pool_gallons, GALLON_RANGES)
        scores["pool_sqft"] = _range_score(prop.pool_sqft, SQFT_RANGES)
        scores["service_time"] = _range_score(prop.estimated_service_minutes, SERVICE_TIME_RANGES)

        water_feature_score = 1.0
        if prop.has_spa:
            water_feature_score += 1.5
        if prop.has_water_feature:
            water_feature_score += 1.0
        scores["water_features"] = min(water_feature_score, 5.0)

        if diff:
            scores["equipment_age"] = _range_score(diff.equipment_age_years, EQUIPMENT_AGE_RANGES)
            scores["shade_debris"] = (
                _shade_score(diff.shade_exposure.value if diff.shade_exposure else None)
                + _debris_score(diff.tree_debris_level.value if diff.tree_debris_level else None)
            ) / 2.0
            scores["enclosure"] = _enclosure_score(
                diff.enclosure_type.value if diff.enclosure_type else None
            )
            scores["chemical_demand"] = diff.chemical_demand_score
            scores["access"] = diff.access_difficulty_score
            scores["customer_demands"] = diff.customer_demands_score
            scores["callback"] = diff.callback_frequency_score
        else:
            scores["equipment_age"] = 1.0
            scores["shade_debris"] = 1.0
            scores["enclosure"] = 3.5
            scores["chemical_demand"] = 1.0
            scores["access"] = 1.0
            scores["customer_demands"] = 1.0
            scores["callback"] = 1.0

        # Distance — would need route data, default to 1.0
        scores["distance"] = 1.0

        composite = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
        return round(min(max(composite, 1.0), 5.0), 2)

    def difficulty_to_multiplier(self, score: float) -> float:
        return round(0.8 + (score - 1.0) * 0.2, 3)

    def compute_cost_breakdown(
        self,
        settings: OrgCostSettings,
        prop: Property,
        customer: Customer,
        difficulty_score: float,
        total_accounts: int,
    ) -> CostBreakdown:
        multiplier = self.difficulty_to_multiplier(difficulty_score)
        visits_per_month = 4.0  # Standard weekly service

        # Chemical cost
        gallons = prop.pool_gallons or 15000
        chemical_cost = (gallons / 10000.0) * settings.chemical_cost_per_gallon * multiplier * visits_per_month

        # Labor cost
        service_minutes = prop.estimated_service_minutes or 30
        labor_cost = (service_minutes / 60.0) * settings.burdened_labor_rate * visits_per_month * multiplier

        # Travel cost (estimate 15 min drive, 8 miles per stop)
        drive_minutes = 15
        miles = 8.0
        travel_cost = (
            (drive_minutes / 60.0) * settings.burdened_labor_rate
            + miles * settings.vehicle_cost_per_mile
        ) * visits_per_month

        # Overhead
        overhead_cost = settings.monthly_overhead / max(total_accounts, 1)

        total_cost = chemical_cost + labor_cost + travel_cost + overhead_cost
        revenue = customer.monthly_rate or 0.0
        profit = revenue - total_cost
        margin_pct = (profit / revenue * 100) if revenue > 0 else 0.0
        target_margin = settings.target_margin_pct / 100.0
        suggested_rate = total_cost / (1 - target_margin) if target_margin < 1 else total_cost * 2
        rate_gap = suggested_rate - revenue

        return CostBreakdown(
            chemical_cost=round(chemical_cost, 2),
            labor_cost=round(labor_cost, 2),
            travel_cost=round(travel_cost, 2),
            overhead_cost=round(overhead_cost, 2),
            total_cost=round(total_cost, 2),
            revenue=round(revenue, 2),
            profit=round(profit, 2),
            margin_pct=round(margin_pct, 1),
            suggested_rate=round(suggested_rate, 2),
            rate_gap=round(rate_gap, 2),
        )

    async def get_overview(
        self,
        org_id: str,
        tech_id: Optional[str] = None,
        min_margin: Optional[float] = None,
        max_margin: Optional[float] = None,
        min_difficulty: Optional[float] = None,
        max_difficulty: Optional[float] = None,
    ) -> ProfitabilityOverview:
        settings = await self.get_or_create_settings(org_id)

        # Get all active customers with properties
        query = (
            select(Customer)
            .where(Customer.organization_id == org_id, Customer.is_active == True)
            .options(joinedload(Customer.properties))
        )
        result = await self.db.execute(query)
        customers = list(result.unique().scalars().all())

        # Count total for overhead calc
        total_accounts = sum(
            1 for c in customers for p in (c.properties or []) if p.is_active
        )

        # Load all difficulties
        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.organization_id == org_id)
        )
        difficulties = {d.property_id: d for d in diff_result.scalars().all()}

        accounts: list[ProfitabilityAccount] = []
        for customer in customers:
            for prop in (customer.properties or []):
                if not prop.is_active:
                    continue

                diff = difficulties.get(prop.id)
                score = self.compute_composite_score(prop, diff)
                multiplier = self.difficulty_to_multiplier(score)
                cost = self.compute_cost_breakdown(settings, prop, customer, score, total_accounts)

                # Apply filters
                if min_margin is not None and cost.margin_pct < min_margin:
                    continue
                if max_margin is not None and cost.margin_pct > max_margin:
                    continue
                if min_difficulty is not None and score < min_difficulty:
                    continue
                if max_difficulty is not None and score > max_difficulty:
                    continue

                rate_per_gallon = None
                if prop.pool_gallons and customer.monthly_rate:
                    rate_per_gallon = round(customer.monthly_rate / prop.pool_gallons, 4)

                accounts.append(ProfitabilityAccount(
                    customer_id=customer.id,
                    customer_name=f"{customer.first_name} {customer.last_name}".strip(),
                    property_id=prop.id,
                    property_address=prop.address,
                    monthly_rate=customer.monthly_rate or 0.0,
                    pool_gallons=prop.pool_gallons,
                    pool_sqft=prop.pool_sqft,
                    estimated_service_minutes=prop.estimated_service_minutes or 30,
                    difficulty_score=score,
                    difficulty_multiplier=multiplier,
                    cost_breakdown=cost,
                    margin_pct=cost.margin_pct,
                    rate_per_gallon=rate_per_gallon,
                ))

        # Sort by margin ascending (worst first)
        accounts.sort(key=lambda a: a.margin_pct)

        total_revenue = sum(a.cost_breakdown.revenue for a in accounts)
        total_cost = sum(a.cost_breakdown.total_cost for a in accounts)
        total_profit = total_revenue - total_cost
        avg_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0.0
        below_target = sum(1 for a in accounts if a.margin_pct < settings.target_margin_pct)

        return ProfitabilityOverview(
            total_accounts=len(accounts),
            total_revenue=round(total_revenue, 2),
            total_cost=round(total_cost, 2),
            total_profit=round(total_profit, 2),
            avg_margin_pct=round(avg_margin, 1),
            below_target_count=below_target,
            target_margin_pct=settings.target_margin_pct,
            accounts=accounts,
        )

    async def get_account_detail(
        self, org_id: str, customer_id: str
    ) -> list[ProfitabilityAccount]:
        settings = await self.get_or_create_settings(org_id)

        result = await self.db.execute(
            select(Customer)
            .where(Customer.id == customer_id, Customer.organization_id == org_id)
            .options(joinedload(Customer.properties))
        )
        customer = result.unique().scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")

        # Total accounts for overhead
        count_result = await self.db.execute(
            select(Property)
            .where(Property.organization_id == org_id, Property.is_active == True)
        )
        total_accounts = len(list(count_result.scalars().all()))

        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.organization_id == org_id)
        )
        difficulties = {d.property_id: d for d in diff_result.scalars().all()}

        accounts = []
        for prop in (customer.properties or []):
            if not prop.is_active:
                continue
            diff = difficulties.get(prop.id)
            score = self.compute_composite_score(prop, diff)
            multiplier = self.difficulty_to_multiplier(score)
            cost = self.compute_cost_breakdown(settings, prop, customer, score, total_accounts)

            rate_per_gallon = None
            if prop.pool_gallons and customer.monthly_rate:
                rate_per_gallon = round(customer.monthly_rate / prop.pool_gallons, 4)

            accounts.append(ProfitabilityAccount(
                customer_id=customer.id,
                customer_name=f"{customer.first_name} {customer.last_name}".strip(),
                property_id=prop.id,
                property_address=prop.address,
                monthly_rate=customer.monthly_rate or 0.0,
                pool_gallons=prop.pool_gallons,
                pool_sqft=prop.pool_sqft,
                estimated_service_minutes=prop.estimated_service_minutes or 30,
                difficulty_score=score,
                difficulty_multiplier=multiplier,
                cost_breakdown=cost,
                margin_pct=cost.margin_pct,
                rate_per_gallon=rate_per_gallon,
            ))
        return accounts

    async def get_whale_curve(self, org_id: str) -> list[WhaleCurvePoint]:
        overview = await self.get_overview(org_id)
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
        overview = await self.get_overview(org_id)
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

    def get_difficulty_response(
        self, prop: Property, diff: PropertyDifficulty
    ) -> PropertyDifficultyResponse:
        score = self.compute_composite_score(prop, diff)
        multiplier = self.difficulty_to_multiplier(score)
        resp = PropertyDifficultyResponse.model_validate(diff)
        resp.composite_score = score
        resp.difficulty_multiplier = multiplier
        return resp
