"""PropertyPresenter — single source of truth for Property + WaterFeature serialization.

Resolves:
- WaterFeature pool dimensions (source of truth, not Property legacy fields)
- Equipment from equipment_items table (not WF legacy strings)
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.presenters.base import Presenter
from src.presenters.equipment_presenter import EquipmentPresenter
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.models.equipment_item import EquipmentItem


class PropertyPresenter(Presenter):
    """Present Property data with resolved WF and equipment."""

    async def _load_equipment_for_wfs(self, wf_ids: list[str]) -> dict[str, list]:
        """Batch load equipment for multiple WFs in a single query."""
        if not wf_ids:
            return {}
        eq_result = await self.db.execute(
            select(EquipmentItem)
            .options(selectinload(EquipmentItem.catalog_equipment))
            .where(EquipmentItem.water_feature_id.in_(wf_ids), EquipmentItem.is_active == True)
        )
        items = eq_result.scalars().all()
        by_wf: dict[str, list] = {}
        for ei in items:
            by_wf.setdefault(ei.water_feature_id, []).append(ei)
        return by_wf

    async def one(self, prop: Property, water_features: list[WaterFeature] | None = None) -> dict:
        d = self._base(prop)
        wfs = water_features or []
        eq_map = await self._load_equipment_for_wfs([wf.id for wf in wfs])
        d["water_features"] = [self._wf_summary(wf, eq_map.get(wf.id, [])) for wf in wfs]
        return d

    async def many(self, properties: list[Property], wf_map: dict[str, list[WaterFeature]] | None = None) -> list[dict]:
        all_wfs = []
        if wf_map:
            for wfs in wf_map.values():
                all_wfs.extend(wfs)
        eq_map = await self._load_equipment_for_wfs([wf.id for wf in all_wfs])

        results = []
        for p in properties:
            d = self._base(p)
            wfs = wf_map.get(p.id, []) if wf_map else []
            d["water_features"] = [self._wf_summary(wf, eq_map.get(wf.id, [])) for wf in wfs]
            results.append(d)
        return results

    @staticmethod
    def _wf_summary(wf: WaterFeature, items: list) -> dict:
        """Full WF summary with pre-loaded equipment."""
        d = {
            "id": wf.id,
            "name": wf.name,
            "water_type": wf.water_type,
            "pool_type": wf.pool_type,
            "pool_gallons": wf.pool_gallons,
            "pool_sqft": wf.pool_sqft,
            "pool_surface": wf.pool_surface,
            "pool_length_ft": wf.pool_length_ft,
            "pool_width_ft": wf.pool_width_ft,
            "pool_depth_shallow": wf.pool_depth_shallow,
            "pool_depth_deep": wf.pool_depth_deep,
            "pool_shape": wf.pool_shape,
            "sanitizer_type": wf.sanitizer_type,
            "estimated_service_minutes": wf.estimated_service_minutes,
            "monthly_rate": wf.monthly_rate,
        }

        d["equipment"] = [EquipmentPresenter._serialize(ei) for ei in items]

        # Backward compat: populate legacy flat fields from equipment_items
        type_map = {}
        for ei in items:
            name = (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                    ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip())
            if name and ei.equipment_type not in type_map:
                type_map[ei.equipment_type] = name
        d["pump_type"] = type_map.get("pump")
        d["filter_type"] = type_map.get("filter")
        d["heater_type"] = type_map.get("heater")
        d["chlorinator_type"] = type_map.get("chlorinator")
        d["automation_system"] = type_map.get("automation")

        return d

    @staticmethod
    def _base(p: Property) -> dict:
        return {
            "id": p.id,
            "customer_id": p.customer_id,
            "name": p.name,
            "address": p.address,
            "city": p.city,
            "state": p.state,
            "zip_code": p.zip_code,
            "gate_code": p.gate_code,
            "access_instructions": p.access_instructions,
            "dog_on_property": p.dog_on_property,
            "monthly_rate": p.monthly_rate,
            "estimated_service_minutes": p.estimated_service_minutes,
            "is_locked_to_day": p.is_locked_to_day,
            "service_day_pattern": p.service_day_pattern,
            "notes": p.notes,
            "is_active": p.is_active,
        }
