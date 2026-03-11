"""Bather load calculation service — jurisdiction-aware with estimation chain."""

import math
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.models.bather_load_jurisdiction import BatherLoadJurisdiction, JurisdictionMethod
from src.models.property_jurisdiction import PropertyJurisdiction
from src.models.property import Property
from src.schemas.profitability import BatherLoadResult
from src.core.exceptions import NotFoundError


class BatherLoadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_jurisdictions(self) -> list[BatherLoadJurisdiction]:
        result = await self.db.execute(
            select(BatherLoadJurisdiction).order_by(BatherLoadJurisdiction.name)
        )
        return list(result.scalars().all())

    async def get_jurisdiction(self, jurisdiction_id: str) -> BatherLoadJurisdiction:
        result = await self.db.execute(
            select(BatherLoadJurisdiction).where(BatherLoadJurisdiction.id == jurisdiction_id)
        )
        j = result.scalar_one_or_none()
        if not j:
            raise NotFoundError("Jurisdiction not found")
        return j

    async def get_default_jurisdiction(self) -> BatherLoadJurisdiction:
        """Get California as default."""
        result = await self.db.execute(
            select(BatherLoadJurisdiction).where(
                BatherLoadJurisdiction.method_key == JurisdictionMethod.california
            )
        )
        j = result.scalar_one_or_none()
        if not j:
            raise NotFoundError("Default jurisdiction (California) not found. Run seed.")
        return j

    async def get_property_jurisdiction(
        self, org_id: str, property_id: str
    ) -> Optional[BatherLoadJurisdiction]:
        result = await self.db.execute(
            select(PropertyJurisdiction)
            .where(
                PropertyJurisdiction.property_id == property_id,
                PropertyJurisdiction.organization_id == org_id,
            )
        )
        pj = result.scalar_one_or_none()
        if pj:
            return await self.get_jurisdiction(pj.jurisdiction_id)
        return None

    async def assign_jurisdiction(
        self, org_id: str, property_id: str, jurisdiction_id: str
    ) -> None:
        await self.get_jurisdiction(jurisdiction_id)
        result = await self.db.execute(
            select(PropertyJurisdiction).where(
                PropertyJurisdiction.property_id == property_id,
                PropertyJurisdiction.organization_id == org_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.jurisdiction_id = jurisdiction_id
        else:
            import uuid
            self.db.add(PropertyJurisdiction(
                id=str(uuid.uuid4()),
                property_id=property_id,
                jurisdiction_id=jurisdiction_id,
                organization_id=org_id,
            ))
        await self.db.flush()

    async def bulk_assign_jurisdiction(
        self, org_id: str, jurisdiction_id: str,
        city: Optional[str] = None, zip_code: Optional[str] = None, state: Optional[str] = None,
    ) -> int:
        await self.get_jurisdiction(jurisdiction_id)
        query = select(Property).where(
            Property.organization_id == org_id,
            Property.is_active == True,
        )
        if city:
            query = query.where(Property.city.ilike(city))
        if zip_code:
            query = query.where(Property.zip_code == zip_code)
        if state:
            query = query.where(Property.state.ilike(state))

        result = await self.db.execute(query)
        properties = list(result.scalars().all())
        count = 0
        for prop in properties:
            await self.assign_jurisdiction(org_id, prop.id, jurisdiction_id)
            count += 1
        await self.db.flush()
        return count

    def calculate(
        self,
        jurisdiction: BatherLoadJurisdiction,
        pool_sqft: Optional[float] = None,
        pool_gallons: Optional[int] = None,
        shallow_sqft: Optional[float] = None,
        deep_sqft: Optional[float] = None,
        has_deep_end: bool = False,
        spa_sqft: Optional[float] = None,
        diving_board_count: int = 0,
        pump_flow_gpm: Optional[float] = None,
        is_indoor: bool = False,
    ) -> BatherLoadResult:
        estimated_fields: list[str] = []

        # Estimation chain: resolve pool_sqft
        if pool_sqft is None and pool_gallons:
            avg_depth = 5.5 if has_deep_end else 4.0
            pool_sqft = pool_gallons / (avg_depth * 7.48)
            estimated_fields.append("pool_sqft")
        elif pool_sqft is None:
            pool_sqft = 0.0
            estimated_fields.append("pool_sqft")

        # Estimation chain: resolve shallow/deep split
        if shallow_sqft is None or deep_sqft is None:
            if has_deep_end:
                shallow_sqft = pool_sqft * 0.6
                deep_sqft = pool_sqft * 0.4
            else:
                shallow_sqft = pool_sqft
                deep_sqft = 0.0
            estimated_fields.append("shallow_deep_split")

        # Estimation chain: resolve flow rate
        if pump_flow_gpm is None and pool_gallons:
            pump_flow_gpm = pool_gallons / 360  # 6-hour commercial turnover
            estimated_fields.append("pump_flow_gpm")

        # Pool bathers
        if jurisdiction.depth_based and has_deep_end:
            pool_bathers = math.floor(
                shallow_sqft / jurisdiction.shallow_sqft_per_bather
                + deep_sqft / jurisdiction.deep_sqft_per_bather
            )
        else:
            pool_bathers = math.floor(pool_sqft / jurisdiction.shallow_sqft_per_bather)

        # Spa bathers
        spa_bathers = math.floor((spa_sqft or 0) / jurisdiction.spa_sqft_per_bather) if spa_sqft else 0

        # Diving board bathers
        diving_bathers = math.floor(
            diving_board_count * jurisdiction.diving_sqft_per_board / jurisdiction.deep_sqft_per_bather
        ) if diving_board_count > 0 else 0

        # Deck bonus (ISPSC)
        deck_bonus_bathers = 0
        if jurisdiction.has_deck_bonus and jurisdiction.deck_sqft_per_bather:
            # Would need deck_sqft input — skip for now, user can add later
            pass

        total = pool_bathers + spa_bathers + diving_bathers + deck_bonus_bathers

        # Flow rate test (Florida) — lesser value wins
        flow_rate_bathers = None
        if jurisdiction.has_flow_rate_test and jurisdiction.flow_gpm_per_bather and pump_flow_gpm:
            flow_rate_bathers = math.floor(pump_flow_gpm / jurisdiction.flow_gpm_per_bather)
            total = min(total, flow_rate_bathers)

        # Indoor multiplier (MAHC)
        if jurisdiction.has_indoor_multiplier and is_indoor and jurisdiction.indoor_multiplier:
            total = math.floor(total * jurisdiction.indoor_multiplier)

        return BatherLoadResult(
            max_bathers=max(total, 0),
            pool_bathers=pool_bathers,
            spa_bathers=spa_bathers,
            diving_bathers=diving_bathers,
            deck_bonus_bathers=deck_bonus_bathers,
            flow_rate_bathers=flow_rate_bathers,
            jurisdiction_name=jurisdiction.name,
            method_key=jurisdiction.method_key.value,
            estimated_fields=estimated_fields,
            pool_sqft_used=pool_sqft,
            shallow_sqft_used=shallow_sqft,
            deep_sqft_used=deep_sqft,
        )
