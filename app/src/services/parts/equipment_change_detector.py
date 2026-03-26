"""Equipment Change Detector — queues parts discovery when equipment fields change."""

import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Equipment fields on WaterFeature to monitor
_EQUIPMENT_FIELDS = {"pump_type", "filter_type", "heater_type", "chlorinator_type", "automation_system"}

_FIELD_TO_TYPE = {
    "pump_type": "pump",
    "filter_type": "filter",
    "heater_type": "heater",
    "chlorinator_type": "chlorinator",
    "automation_system": "automation",
}

_MIN_MODEL_LEN = 5


def detect_equipment_changes(old_values: dict, new_values: dict) -> list[dict]:
    """Compare old and new equipment field values, return list of changed models.

    Args:
        old_values: dict of field_name -> old_value (before update)
        new_values: dict of field_name -> new_value (after update)

    Returns:
        List of {"model": str, "type": str} for changed equipment that needs discovery.
    """
    changes = []
    for field in _EQUIPMENT_FIELDS:
        old_val = (old_values.get(field) or "").strip()
        new_val = (new_values.get(field) or "").strip()
        if new_val and new_val != old_val and len(new_val) >= _MIN_MODEL_LEN:
            changes.append({
                "model": new_val,
                "type": _FIELD_TO_TYPE.get(field, "equipment"),
            })
    return changes


async def queue_parts_discovery(db: AsyncSession, changes: list[dict]) -> None:
    """Fire-and-forget parts discovery for changed equipment models.

    Creates a background task for each changed model. Uses a fresh DB session
    to avoid interfering with the caller's transaction.
    """
    if not changes:
        return

    from src.core.database import get_db_context

    async def _discover(model: str, eq_type: str):
        try:
            async with get_db_context() as session:
                from src.services.parts.equipment_parts_agent import EquipmentPartsAgent
                agent = EquipmentPartsAgent(session)
                parts = await agent.discover_parts_for_model(model, eq_type)
                logger.info(f"Background discovery for {model}: {len(parts)} parts")
        except Exception as e:
            logger.error(f"Background discovery failed for {model}: {e}")

    for change in changes:
        asyncio.create_task(_discover(change["model"], change["type"]))
        logger.info(f"Queued parts discovery for {change['type']}: {change['model']}")
