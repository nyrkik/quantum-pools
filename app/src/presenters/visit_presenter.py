"""VisitPresenter — single source of truth for Visit context serialization.

Resolves:
- WaterFeature equipment from equipment_items table
- Customer name from Customer table
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.presenters.base import Presenter
from src.presenters.equipment_presenter import EquipmentPresenter
from src.models.equipment_item import EquipmentItem


class VisitPresenter(Presenter):
    """Present visit-related WF data with equipment from source of truth."""

    async def water_features(self, wfs: list) -> list[dict]:
        """Build WF context with equipment from equipment_items table."""
        results = []
        for wf in wfs:
            d = {
                "id": wf.id,
                "name": wf.name,
                "water_type": wf.water_type,
                "pool_gallons": wf.pool_gallons,
                "pool_type": wf.pool_type,
            }
            eq_result = await self.db.execute(
                select(EquipmentItem)
                .options(selectinload(EquipmentItem.catalog_equipment))
                .where(EquipmentItem.water_feature_id == wf.id, EquipmentItem.is_active == True)
            )
            items = eq_result.scalars().all()
            d["equipment"] = [
                {"type": ei.equipment_type, "name": EquipmentPresenter._serialize(ei).get("catalog_canonical_name") or EquipmentPresenter._serialize(ei).get("normalized_name", "")}
                for ei in items
            ]
            results.append(d)
        return results
