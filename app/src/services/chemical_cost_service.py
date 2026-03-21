"""Chemical cost engine — computes per-BOW monthly chemical costs using regional defaults,
org price overrides, environment adjustments from satellite/difficulty data."""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.regional_default import RegionalDefault
from src.models.org_chemical_prices import OrgChemicalPrices
from src.models.chemical_cost_profile import ChemicalCostProfile
from src.models.body_of_water import BodyOfWater
from src.models.satellite_analysis import SatelliteAnalysis
from src.models.property_difficulty import PropertyDifficulty
from src.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)

# Conversion: 128 oz per gallon
OZ_PER_GALLON = 128.0

# Tabs: a 50lb bucket contains ~800oz of product. Price is per bucket.
TABS_BUCKET_OZ = 800.0

# Standard visits per month (weekly service)
VISITS_PER_MONTH = 4.0

# Default region when org has none configured
DEFAULT_REGION = "sacramento_ca"
FALLBACK_REGION = "national"

# Map sanitizer_type to the OrgChemicalPrices field that overrides its price
SANITIZER_PRICE_FIELD_MAP = {
    "liquid": "liquid_chlorine_per_gal",
    "tabs": "tabs_per_bucket",
    "cal_hypo": "cal_hypo_per_lb",
    "dichlor": "dichlor_per_lb",
    "salt": "salt_per_bag",
    "bromine": "bromine_per_lb",
}

# Map sanitizer_type to the unit conversion factor (oz of product per unit of purchase)
# For "liquid": 1 gallon = 128 oz, so usage_oz / 128 * price_per_gal
# For "tabs": 1 bucket = 800 oz, so usage_oz / 800 * price_per_bucket
# For "lb" types: 1 lb = 16 oz, so usage_oz / 16 * price_per_lb
# For "salt": sanitizer_usage_oz is 0 (cell generates), cost comes from salt_bags_per_year
# For "bag" (salt): 1 bag = 640 oz (40lb), but we use bags_per_year directly
UNIT_OZ_MAP = {
    "gallon": OZ_PER_GALLON,
    "bucket": TABS_BUCKET_OZ,
    "lb": 16.0,
    "bag": 640.0,  # 40lb bag
}


def estimate_volume(bow: BodyOfWater) -> int:
    """Estimate pool volume from area + depth + structure.

    Uses shallow/deep depths when available, applies reductions for steps and
    bench/sun shelves to produce a more accurate cubic-foot-to-gallon estimate.
    """
    if bow.pool_gallons:
        return bow.pool_gallons  # User-entered, always wins

    # Type-based defaults when no data available
    DEFAULT_GALLONS = {
        "pool": 15000,
        "spa": 800,
        "hot_tub": 800,
        "wading_pool": 800,
        "fountain": 500,
        "water_feature": 500,
    }

    sqft = bow.pool_sqft
    if not sqft:
        base = DEFAULT_GALLONS.get(bow.water_type, 15000)
        # Commercial pools are larger
        if bow.water_type == "pool" and bow.pool_type == "commercial":
            base = 25000
        return base

    # Average depth from shallow + deep
    shallow = bow.pool_depth_shallow
    deep = bow.pool_depth_deep
    if shallow and deep:
        avg_depth = (shallow + deep) / 2
    elif bow.pool_depth_avg:
        avg_depth = bow.pool_depth_avg
    elif bow.water_type in ("spa", "hot_tub"):
        avg_depth = 3.0
    elif bow.water_type == "wading_pool":
        avg_depth = 1.25
    elif bow.pool_type == "commercial" or (sqft and sqft > 800):
        avg_depth = 4.0
    elif sqft and sqft < 400:
        avg_depth = 4.0
    else:
        avg_depth = 4.5

    base_volume_cuft = sqft * avg_depth

    # Step reduction: each step entry ~15 sqft, depth difference from step to shallow
    step_reduction = 0.0
    if bow.step_entry_count and bow.step_entry_count > 0 and shallow:
        step_area = bow.step_entry_count * 15  # ~15 sqft per step entry
        step_depth_saved = shallow * 0.5  # Steps are about half the shallow depth
        step_reduction = step_area * step_depth_saved

    # Bench/shelf reduction: ~10% of area at ~1ft depth instead of avg
    shelf_reduction = 0.0
    if bow.has_bench_shelf and avg_depth > 1.5:
        shelf_area = sqft * 0.10  # ~10% of pool area
        shelf_depth_saved = avg_depth - 1.0  # Shelf is ~1ft deep
        shelf_reduction = shelf_area * shelf_depth_saved

    adjusted_cuft = base_volume_cuft - step_reduction - shelf_reduction
    return max(int(adjusted_cuft * 7.48), 100)


