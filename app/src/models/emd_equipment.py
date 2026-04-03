"""Backward-compat alias — EMDEquipment was renamed to InspectionEquipment."""
from src.models.inspection_equipment import InspectionEquipment as EMDEquipment

__all__ = ["EMDEquipment"]
