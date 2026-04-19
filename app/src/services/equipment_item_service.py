"""EquipmentItemService — canonical CRUD for equipment_items.

Minimal service added for Phase 2 so the proposal creator has a
canonical path to delegate to (rather than constructing EquipmentItem
rows directly — which would violate the 'single source of truth'
discipline that justifies every other canonical service).

Scope is intentionally small: just `add_item` for now. Future edits /
deletes can grow this when the need appears; we don't build
speculative CRUD.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.equipment_item import EquipmentItem
from src.models.water_feature import WaterFeature
from src.services.events.actor_factory import actor_system
from src.services.events.platform_event_service import Actor, PlatformEventService


class EquipmentItemService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_item(
        self,
        *,
        org_id: str,
        water_feature_id: str,
        equipment_type: str,
        actor: Optional[Actor] = None,
        brand: Optional[str] = None,
        model: Optional[str] = None,
        serial_number: Optional[str] = None,
        part_number: Optional[str] = None,
        normalized_name: Optional[str] = None,
        horsepower: Optional[float] = None,
        flow_rate_gpm: Optional[int] = None,
        voltage: Optional[int] = None,
        catalog_part_id: Optional[str] = None,
        catalog_equipment_id: Optional[str] = None,
        install_date: Optional[date] = None,
        warranty_expires: Optional[date] = None,
        expected_lifespan_years: Optional[int] = None,
        system_group: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> EquipmentItem:
        """Add an equipment item to a water feature. Emits
        `equipment_item.added` event.

        Validates the water feature belongs to the provided org — cross-org
        leaks would be a security bug even from an internal caller.
        """
        wf = (await self.db.execute(
            select(WaterFeature).where(
                WaterFeature.id == water_feature_id,
                WaterFeature.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if wf is None:
            raise NotFoundError(
                f"WaterFeature {water_feature_id} not found in org {org_id}"
            )

        item = EquipmentItem(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            water_feature_id=water_feature_id,
            equipment_type=equipment_type,
            brand=brand,
            model=model,
            serial_number=serial_number,
            part_number=part_number,
            normalized_name=normalized_name,
            horsepower=horsepower,
            flow_rate_gpm=flow_rate_gpm,
            voltage=voltage,
            catalog_part_id=catalog_part_id,
            catalog_equipment_id=catalog_equipment_id,
            install_date=install_date,
            warranty_expires=warranty_expires,
            expected_lifespan_years=expected_lifespan_years,
            system_group=system_group,
            notes=notes,
        )
        self.db.add(item)
        await self.db.flush()

        refs = {
            "equipment_item_id": item.id,
            "water_feature_id": water_feature_id,
            "property_id": wf.property_id,
        }
        source = "proposal_accepted" if actor and actor.actor_type == "user" else (
            "agent" if actor and actor.actor_type == "agent" else "system"
        )
        await PlatformEventService.emit(
            db=self.db,
            event_type="equipment_item.added",
            level=("user_action" if actor and actor.actor_type == "user"
                   else "agent_action" if actor and actor.actor_type == "agent"
                   else "system_action"),
            actor=actor or actor_system(),
            organization_id=org_id,
            entity_refs=refs,
            payload={
                "catalog_equipment_id": catalog_equipment_id,
                "source": source,
            },
        )
        return item