class ChemicalCostService:
    """Computes and caches per-BOW monthly chemical costs."""

    # Environment adjustments based on satellite analysis and property difficulty
    ENVIRONMENT_ADJUSTMENTS = {
        "canopy_high": {
            "field": "canopy_overhang_pct",
            "threshold": 30,
            "sanitizer_adj": 0.15,
            "acid_adj": 0.20,
            "note": "High canopy overhang +{pct}%",
        },
        "shade_full": {
            "field": "shade_exposure",
            "value": "full_shade",
            "sanitizer_adj": -0.10,
            "acid_adj": 0.10,
            "note": "Full shade san-10%/acid+10%",
        },
        "debris_heavy": {
            "field": "tree_debris_level",
            "value": "heavy",
            "sanitizer_adj": 0.25,
            "acid_adj": 0.10,
            "note": "Heavy debris +25% sanitizer",
        },
        "indoor": {
            "field": "enclosure_type",
            "value": "indoor",
            "sanitizer_adj": -0.30,
            "acid_adj": -0.20,
            "note": "Indoor pool -30% sanitizer",
        },
        "commercial": {
            "field": "pool_type",
            "value": "commercial",
            "sanitizer_adj": 0.20,
            "acid_adj": 0.15,
            "note": "Commercial pool +20% sanitizer",
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_regional_defaults(self, region_key: str, sanitizer_type: str) -> RegionalDefault:
        """Get regional defaults, falling back to national."""
        result = await self.db.execute(
            select(RegionalDefault).where(
                RegionalDefault.region_key == region_key,
                RegionalDefault.sanitizer_type == sanitizer_type,
            )
        )
        default = result.scalar_one_or_none()
        if default:
            return default

        # Fallback to national
        if region_key != FALLBACK_REGION:
            result = await self.db.execute(
                select(RegionalDefault).where(
                    RegionalDefault.region_key == FALLBACK_REGION,
                    RegionalDefault.sanitizer_type == sanitizer_type,
                )
            )
            default = result.scalar_one_or_none()
            if default:
                return default

        # Last resort: national liquid
        result = await self.db.execute(
            select(RegionalDefault).where(
                RegionalDefault.region_key == FALLBACK_REGION,
                RegionalDefault.sanitizer_type == "liquid",
            )
        )
        default = result.scalar_one_or_none()
        if not default:
            raise NotFoundError(f"No regional defaults found for {region_key}/{sanitizer_type}")
        return default

    async def get_all_regional_defaults(self, region_key: str) -> list[RegionalDefault]:
        """Get all sanitizer type defaults for a region."""
        result = await self.db.execute(
            select(RegionalDefault).where(RegionalDefault.region_key == region_key)
            .order_by(RegionalDefault.sanitizer_type)
        )
        defaults = list(result.scalars().all())
        if not defaults:
            # Fallback to national
            result = await self.db.execute(
                select(RegionalDefault).where(RegionalDefault.region_key == FALLBACK_REGION)
                .order_by(RegionalDefault.sanitizer_type)
            )
            defaults = list(result.scalars().all())
        return defaults

    async def get_org_prices(self, org_id: str) -> Optional[OrgChemicalPrices]:
        """Return org price overrides or None."""
        result = await self.db.execute(
            select(OrgChemicalPrices).where(OrgChemicalPrices.organization_id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_org_prices(self, org_id: str) -> OrgChemicalPrices:
        """Get or create org chemical prices record."""
        prices = await self.get_org_prices(org_id)
        if not prices:
            prices = OrgChemicalPrices(
                id=str(uuid.uuid4()),
                organization_id=org_id,
            )
            self.db.add(prices)
            await self.db.flush()
            await self.db.refresh(prices)
        return prices

    def get_effective_price(
        self,
        sanitizer_type: str,
        org_prices: Optional[OrgChemicalPrices],
        regional: RegionalDefault,
    ) -> dict:
        """Merge prices: org override > regional default.

        Returns dict with sanitizer_price, sanitizer_unit, acid_price, cya_price, salt_price.
        """
        sanitizer_price = regional.sanitizer_price_per_unit or 0.0
        sanitizer_unit = regional.sanitizer_unit or "gallon"
        acid_price = regional.acid_price_per_gallon
        cya_price = regional.cya_price_per_lb
        salt_price = regional.salt_price_per_bag

        if org_prices:
            # Override sanitizer price from org
            field = SANITIZER_PRICE_FIELD_MAP.get(sanitizer_type)
            if field:
                org_val = getattr(org_prices, field, None)
                if org_val is not None:
                    sanitizer_price = org_val

            # Override acid, CYA, salt
            if org_prices.acid_per_gal is not None:
                acid_price = org_prices.acid_per_gal
            if org_prices.cya_per_lb is not None:
                cya_price = org_prices.cya_per_lb
            if org_prices.salt_per_bag is not None:
                salt_price = org_prices.salt_per_bag

        return {
            "sanitizer_price": sanitizer_price,
            "sanitizer_unit": sanitizer_unit,
            "acid_price": acid_price,
            "cya_price": cya_price,
            "salt_price": salt_price,
        }

    def compute_adjustments(
        self,
        satellite_data: Optional[dict],
        difficulty_data: Optional[dict],
        pool_type: Optional[str],
    ) -> dict:
        """Compute environment adjustment factors based on satellite analysis and difficulty scores.

        Returns {"sanitizer_factor": 1.15, "acid_factor": 1.20, "notes": [...], "adjustments": {...}}
        """
        sanitizer_adj = 0.0
        acid_adj = 0.0
        notes = []
        adjustments = {}

        combined = {}
        if satellite_data:
            combined.update(satellite_data)
        if difficulty_data:
            combined.update(difficulty_data)
        if pool_type:
            combined["pool_type"] = pool_type

        for adj_key, config in self.ENVIRONMENT_ADJUSTMENTS.items():
            field = config["field"]
            value = combined.get(field)
            if value is None:
                continue

            triggered = False
            if "threshold" in config:
                if isinstance(value, (int, float)) and value >= config["threshold"]:
                    triggered = True
            elif "value" in config:
                val_str = value.value if hasattr(value, "value") else str(value)
                if val_str == config["value"]:
                    triggered = True

            if triggered:
                san_pct = config["sanitizer_adj"]
                acid_pct = config["acid_adj"]
                sanitizer_adj += san_pct
                acid_adj += acid_pct
                adjustments[adj_key] = {"sanitizer": san_pct, "acid": acid_pct}
                notes.append(config["note"].format(pct=int(abs(san_pct) * 100)))

        return {
            "sanitizer_factor": 1.0 + sanitizer_adj,
            "acid_factor": 1.0 + acid_adj,
            "notes": notes,
            "adjustments": adjustments,
        }

    async def compute_bow_chemical_cost(
        self,
        org_id: str,
        bow: BodyOfWater,
        region_key: str = DEFAULT_REGION,
        satellite_analysis: Optional[SatelliteAnalysis] = None,
        difficulty: Optional[PropertyDifficulty] = None,
    ) -> ChemicalCostProfile:
        """Compute monthly chemical cost for a single body of water.

        Computation:
        1. Get gallons (or estimate from sqft)
        2. Get sanitizer type (or default to "liquid")
        3. Get prices (org override > regional > national)
        4. Get usage rates (BOW override > regional)
        5. Get environment adjustments
        6. Compute monthly costs
        7. Save/update ChemicalCostProfile
        """
        # 1. Gallons — use structure-aware estimation
        gallons = estimate_volume(bow)

        units_10k = gallons / 10000.0

        # 2. Sanitizer type
        sanitizer_type = bow.sanitizer_type or "liquid"
        # Normalize some common aliases
        type_map = {"trichlor": "tabs", "chlorine": "liquid"}
        sanitizer_type = type_map.get(sanitizer_type, sanitizer_type)

        # 3. Prices
        regional = await self.get_regional_defaults(region_key, sanitizer_type)
        org_prices = await self.get_org_prices(org_id)
        prices = self.get_effective_price(sanitizer_type, org_prices, regional)

        # 4. Usage rates (BOW override > regional)
        # Check for existing profile with overrides
        existing = await self._get_existing_profile(bow.id)
        sanitizer_usage_oz = regional.sanitizer_usage_oz
        acid_usage_oz = regional.acid_usage_oz
        if existing and existing.sanitizer_usage_override_oz is not None:
            sanitizer_usage_oz = existing.sanitizer_usage_override_oz
        if existing and existing.acid_usage_override_oz is not None:
            acid_usage_oz = existing.acid_usage_override_oz

        # 5. Environment adjustments
        sat_data = None
        if satellite_analysis:
            sat_data = {
                "canopy_overhang_pct": satellite_analysis.canopy_overhang_pct,
            }

        diff_data = None
        if difficulty:
            diff_data = {}
            if difficulty.shade_exposure:
                diff_data["shade_exposure"] = difficulty.shade_exposure
            if difficulty.tree_debris_level:
                diff_data["tree_debris_level"] = difficulty.tree_debris_level
            if difficulty.enclosure_type:
                diff_data["enclosure_type"] = difficulty.enclosure_type

        pool_type = bow.pool_type
        adj = self.compute_adjustments(sat_data, diff_data, pool_type)
        san_factor = adj["sanitizer_factor"]
        acid_factor = adj["acid_factor"]

        # 6. Compute costs
        unit_oz = UNIT_OZ_MAP.get(prices["sanitizer_unit"], OZ_PER_GALLON)

        # Sanitizer: (usage_oz / oz_per_unit) * price_per_unit * (gallons/10000) * adj * visits
        if sanitizer_usage_oz > 0:
            sanitizer_cost = (
                (sanitizer_usage_oz / unit_oz)
                * prices["sanitizer_price"]
                * units_10k
                * san_factor
                * VISITS_PER_MONTH
            )
        else:
            sanitizer_cost = 0.0

        # Acid: (acid_oz / 128) * acid_price_per_gal * (gallons/10000) * adj * visits
        acid_cost = (
            (acid_usage_oz / OZ_PER_GALLON)
            * prices["acid_price"]
            * units_10k
            * acid_factor
            * VISITS_PER_MONTH
        )

        # CYA: near-zero for established pools
        # Tabs/dichlor add CYA with every dose — $0 standalone CYA cost
        # Bromine doesn't use CYA
        # Liquid/cal_hypo/salt: one-time establishment, ~$0-2/mo amortized for top-offs
        cya_cost = 0.0  # Established pools don't need ongoing CYA

        # Salt: only applies to salt-system pools
        if sanitizer_type == "salt":
            salt_cost = regional.salt_bags_per_year_per_10k * prices["salt_price"] * units_10k / 12.0
        else:
            salt_cost = 0.0

        # Salt cell amortization: only for salt pools
        cell_cost = regional.salt_cell_replacement_cost if sanitizer_type == "salt" else 0.0

        # Insurance chemicals (phosphate remover, enzyme, algaecide): per 10k gal/month
        insurance_cost = regional.insurance_chemicals_monthly * units_10k

        total_monthly = sanitizer_cost + acid_cost + cya_cost + salt_cost + cell_cost + insurance_cost

        # 7. Save/update profile, respecting user overrides
        overrides = {}
        if existing and existing.overrides:
            overrides = existing.overrides
            # Preserve user-overridden fields
            if overrides.get("sanitizer_cost") and existing.source == "user_override":
                sanitizer_cost = existing.sanitizer_cost
            if overrides.get("acid_cost") and existing.source == "user_override":
                acid_cost = existing.acid_cost
            if overrides.get("cya_cost") and existing.source == "user_override":
                cya_cost = existing.cya_cost
            if overrides.get("salt_cost") and existing.source == "user_override":
                salt_cost = existing.salt_cost
            total_monthly = sanitizer_cost + acid_cost + cya_cost + salt_cost + cell_cost + insurance_cost

        now = datetime.now(timezone.utc)

        if existing:
            existing.sanitizer_cost = round(sanitizer_cost, 2)
            existing.acid_cost = round(acid_cost, 2)
            existing.cya_cost = round(cya_cost, 2)
            existing.salt_cost = round(salt_cost, 2)
            existing.cell_cost = round(cell_cost, 2)
            existing.insurance_cost = round(insurance_cost, 2)
            existing.total_monthly = round(total_monthly, 2)
            existing.adjustments_applied = adj.get("adjustments") or None
            existing.last_computed = now
            if not overrides:
                existing.source = "computed"
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        else:
            profile = ChemicalCostProfile(
                id=str(uuid.uuid4()),
                body_of_water_id=bow.id,
                organization_id=org_id,
                sanitizer_cost=round(sanitizer_cost, 2),
                acid_cost=round(acid_cost, 2),
                cya_cost=round(cya_cost, 2),
                salt_cost=round(salt_cost, 2),
                cell_cost=round(cell_cost, 2),
                insurance_cost=round(insurance_cost, 2),
                total_monthly=round(total_monthly, 2),
                source="computed",
                adjustments_applied=adj.get("adjustments") or None,
                last_computed=now,
            )
            self.db.add(profile)
            await self.db.flush()
            await self.db.refresh(profile)
            return profile

    async def _get_existing_profile(self, bow_id: str) -> Optional[ChemicalCostProfile]:
        result = await self.db.execute(
            select(ChemicalCostProfile).where(ChemicalCostProfile.body_of_water_id == bow_id)
        )
        return result.scalar_one_or_none()

    async def get_or_compute(
        self,
        org_id: str,
        bow_id: str,
        region_key: str = DEFAULT_REGION,
    ) -> ChemicalCostProfile:
        """Get existing profile or compute a new one."""
        existing = await self._get_existing_profile(bow_id)
        if existing:
            return existing

        # Need to load the BOW
        result = await self.db.execute(
            select(BodyOfWater).where(BodyOfWater.id == bow_id, BodyOfWater.organization_id == org_id)
        )
        bow = result.scalar_one_or_none()
        if not bow:
            raise NotFoundError("Body of water not found")

        # Load satellite analysis for the property
        sat_result = await self.db.execute(
            select(SatelliteAnalysis).where(SatelliteAnalysis.property_id == bow.property_id)
        )
        satellite = sat_result.scalar_one_or_none()

        # Load difficulty
        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.property_id == bow.property_id)
        )
        difficulty = diff_result.scalar_one_or_none()

        return await self.compute_bow_chemical_cost(
            org_id, bow, region_key=region_key,
            satellite_analysis=satellite, difficulty=difficulty,
        )

    async def update_org_prices(self, org_id: str, **kwargs) -> OrgChemicalPrices:
        """Update org-level chemical prices."""
        prices = await self.get_or_create_org_prices(org_id)
        for key, value in kwargs.items():
            if hasattr(prices, key):
                setattr(prices, key, value)
        await self.db.flush()
        await self.db.refresh(prices)
        return prices

    async def update_bow_overrides(self, org_id: str, bow_id: str, **kwargs) -> ChemicalCostProfile:
        """Update BOW-level cost overrides."""
        profile = await self._get_existing_profile(bow_id)
        if not profile:
            # Compute first, then override
            profile = await self.get_or_compute(org_id, bow_id)

        overrides = profile.overrides or {}
        cost_fields = {"sanitizer_cost", "acid_cost", "cya_cost", "salt_cost"}
        usage_fields = {"sanitizer_usage_override_oz", "acid_usage_override_oz"}

        for key, value in kwargs.items():
            if key in cost_fields and value is not None:
                setattr(profile, key, value)
                overrides[key] = True
                profile.source = "user_override"
            elif key in usage_fields:
                setattr(profile, key, value)

        profile.overrides = overrides if overrides else None

        # Recompute total
        profile.total_monthly = round(
            profile.sanitizer_cost + profile.acid_cost + profile.cya_cost + profile.salt_cost, 2
        )

        await self.db.flush()
        await self.db.refresh(profile)
        return profile

    async def recompute_all(self, org_id: str, region_key: str = DEFAULT_REGION) -> int:
        """Recompute all BOW chemical costs for an org. Returns count recomputed."""
        # Load all active BOWs
        bow_result = await self.db.execute(
            select(BodyOfWater).where(
                BodyOfWater.organization_id == org_id,
                BodyOfWater.is_active == True,
            )
        )
        bows = list(bow_result.scalars().all())

        # Load satellite analyses indexed by property_id
        sat_result = await self.db.execute(
            select(SatelliteAnalysis).where(SatelliteAnalysis.organization_id == org_id)
        )
        sat_by_prop = {s.property_id: s for s in sat_result.scalars().all()}

        # Load difficulties indexed by property_id
        diff_result = await self.db.execute(
            select(PropertyDifficulty).where(PropertyDifficulty.organization_id == org_id)
        )
        diff_by_prop = {d.property_id: d for d in diff_result.scalars().all()}

        count = 0
        for bow in bows:
            satellite = sat_by_prop.get(bow.property_id)
            difficulty = diff_by_prop.get(bow.property_id)
            await self.compute_bow_chemical_cost(
                org_id, bow, region_key=region_key,
                satellite_analysis=satellite, difficulty=difficulty,
            )
            count += 1

        logger.info(f"Recomputed chemical costs for {count} BOWs in org {org_id}")
        return count
