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
from src.models.body_of_water import BodyOfWater
from src.schemas.profitability import (
    CostBreakdown,
    ProfitabilityAccount,
    ProfitabilityOverview,
    WhaleCurvePoint,
    PricingSuggestion,
    PropertyDifficultyResponse,
)
from src.core.exceptions import NotFoundError
from src.models.chemical_cost_profile import ChemicalCostProfile


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
        self, prop: Property, diff: Optional[PropertyDifficulty],
        bows: Optional[list[BodyOfWater]] = None,
    ) -> float:
        if diff and diff.override_composite is not None:
            return diff.override_composite

        scores = {}

        # Aggregate from BOWs if available, else fall back to property fields
        if bows:
            total_gallons = sum(b.pool_gallons or 0 for b in bows) or None
            total_sqft = sum(b.pool_sqft or 0 for b in bows) or None
            total_service_minutes = sum(b.estimated_service_minutes or 0 for b in bows) or None
            has_spa = any(b.water_type == "spa" for b in bows)
            has_water_feature = any(b.water_type in ("water_feature", "fountain") for b in bows)
        else:
            total_gallons = prop.pool_gallons
            total_sqft = prop.pool_sqft
            total_service_minutes = prop.estimated_service_minutes
            has_spa = prop.has_spa
            has_water_feature = prop.has_water_feature

        # Measured factors
        scores["pool_gallons"] = _range_score(total_gallons, GALLON_RANGES)
        scores["pool_sqft"] = _range_score(total_sqft, SQFT_RANGES)
        scores["service_time"] = _range_score(total_service_minutes, SERVICE_TIME_RANGES)

        water_feature_score = 1.0
        if has_spa:
            water_feature_score += 1.5
        if has_water_feature:
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
        bows: Optional[list[BodyOfWater]] = None,
        chemical_profiles: Optional[dict[str, ChemicalCostProfile]] = None,
    ) -> CostBreakdown:
        multiplier = self.difficulty_to_multiplier(difficulty_score)
        visits = settings.visits_per_month

        # Chemical cost — use chemical cost profiles if available
        if bows:
            gallons = sum(b.pool_gallons or 0 for b in bows) or 15000
            service_minutes = sum(b.estimated_service_minutes or 0 for b in bows) or 30
        else:
            gallons = prop.pool_gallons or 15000
            service_minutes = prop.estimated_service_minutes or 30

        # Try to use per-BOW chemical cost profiles
        chemical_cost = None
        if chemical_profiles and bows:
            bow_costs = []
            for bow in bows:
                profile = chemical_profiles.get(bow.id)
                if profile and profile.total_monthly > 0:
                    bow_costs.append(profile.total_monthly)
            if bow_costs:
                chemical_cost = sum(bow_costs)

        # Fallback to flat calculation if no profiles
        if chemical_cost is None:
            chemical_cost = (gallons / 10000.0) * settings.chemical_cost_per_gallon * multiplier * visits

        # Labor cost
        labor_cost = (service_minutes / 60.0) * settings.burdened_labor_rate * visits * multiplier

        # Travel cost
        travel_cost = (
            (settings.avg_drive_minutes / 60.0) * settings.burdened_labor_rate
            + settings.avg_drive_miles * settings.vehicle_cost_per_mile
        ) * visits

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

        # Load all BOWs for org, indexed by property_id
        bow_result = await self.db.execute(
            select(BodyOfWater).where(
                BodyOfWater.organization_id == org_id,
                BodyOfWater.is_active == True,
            )
        )
        bows_by_property: dict[str, list[BodyOfWater]] = {}
        for bow in bow_result.scalars().all():
            bows_by_property.setdefault(bow.property_id, []).append(bow)

        # Count total for overhead calc
        total_accounts = sum(
            1 for c in customers for p in (c.properties or []) if p.is_active
        )

        # Load all difficulties
        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.organization_id == org_id)
        )
        difficulties = {d.property_id: d for d in diff_result.scalars().all()}

        # Load all chemical cost profiles indexed by bow_id
        chem_result = await self.db.execute(
            select(ChemicalCostProfile).where(ChemicalCostProfile.organization_id == org_id)
        )
        chem_profiles_by_bow = {p.body_of_water_id: p for p in chem_result.scalars().all()}

        accounts: list[ProfitabilityAccount] = []
        for customer in customers:
            for prop in (customer.properties or []):
                if not prop.is_active:
                    continue

                prop_bows = bows_by_property.get(prop.id, [])
                diff = difficulties.get(prop.id)
                score = self.compute_composite_score(prop, diff, bows=prop_bows)
                multiplier = self.difficulty_to_multiplier(score)
                cost = self.compute_cost_breakdown(
                    settings, prop, customer, score, total_accounts,
                    bows=prop_bows, chemical_profiles=chem_profiles_by_bow,
                )

                # Apply filters
                if min_margin is not None and cost.margin_pct < min_margin:
                    continue
                if max_margin is not None and cost.margin_pct > max_margin:
                    continue
                if min_difficulty is not None and score < min_difficulty:
                    continue
                if max_difficulty is not None and score > max_difficulty:
                    continue

                total_gallons = sum(b.pool_gallons or 0 for b in prop_bows) if prop_bows else prop.pool_gallons
                total_sqft = sum(b.pool_sqft or 0 for b in prop_bows) if prop_bows else prop.pool_sqft
                total_svc_min = sum(b.estimated_service_minutes or 0 for b in prop_bows) if prop_bows else (prop.estimated_service_minutes or 30)

                rate_per_gallon = None
                if total_gallons and customer.monthly_rate:
                    rate_per_gallon = round(customer.monthly_rate / total_gallons, 4)

                accounts.append(ProfitabilityAccount(
                    customer_id=customer.id,
                    customer_name=f"{customer.first_name} {customer.last_name}".strip(),
                    property_id=prop.id,
                    property_address=prop.address,
                    monthly_rate=customer.monthly_rate or 0.0,
                    pool_gallons=total_gallons,
                    pool_sqft=total_sqft,
                    estimated_service_minutes=total_svc_min,
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

        # Load BOWs for this customer's properties
        property_ids = [p.id for p in (customer.properties or []) if p.is_active]
        bow_result = await self.db.execute(
            select(BodyOfWater).where(
                BodyOfWater.organization_id == org_id,
                BodyOfWater.property_id.in_(property_ids),
                BodyOfWater.is_active == True,
            )
        ) if property_ids else None
        bows_by_property: dict[str, list[BodyOfWater]] = {}
        if bow_result:
            for bow in bow_result.scalars().all():
                bows_by_property.setdefault(bow.property_id, []).append(bow)

        # Load chemical cost profiles for this customer's BOWs
        all_bow_ids = [bow.id for bows in bows_by_property.values() for bow in bows]
        chem_profiles_by_bow: dict[str, ChemicalCostProfile] = {}
        if all_bow_ids:
            chem_result = await self.db.execute(
                select(ChemicalCostProfile).where(
                    ChemicalCostProfile.body_of_water_id.in_(all_bow_ids)
                )
            )
            chem_profiles_by_bow = {p.body_of_water_id: p for p in chem_result.scalars().all()}

        accounts = []
        for prop in (customer.properties or []):
            if not prop.is_active:
                continue
            prop_bows = bows_by_property.get(prop.id, [])
            diff = difficulties.get(prop.id)
            score = self.compute_composite_score(prop, diff, bows=prop_bows)
            multiplier = self.difficulty_to_multiplier(score)
            cost = self.compute_cost_breakdown(
                settings, prop, customer, score, total_accounts,
                bows=prop_bows, chemical_profiles=chem_profiles_by_bow,
            )

            total_gallons = sum(b.pool_gallons or 0 for b in prop_bows) if prop_bows else prop.pool_gallons
            total_sqft = sum(b.pool_sqft or 0 for b in prop_bows) if prop_bows else prop.pool_sqft
            total_svc_min = sum(b.estimated_service_minutes or 0 for b in prop_bows) if prop_bows else (prop.estimated_service_minutes or 30)

            rate_per_gallon = None
            if total_gallons and customer.monthly_rate:
                rate_per_gallon = round(customer.monthly_rate / total_gallons, 4)

            accounts.append(ProfitabilityAccount(
                customer_id=customer.id,
                customer_name=f"{customer.first_name} {customer.last_name}".strip(),
                property_id=prop.id,
                property_address=prop.address,
                monthly_rate=customer.monthly_rate or 0.0,
                pool_gallons=total_gallons,
                pool_sqft=total_sqft,
                estimated_service_minutes=total_svc_min,
                difficulty_score=score,
                difficulty_multiplier=multiplier,
                cost_breakdown=cost,
                margin_pct=cost.margin_pct,
                rate_per_gallon=rate_per_gallon,
            ))
        return accounts

    @staticmethod
    def allocate_rate_to_bows(total_rate: float, bows: list[BodyOfWater]) -> dict[str, dict]:
        """Allocate a property's total rate across its BOWs.

        Returns dict of bow_id -> {allocated_rate, allocation_method, weight}

        Priority: gallons > sqft > service_time > type_weighting
        """
        if not bows or total_rate <= 0:
            return {}

        if len(bows) == 1:
            return {bows[0].id: {"allocated_rate": total_rate, "allocation_method": "sole", "weight": 1.0}}

        TYPE_WEIGHTS = {
            "pool": 1.0,
            "spa": 0.25,
            "hot_tub": 0.20,
            "wading_pool": 0.15,
            "fountain": 0.10,
            "water_feature": 0.10,
        }

        # Try gallons
        gallons = [(b, b.pool_gallons or 0) for b in bows]
        total_gal = sum(g for _, g in gallons)
        if total_gal > 0 and all(g > 0 for _, g in gallons):
            result = {}
            for b, g in gallons:
                w = g / total_gal
                result[b.id] = {"allocated_rate": round(total_rate * w, 2), "allocation_method": "gallons", "weight": round(w, 4)}
            return result

        # Try sqft
        sqfts = [(b, b.pool_sqft or 0) for b in bows]
        total_sqft = sum(s for _, s in sqfts)
        if total_sqft > 0 and all(s > 0 for _, s in sqfts):
            result = {}
            for b, s in sqfts:
                w = s / total_sqft
                result[b.id] = {"allocated_rate": round(total_rate * w, 2), "allocation_method": "sqft", "weight": round(w, 4)}
            return result

        # Try service time
        times = [(b, b.estimated_service_minutes or 0) for b in bows]
        total_time = sum(t for _, t in times)
        if total_time > 0 and all(t > 0 for _, t in times):
            result = {}
            for b, t in times:
                w = t / total_time
                result[b.id] = {"allocated_rate": round(total_rate * w, 2), "allocation_method": "service_time", "weight": round(w, 4)}
            return result

        # Type weighting (always available)
        weights = [(b, TYPE_WEIGHTS.get(b.water_type, 0.5)) for b in bows]
        total_w = sum(w for _, w in weights)
        result = {}
        for b, w in weights:
            ratio = w / total_w if total_w > 0 else 1.0 / len(bows)
            result[b.id] = {"allocated_rate": round(total_rate * ratio, 2), "allocation_method": "type_weight", "weight": round(ratio, 4)}
        return result

    async def get_portfolio_medians(self, org_id: str) -> dict:
        """Compute median rate/gal, cost, margin, difficulty across all active accounts."""
        import statistics
        overview = await self.get_overview(org_id)
        accounts = overview.accounts
        if not accounts:
            return {"rate_per_gallon": None, "cost": 0, "margin_pct": 0, "difficulty": 0}

        rpg = [a.rate_per_gallon for a in accounts if a.rate_per_gallon and a.rate_per_gallon > 0]
        costs = [a.cost_breakdown.total_cost for a in accounts if a.cost_breakdown.total_cost > 0]
        margins = [a.margin_pct for a in accounts]
        diffs = [a.difficulty_score for a in accounts]

        return {
            "rate_per_gallon": statistics.median(rpg) if rpg else None,
            "cost": statistics.median(costs) if costs else 0,
            "margin_pct": statistics.median(margins) if margins else 0,
            "difficulty": statistics.median(diffs) if diffs else 0,
        }

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

    def compute_bow_cost(
        self,
        settings: OrgCostSettings,
        bow: BodyOfWater,
        difficulty_score: float,
        total_accounts: int,
        num_bows_at_property: int,
        chemical_profile: Optional[ChemicalCostProfile] = None,
    ) -> dict:
        """Compute cost breakdown for a single BOW.

        Travel and overhead are split across BOWs at the same property
        (one trip services all BOWs).
        """
        multiplier = self.difficulty_to_multiplier(difficulty_score)
        visits = settings.visits_per_month

        gallons = bow.pool_gallons or 15000
        service_minutes = bow.estimated_service_minutes or 30

        # Chemical cost
        if chemical_profile and chemical_profile.total_monthly > 0:
            chemical_cost = chemical_profile.total_monthly
        else:
            chemical_cost = (gallons / 10000.0) * settings.chemical_cost_per_gallon * multiplier * visits

        # Labor cost (per BOW — each BOW has its own service time)
        labor_cost = (service_minutes / 60.0) * settings.burdened_labor_rate * visits * multiplier

        # Travel cost — split across BOWs at the property (one trip)
        full_travel = (
            (settings.avg_drive_minutes / 60.0) * settings.burdened_labor_rate
            + settings.avg_drive_miles * settings.vehicle_cost_per_mile
        ) * visits
        travel_cost = full_travel / max(num_bows_at_property, 1)

        # Overhead — split across all accounts, then across BOWs at property
        full_overhead = settings.monthly_overhead / max(total_accounts, 1)
        overhead_cost = full_overhead / max(num_bows_at_property, 1)

        total_cost = chemical_cost + labor_cost + travel_cost + overhead_cost
        revenue = bow.monthly_rate or 0.0
        profit = revenue - total_cost
        margin_pct = (profit / revenue * 100) if revenue > 0 else 0.0
        target_margin = settings.target_margin_pct / 100.0
        suggested_rate = total_cost / (1 - target_margin) if target_margin < 1 else total_cost * 2
        rate_gap = suggested_rate - revenue

        return {
            "bow_id": bow.id,
            "bow_name": bow.name,
            "water_type": bow.water_type,
            "gallons": gallons,
            "service_minutes": service_minutes,
            "monthly_rate": revenue,
            "chemical_cost": round(chemical_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "travel_cost": round(travel_cost, 2),
            "overhead_cost": round(overhead_cost, 2),
            "total_cost": round(total_cost, 2),
            "profit": round(profit, 2),
            "margin_pct": round(margin_pct, 1),
            "suggested_rate": round(suggested_rate, 2),
            "rate_gap": round(rate_gap, 2),
            "difficulty_score": round(difficulty_score, 2),
            "difficulty_multiplier": round(multiplier, 2),
        }

    async def get_rate_allocation_preview(self, customer_id: str, org_id: str) -> dict:
        """Preview rate allocation for a customer's BOWs without saving."""
        customer = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = customer.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")

        # Get all properties + BOWs
        props = await self.db.execute(
            select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
        )
        properties = props.scalars().all()
        prop_ids = [p.id for p in properties]

        bows_result = await self.db.execute(
            select(BodyOfWater).where(BodyOfWater.property_id.in_(prop_ids), BodyOfWater.is_active == True)
        )
        bows = bows_result.scalars().all()

        if not bows:
            return {"customer_id": customer_id, "total_rate": customer.monthly_rate, "allocations": [], "method": None}

        allocation = self.allocate_rate_to_bows(customer.monthly_rate, bows)

        allocations = []
        method = None
        for bow in bows:
            alloc = allocation.get(bow.id, {})
            method = alloc.get("allocation_method", method)
            allocations.append({
                "bow_id": bow.id,
                "bow_name": bow.name,
                "water_type": bow.water_type,
                "gallons": bow.pool_gallons,
                "service_minutes": bow.estimated_service_minutes,
                "current_rate": bow.monthly_rate,
                "proposed_rate": alloc.get("allocated_rate", 0),
                "weight": alloc.get("weight", 0),
                "allocation_method": alloc.get("allocation_method"),
            })

        return {
            "customer_id": customer_id,
            "customer_name": customer.display_name_col,
            "total_rate": customer.monthly_rate,
            "method": method,
            "allocations": allocations,
        }

    async def apply_rate_allocation(self, customer_id: str, org_id: str, rates: dict[str, float]) -> dict:
        """Apply per-BOW rates. rates = {bow_id: rate}."""
        from datetime import datetime, timezone

        customer = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = customer.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")

        updated = 0
        for bow_id, rate in rates.items():
            result = await self.db.execute(
                select(BodyOfWater).where(BodyOfWater.id == bow_id, BodyOfWater.organization_id == org_id)
            )
            bow = result.scalar_one_or_none()
            if bow:
                bow.monthly_rate = round(rate, 2)
                bow.rate_allocation_method = "manual"
                bow.rate_allocated_at = datetime.now(timezone.utc)
                updated += 1

        await self.db.flush()
        return {"updated": updated, "customer_id": customer_id}

    async def get_profit_gaps(self, org_id: str) -> list[dict]:
        """Get all BOWs sorted by margin, flagging those below target."""
        settings = await self.get_or_create_settings(org_id)

        # Count total active accounts
        from sqlalchemy import func
        count_result = await self.db.execute(
            select(func.count(Customer.id)).where(Customer.organization_id == org_id, Customer.is_active == True)
        )
        total_accounts = count_result.scalar() or 1

        # Load all active BOWs with their property + customer
        result = await self.db.execute(
            select(BodyOfWater, Property, Customer)
            .join(Property, BodyOfWater.property_id == Property.id)
            .join(Customer, Property.customer_id == Customer.id)
            .where(
                BodyOfWater.organization_id == org_id,
                BodyOfWater.is_active == True,
                Customer.is_active == True,
            )
        )
        rows = result.all()

        # Count BOWs per property for travel/overhead split
        from collections import Counter
        prop_bow_counts = Counter(r[1].id for r in rows)

        # Load difficulty scores
        diff_map = {}
        prop_ids = list(set(r[1].id for r in rows))
        if prop_ids:
            diff_result = await self.db.execute(
                select(PropertyDifficulty).where(PropertyDifficulty.property_id.in_(prop_ids))
            )
            for d in diff_result.scalars().all():
                diff_map[d.property_id] = d

        # Load chemical profiles
        chem_map = {}
        bow_ids = [r[0].id for r in rows]
        if bow_ids:
            chem_result = await self.db.execute(
                select(ChemicalCostProfile).where(ChemicalCostProfile.body_of_water_id.in_(bow_ids))
            )
            for cp in chem_result.scalars().all():
                chem_map[cp.body_of_water_id] = cp

        gaps = []
        for bow, prop, customer in rows:
            diff = diff_map.get(prop.id)
            score = self.compute_composite_score(prop, diff, bows=[bow]) if diff else 2.5
            profile = chem_map.get(bow.id)

            cost_data = self.compute_bow_cost(
                settings=settings,
                bow=bow,
                difficulty_score=score,
                total_accounts=total_accounts,
                num_bows_at_property=prop_bow_counts[prop.id],
                chemical_profile=profile,
            )
            cost_data["customer_id"] = customer.id
            cost_data["customer_name"] = customer.display_name_col
            cost_data["property_address"] = prop.address
            cost_data["below_target"] = cost_data["margin_pct"] < settings.target_margin_pct
            gaps.append(cost_data)

        # Sort by margin ascending (worst first)
        gaps.sort(key=lambda g: g["margin_pct"])

        return gaps

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
        """Suggest a rate for a BOW.

        Residential: tier base_rate × difficulty_multiplier × volume_factor
        Commercial: cost-based calculation with target margin
        """
        settings = await self.get_or_create_settings(org_id)
        multiplier = self.difficulty_to_multiplier(difficulty_score)

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

                suggested_rate = tier.base_rate * multiplier * volume_factor

                # Load all tiers for comparison
                result = await self.db.execute(
                    select(ServiceTier)
                    .where(ServiceTier.organization_id == org_id, ServiceTier.is_active == True)
                    .order_by(ServiceTier.sort_order)
                )
                all_tiers = result.scalars().all()
                tier_options = []
                for t in all_tiers:
                    tier_rate = t.base_rate * multiplier * volume_factor
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
                    "difficulty_multiplier": round(multiplier, 2),
                    "volume_factor": round(volume_factor, 2),
                    "gallons": gallons,
                    "water_type": water_type,
                    "difficulty_score": round(difficulty_score, 2),
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
        overhead_cost = settings.monthly_overhead / max(total_accounts, 1)

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
