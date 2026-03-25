"""Profitability analysis service — cost breakdown, margins, overview aggregation.

Delegates difficulty scoring to DifficultyService and pricing/whale curve to PricingService.
"""

import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.models.org_cost_settings import OrgCostSettings
from src.models.property_difficulty import PropertyDifficulty
from src.models.property import Property
from src.models.customer import Customer
from src.models.water_feature import WaterFeature
from src.schemas.profitability import (
    CostBreakdown,
    WfCost,
    ProfitabilityAccount,
    ProfitabilityOverview,
    WhaleCurvePoint,
    PricingSuggestion,
    PropertyDifficultyResponse,
)
from src.core.exceptions import NotFoundError
from src.models.chemical_cost_profile import ChemicalCostProfile
from src.services.difficulty_service import DifficultyService
from src.services.pricing_service import PricingService


class ProfitabilityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._difficulty_svc = DifficultyService(db)
        self._pricing_svc = PricingService(db)

    # --- Delegate difficulty methods ---

    async def get_or_create_difficulty(self, org_id: str, property_id: str) -> PropertyDifficulty:
        return await self._difficulty_svc.get_or_create_difficulty(org_id, property_id)

    async def update_difficulty(self, org_id: str, property_id: str, **kwargs) -> PropertyDifficulty:
        return await self._difficulty_svc.update_difficulty(org_id, property_id, **kwargs)

    def compute_composite_score(
        self, prop: Property, diff: Optional[PropertyDifficulty],
        wfs: Optional[list[WaterFeature]] = None,
    ) -> float:
        return self._difficulty_svc.compute_composite_score(prop, diff, wfs=wfs)

    def difficulty_to_multiplier(self, score: float) -> float:
        return self._difficulty_svc.difficulty_to_multiplier(score)

    def get_difficulty_response(
        self, prop: Property, diff: PropertyDifficulty
    ) -> PropertyDifficultyResponse:
        return self._difficulty_svc.get_difficulty_response(prop, diff)

    # --- Delegate pricing methods ---

    async def get_whale_curve(self, org_id: str) -> list[WhaleCurvePoint]:
        return await self._pricing_svc.get_whale_curve(org_id)

    async def get_suggestions(self, org_id: str) -> list[PricingSuggestion]:
        return await self._pricing_svc.get_suggestions(org_id)

    async def suggest_rate(
        self, org_id: str, gallons: int, water_type: str = "pool",
        service_minutes: int = 30, difficulty_score: float = 2.5,
        customer_type: str = "residential", tier_id: str | None = None,
    ) -> dict:
        return await self._pricing_svc.suggest_rate(
            org_id=org_id, gallons=gallons, water_type=water_type,
            service_minutes=service_minutes, difficulty_score=difficulty_score,
            customer_type=customer_type, tier_id=tier_id,
        )

    # --- Settings ---

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

    # --- Overview & Analysis ---

    async def get_overview(
        self,
        org_id: str,
        tech_id: Optional[str] = None,
        min_margin: Optional[float] = None,
        max_margin: Optional[float] = None,
        min_difficulty: Optional[float] = None,
        max_difficulty: Optional[float] = None,
    ) -> ProfitabilityOverview:
        """Portfolio profitability overview — aggregated from per-WF costs."""
        settings = await self.get_or_create_settings(org_id)

        # Get only recurring active customers (exclude service_call, lead, inactive)
        query = select(Customer).where(Customer.organization_id == org_id, Customer.status == "active")
        result = await self.db.execute(query)
        customers = list(result.scalars().all())

        accounts: list[ProfitabilityAccount] = []
        for customer in customers:
            # Get all properties for this customer
            from src.models.property import Property as PropModel
            props_result = await self.db.execute(
                select(PropModel).where(PropModel.customer_id == customer.id, PropModel.is_active == True)
            )
            props = props_result.scalars().all()
            if not props:
                continue

            # Compute per-property profitability
            for prop in props:
                prop_wf_costs = await self._compute_property_cost(prop, customer, settings)
                if not prop_wf_costs:
                    continue

                total_gallons = sum(bc["gallons"] for bc in prop_wf_costs)
                total_svc_min = sum(bc["service_minutes"] for bc in prop_wf_costs)
                avg_difficulty = sum(bc["difficulty_score"] for bc in prop_wf_costs) / len(prop_wf_costs)
                avg_multiplier = sum(bc["difficulty_multiplier"] for bc in prop_wf_costs) / len(prop_wf_costs)

                total_cost = sum(bc["total_cost"] for bc in prop_wf_costs)
                revenue = prop.monthly_rate or sum(bc["monthly_rate"] for bc in prop_wf_costs)
                profit = revenue - total_cost
                margin_pct = (profit / revenue * 100) if revenue > 0 else 0.0
                target_margin = settings.target_margin_pct / 100.0
                suggested_rate = total_cost / (1 - target_margin) if target_margin < 1 else total_cost * 2
                rate_gap = suggested_rate - revenue

                cost = CostBreakdown(
                    chemical_cost=round(sum(bc["chemical_cost"] for bc in prop_wf_costs), 2),
                    labor_cost=round(sum(bc["labor_cost"] for bc in prop_wf_costs), 2),
                    travel_cost=round(sum(bc["travel_cost"] for bc in prop_wf_costs), 2),
                    overhead_cost=round(sum(bc["overhead_cost"] for bc in prop_wf_costs), 2),
                    total_cost=round(total_cost, 2),
                    revenue=round(revenue, 2),
                    profit=round(profit, 2),
                    margin_pct=round(margin_pct, 1),
                    suggested_rate=round(suggested_rate, 2),
                    rate_gap=round(rate_gap, 2),
                )

                # Apply filters
                if min_margin is not None and cost.margin_pct < min_margin:
                    continue
                if max_margin is not None and cost.margin_pct > max_margin:
                    continue
                if min_difficulty is not None and avg_difficulty < min_difficulty:
                    continue
                if max_difficulty is not None and avg_difficulty > max_difficulty:
                    continue

                rate_per_gallon = round(revenue / total_gallons, 4) if total_gallons and revenue > 0 else None

                display_name = customer.display_name_col
                if len(props) > 1:
                    display_name = f"{display_name} — {prop.name or prop.address}"

                accounts.append(ProfitabilityAccount(
                    customer_id=customer.id,
                    customer_name=display_name,
                    customer_type=customer.customer_type or "residential",
                    property_id=prop.id,
                    property_address=prop.address,
                    monthly_rate=round(revenue, 2),
                    pool_gallons=total_gallons,
                    pool_sqft=None,
                    estimated_service_minutes=total_svc_min,
                    difficulty_score=round(avg_difficulty, 2),
                    difficulty_multiplier=round(avg_multiplier, 2),
                    cost_breakdown=cost,
                    margin_pct=cost.margin_pct,
                    rate_per_gallon=rate_per_gallon,
                    wf_costs=[WfCost(**bc) for bc in prop_wf_costs],
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
        """Account detail — uses compute_account_cost() for single source of truth."""
        settings = await self.get_or_create_settings(org_id)

        result = await self.db.execute(
            select(Customer)
            .where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")

        cost, wf_costs = await self.compute_account_cost(customer, org_id, settings)

        total_gallons = sum(bc["gallons"] for bc in wf_costs)
        total_svc_min = sum(bc["service_minutes"] for bc in wf_costs)
        avg_difficulty = sum(bc["difficulty_score"] for bc in wf_costs) / len(wf_costs) if wf_costs else 2.5
        avg_multiplier = sum(bc["difficulty_multiplier"] for bc in wf_costs) / len(wf_costs) if wf_costs else 1.0

        rate_per_gallon = None
        if total_gallons and cost.revenue > 0:
            rate_per_gallon = round(cost.revenue / total_gallons, 4)

        prop_result = await self.db.execute(
            select(Property).where(Property.customer_id == customer.id, Property.is_active == True).limit(1)
        )
        prop = prop_result.scalar_one_or_none()

        return [ProfitabilityAccount(
            customer_id=customer.id,
            customer_name=customer.display_name_col,
            property_id=prop.id if prop else "",
            property_address=prop.address if prop else "",
            monthly_rate=cost.revenue,
            pool_gallons=total_gallons,
            pool_sqft=None,
            estimated_service_minutes=total_svc_min,
            difficulty_score=round(avg_difficulty, 2),
            difficulty_multiplier=round(avg_multiplier, 2),
            cost_breakdown=cost,
            margin_pct=cost.margin_pct,
            rate_per_gallon=rate_per_gallon,
            wf_costs=[WfCost(**bc) for bc in wf_costs],
        )]

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

    # --- Rate Allocation ---

    @staticmethod
    def allocate_rate_to_wfs(total_rate: float, wfs: list[WaterFeature]) -> dict[str, dict]:
        """Allocate a property's total rate across its WFs.

        Returns dict of wf_id -> {allocated_rate, allocation_method, weight}

        Priority: gallons > sqft > service_time > type_weighting
        """
        if not wfs or total_rate <= 0:
            return {}

        if len(wfs) == 1:
            return {wfs[0].id: {"allocated_rate": total_rate, "allocation_method": "sole", "weight": 1.0}}

        TYPE_WEIGHTS = {
            "pool": 1.0,
            "spa": 0.25,
            "hot_tub": 0.20,
            "wading_pool": 0.15,
            "fountain": 0.10,
            "water_feature": 0.10,
        }

        # Try gallons
        gallons = [(b, b.pool_gallons or 0) for b in wfs]
        total_gal = sum(g for _, g in gallons)
        if total_gal > 0 and all(g > 0 for _, g in gallons):
            result = {}
            for b, g in gallons:
                w = g / total_gal
                result[b.id] = {"allocated_rate": round(total_rate * w, 2), "allocation_method": "gallons", "weight": round(w, 4)}
            return result

        # Try sqft
        sqfts = [(b, b.pool_sqft or 0) for b in wfs]
        total_sqft = sum(s for _, s in sqfts)
        if total_sqft > 0 and all(s > 0 for _, s in sqfts):
            result = {}
            for b, s in sqfts:
                w = s / total_sqft
                result[b.id] = {"allocated_rate": round(total_rate * w, 2), "allocation_method": "sqft", "weight": round(w, 4)}
            return result

        # Try service time
        times = [(b, b.estimated_service_minutes or 0) for b in wfs]
        total_time = sum(t for _, t in times)
        if total_time > 0 and all(t > 0 for _, t in times):
            result = {}
            for b, t in times:
                w = t / total_time
                result[b.id] = {"allocated_rate": round(total_rate * w, 2), "allocation_method": "service_time", "weight": round(w, 4)}
            return result

        # Type weighting (always available)
        weights = [(b, TYPE_WEIGHTS.get(b.water_type, 0.5)) for b in wfs]
        total_w = sum(w for _, w in weights)
        result = {}
        for b, w in weights:
            ratio = w / total_w if total_w > 0 else 1.0 / len(wfs)
            result[b.id] = {"allocated_rate": round(total_rate * ratio, 2), "allocation_method": "type_weight", "weight": round(ratio, 4)}
        return result

    async def get_rate_allocation_preview(self, customer_id: str, org_id: str) -> dict:
        """Preview rate allocation for a customer's WFs without saving."""
        customer = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = customer.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")

        # Get all properties + WFs
        props = await self.db.execute(
            select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
        )
        properties = props.scalars().all()
        prop_ids = [p.id for p in properties]

        bows_result = await self.db.execute(
            select(WaterFeature).where(WaterFeature.property_id.in_(prop_ids), WaterFeature.is_active == True)
        )
        wfs = bows_result.scalars().all()

        if not wfs:
            return {"customer_id": customer_id, "total_rate": customer.monthly_rate, "allocations": [], "method": None}

        allocation = self.allocate_rate_to_wfs(customer.monthly_rate, wfs)

        allocations = []
        method = None
        for wf in wfs:
            alloc = allocation.get(wf.id, {})
            method = alloc.get("allocation_method", method)
            allocations.append({
                "wf_id": wf.id,
                "bow_name": wf.name,
                "water_type": wf.water_type,
                "gallons": wf.pool_gallons,
                "service_minutes": wf.estimated_service_minutes,
                "current_rate": wf.monthly_rate,
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
        """Apply per-WF rates. rates = {wf_id: rate}."""
        from datetime import datetime, timezone

        customer = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = customer.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer not found")

        from src.services.rate_sync import sync_rates_for_property

        updated = 0
        affected_property_ids = set()
        for wf_id, rate in rates.items():
            result = await self.db.execute(
                select(WaterFeature).where(WaterFeature.id == wf_id, WaterFeature.organization_id == org_id)
            )
            wf = result.scalar_one_or_none()
            if wf:
                wf.monthly_rate = round(rate, 2)
                wf.rate_allocation_method = "manual"
                wf.rate_allocated_at = datetime.now(timezone.utc)
                affected_property_ids.add(wf.property_id)
                updated += 1

        await self.db.flush()

        # Sync property + customer rates
        for prop_id in affected_property_ids:
            await sync_rates_for_property(self.db, prop_id)

        return {"updated": updated, "customer_id": customer_id}

    # --- Cost Computation ---

    def compute_wf_cost(
        self,
        settings: OrgCostSettings,
        wf: WaterFeature,
        difficulty_score: float,
        num_wfs_at_property: int,
        customer_type: str = "residential",
        chemical_profile: Optional[ChemicalCostProfile] = None,
        difficulty: Optional[PropertyDifficulty] = None,
    ) -> dict:
        """Compute cost breakdown for a single WF.

        Residential: flat dollar adjustments per visit from difficulty factors.
        Commercial: multiplier-based scaling from composite difficulty score.
        Travel and overhead are split across WFs at the same property.
        """
        visits = settings.visits_per_month

        # Type-aware gallon defaults
        if wf.pool_gallons:
            gallons = wf.pool_gallons
        elif wf.water_type in ("spa", "hot_tub"):
            gallons = 800
        elif wf.water_type in ("wading_pool",):
            gallons = 800
        elif wf.water_type in ("fountain", "water_feature"):
            gallons = 500
        elif customer_type == "commercial":
            gallons = 25000
        else:
            gallons = 15000
        service_minutes = wf.estimated_service_minutes or 30

        if customer_type == "commercial":
            # Commercial: multiplier-based (0.8x to 1.6x)
            multiplier = self.difficulty_to_multiplier(difficulty_score)
            difficulty_adjustment = 0.0
        else:
            # Residential: flat dollar adjustments per visit, no multiplier
            multiplier = 1.0
            if difficulty:
                difficulty_adjustment = (
                    (difficulty.res_tree_debris or 0)
                    + (difficulty.res_dog or 0)
                    + (difficulty.res_customer_demands or 0)
                    + (difficulty.res_system_effectiveness or 0)
                ) * visits
            else:
                difficulty_adjustment = 0.0

        # Chemical cost
        if chemical_profile and chemical_profile.total_monthly > 0:
            chemical_cost = chemical_profile.total_monthly
        else:
            chemical_cost = (gallons / 10000.0) * settings.chemical_cost_per_gallon * multiplier * visits

        # Labor cost
        labor_cost = (service_minutes / 60.0) * settings.burdened_labor_rate * visits * multiplier

        # Travel cost — split across WFs at the property (one trip)
        full_travel = (
            (settings.avg_drive_minutes / 60.0) * settings.burdened_labor_rate
            + settings.avg_drive_miles * settings.vehicle_cost_per_mile
        ) * visits
        travel_cost = full_travel / max(num_wfs_at_property, 1)

        # Overhead — per account type, split across WFs at property
        if customer_type == "commercial":
            full_overhead = settings.commercial_overhead_per_account
        else:
            full_overhead = settings.residential_overhead_per_account
        overhead_cost = full_overhead / max(num_wfs_at_property, 1)

        total_cost = chemical_cost + labor_cost + travel_cost + overhead_cost + difficulty_adjustment
        revenue = wf.monthly_rate or 0.0
        profit = revenue - total_cost
        margin_pct = (profit / revenue * 100) if revenue > 0 else 0.0
        target_margin = settings.target_margin_pct / 100.0
        suggested_rate = total_cost / (1 - target_margin) if target_margin < 1 else total_cost * 2
        rate_gap = suggested_rate - revenue

        return {
            "wf_id": wf.id,
            "bow_name": wf.name,
            "water_type": wf.water_type,
            "gallons": gallons,
            "service_minutes": service_minutes,
            "monthly_rate": revenue,
            "chemical_cost": round(chemical_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "travel_cost": round(travel_cost, 2),
            "overhead_cost": round(overhead_cost, 2),
            "difficulty_adjustment": round(difficulty_adjustment, 2),
            "total_cost": round(total_cost, 2),
            "profit": round(profit, 2),
            "margin_pct": round(margin_pct, 1),
            "suggested_rate": round(suggested_rate, 2),
            "rate_gap": round(rate_gap, 2),
            "difficulty_score": round(difficulty_score, 2),
            "difficulty_multiplier": round(multiplier, 2),
        }

    async def _compute_property_cost(
        self,
        prop: Property,
        customer: Customer,
        settings: OrgCostSettings,
    ) -> list[dict]:
        """Compute per-WF costs for a single property. Returns list of wf cost dicts."""
        from collections import Counter

        bows_result = await self.db.execute(
            select(WaterFeature).where(WaterFeature.property_id == prop.id, WaterFeature.is_active == True)
        )
        wfs = bows_result.scalars().all()
        if not wfs:
            return []

        num_bows = len(wfs)

        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.property_id == prop.id)
        )
        diff = diff_result.scalar_one_or_none()

        wf_ids = [b.id for b in wfs]
        chem_result = await self.db.execute(
            select(ChemicalCostProfile).where(ChemicalCostProfile.water_feature_id.in_(wf_ids))
        )
        chem_map = {cp.water_feature_id: cp for cp in chem_result.scalars().all()}

        wf_costs = []
        for wf in wfs:
            score = self.compute_composite_score(prop, diff, wfs=[wf]) if diff else 2.5
            bc = self.compute_wf_cost(
                settings=settings,
                wf=wf,
                difficulty_score=score,
                num_wfs_at_property=num_bows,
                customer_type=customer.customer_type or "residential",
                chemical_profile=chem_map.get(wf.id),
                difficulty=diff,
            )
            wf_costs.append(bc)

        return wf_costs

    async def compute_account_cost(
        self,
        customer: Customer,
        org_id: str,
        settings: Optional[OrgCostSettings] = None,
    ) -> tuple[CostBreakdown, list[dict]]:
        """Compute account-level cost by aggregating per-WF costs.

        Returns (CostBreakdown, wf_costs) where CostBreakdown is the aggregate
        and wf_costs is the per-WF detail list.
        """
        if not settings:
            settings = await self.get_or_create_settings(org_id)

        # Load WFs with properties
        props_result = await self.db.execute(
            select(Property).where(Property.customer_id == customer.id, Property.is_active == True)
        )
        properties = props_result.scalars().all()
        prop_ids = [p.id for p in properties]

        if not prop_ids:
            return CostBreakdown(
                chemical_cost=0, labor_cost=0, travel_cost=0, overhead_cost=0,
                total_cost=0, revenue=0, profit=0, margin_pct=0,
                suggested_rate=0, rate_gap=0,
            ), []

        bows_result = await self.db.execute(
            select(WaterFeature).where(WaterFeature.property_id.in_(prop_ids), WaterFeature.is_active == True)
        )
        wfs = bows_result.scalars().all()

        if not wfs:
            return CostBreakdown(
                chemical_cost=0, labor_cost=0, travel_cost=0, overhead_cost=0,
                total_cost=0, revenue=0, profit=0, margin_pct=0,
                suggested_rate=0, rate_gap=0,
            ), []

        # Count WFs per property for travel/overhead split
        from collections import Counter
        prop_wf_counts = Counter(b.property_id for b in wfs)

        # Load difficulty scores
        diff_map = {}
        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.property_id.in_(prop_ids))
        )
        for d in diff_result.scalars().all():
            diff_map[d.property_id] = d

        # Load chemical profiles
        chem_map = {}
        wf_ids = [b.id for b in wfs]
        chem_result = await self.db.execute(
            select(ChemicalCostProfile).where(ChemicalCostProfile.water_feature_id.in_(wf_ids))
        )
        for cp in chem_result.scalars().all():
            chem_map[cp.water_feature_id] = cp

        # Compute per-WF costs
        wf_costs = []
        total_chem = 0.0
        total_labor = 0.0
        total_travel = 0.0
        total_overhead = 0.0

        for wf in wfs:
            # Find property for this WF
            prop = next((p for p in properties if p.id == wf.property_id), None)
            diff = diff_map.get(wf.property_id)
            score = self.compute_composite_score(prop, diff, wfs=[wf]) if diff and prop else 2.5
            profile = chem_map.get(wf.id)

            bc = self.compute_wf_cost(
                settings=settings,
                wf=wf,
                difficulty_score=score,
                num_wfs_at_property=prop_wf_counts[wf.property_id],
                customer_type=customer.customer_type or "residential",
                chemical_profile=profile,
                difficulty=diff,
            )
            wf_costs.append(bc)
            total_chem += bc["chemical_cost"]
            total_labor += bc["labor_cost"]
            total_travel += bc["travel_cost"]
            total_overhead += bc["overhead_cost"]

        total_cost = total_chem + total_labor + total_travel + total_overhead
        revenue = sum(b.monthly_rate or 0 for b in wfs)
        profit = revenue - total_cost
        margin_pct = (profit / revenue * 100) if revenue > 0 else 0.0
        target_margin = settings.target_margin_pct / 100.0
        suggested_rate = total_cost / (1 - target_margin) if target_margin < 1 else total_cost * 2
        rate_gap = suggested_rate - revenue

        breakdown = CostBreakdown(
            chemical_cost=round(total_chem, 2),
            labor_cost=round(total_labor, 2),
            travel_cost=round(total_travel, 2),
            overhead_cost=round(total_overhead, 2),
            total_cost=round(total_cost, 2),
            revenue=round(revenue, 2),
            profit=round(profit, 2),
            margin_pct=round(margin_pct, 1),
            suggested_rate=round(suggested_rate, 2),
            rate_gap=round(rate_gap, 2),
        )

        return breakdown, wf_costs

    # --- Profit Gaps ---

    async def get_profit_gaps(self, org_id: str) -> list[dict]:
        """Get all WFs sorted by margin, flagging those below target."""
        settings = await self.get_or_create_settings(org_id)

        # Count total active accounts
        from sqlalchemy import func
        count_result = await self.db.execute(
            select(func.count(Customer.id)).where(Customer.organization_id == org_id, Customer.status == "active")
        )
        total_accounts = count_result.scalar() or 1

        # Load all active WFs with their property + customer (recurring active only)
        result = await self.db.execute(
            select(WaterFeature, Property, Customer)
            .join(Property, WaterFeature.property_id == Property.id)
            .join(Customer, Property.customer_id == Customer.id)
            .where(
                WaterFeature.organization_id == org_id,
                WaterFeature.is_active == True,
                Customer.status == "active",
            )
        )
        rows = result.all()

        # Count WFs per property for travel/overhead split
        from collections import Counter
        prop_wf_counts = Counter(r[1].id for r in rows)

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
        wf_ids = [r[0].id for r in rows]
        if wf_ids:
            chem_result = await self.db.execute(
                select(ChemicalCostProfile).where(ChemicalCostProfile.water_feature_id.in_(wf_ids))
            )
            for cp in chem_result.scalars().all():
                chem_map[cp.water_feature_id] = cp

        gaps = []
        for wf, prop, customer in rows:
            diff = diff_map.get(prop.id)
            score = self.compute_composite_score(prop, diff, wfs=[wf]) if diff else 2.5
            profile = chem_map.get(wf.id)

            cost_data = self.compute_wf_cost(
                settings=settings,
                wf=wf,
                difficulty_score=score,
                num_wfs_at_property=prop_wf_counts[prop.id],
                customer_type=customer.customer_type or "residential",
                chemical_profile=profile,
                difficulty=diff,
            )
            cost_data["customer_id"] = customer.id
            cost_data["customer_name"] = customer.display_name_col
            cost_data["customer_type"] = customer.customer_type or "residential"
            cost_data["property_address"] = prop.address
            cost_data["below_target"] = cost_data["margin_pct"] < settings.target_margin_pct
            gaps.append(cost_data)

        # Sort by margin ascending (worst first)
        gaps.sort(key=lambda g: g["margin_pct"])

        return gaps
