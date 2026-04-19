"""Proposal creator: `equipment_item` entity_type.

Delegates to `EquipmentItemService.add_item()` — the canonical path
(added alongside this creator because no prior canonical service for
equipment_items existed).

This is the entity_type the Step 5 DeepBlue dogfood migration targets:
`add_equipment_to_pool` tool stages a proposal of this type.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.equipment_item_service import EquipmentItemService
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


class EquipmentItemProposalPayload(BaseModel):
    """Fields a proposal can commit to an equipment_item."""

    water_feature_id: str
    equipment_type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    part_number: Optional[str] = None
    normalized_name: Optional[str] = None
    horsepower: Optional[float] = None
    flow_rate_gpm: Optional[int] = None
    voltage: Optional[int] = None
    catalog_part_id: Optional[str] = None
    catalog_equipment_id: Optional[str] = None
    install_date: Optional[date] = None
    warranty_expires: Optional[date] = None
    expected_lifespan_years: Optional[int] = None
    system_group: Optional[str] = None
    notes: Optional[str] = None


@register("equipment_item", schema=EquipmentItemProposalPayload)
async def create_equipment_item_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    return await EquipmentItemService(db).add_item(
        org_id=org_id,
        actor=actor,
        water_feature_id=payload["water_feature_id"],
        equipment_type=payload["equipment_type"],
        brand=payload.get("brand"),
        model=payload.get("model"),
        serial_number=payload.get("serial_number"),
        part_number=payload.get("part_number"),
        normalized_name=payload.get("normalized_name"),
        horsepower=payload.get("horsepower"),
        flow_rate_gpm=payload.get("flow_rate_gpm"),
        voltage=payload.get("voltage"),
        catalog_part_id=payload.get("catalog_part_id"),
        catalog_equipment_id=payload.get("catalog_equipment_id"),
        install_date=payload.get("install_date"),
        warranty_expires=payload.get("warranty_expires"),
        expected_lifespan_years=payload.get("expected_lifespan_years"),
        system_group=payload.get("system_group"),
        notes=payload.get("notes"),
    )
