"""EquipmentPresenter — single source of truth for EquipmentItem serialization.

Resolves:
- catalog_equipment_id → canonical_name, image_url from EquipmentCatalog
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.presenters.base import Presenter
from src.models.equipment_item import EquipmentItem


class EquipmentPresenter(Presenter):
    """Present EquipmentItem data with resolved catalog FK."""

    async def many(self, items: list[EquipmentItem]) -> list[dict]:
        return [self._serialize(ei) for ei in items]

    async def one(self, item: EquipmentItem) -> dict:
        return self._serialize(item)

    @staticmethod
    def _serialize(ei: EquipmentItem) -> dict:
        catalog = ei.catalog_equipment if hasattr(ei, "catalog_equipment") and ei.catalog_equipment else None
        return {
            "id": ei.id,
            "water_feature_id": ei.water_feature_id,
            "equipment_type": ei.equipment_type,
            "brand": ei.brand,
            "model": ei.model,
            "part_number": ei.part_number,
            "system_group": ei.system_group,
            "serial_number": ei.serial_number,
            "normalized_name": ei.normalized_name,
            "horsepower": ei.horsepower,
            "notes": ei.notes,
            "is_active": ei.is_active,
            "catalog_equipment_id": ei.catalog_equipment_id,
            "catalog_canonical_name": catalog.canonical_name if catalog else None,
        }
