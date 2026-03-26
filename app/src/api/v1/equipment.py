"""Equipment normalization — autocomplete from known models, AI-powered text parsing."""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.services.parts.equipment_normalizer import EquipmentNormalizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/models")
async def get_equipment_models(
    type: str = Query(..., description="Equipment type: pump, filter, heater, chlorinator, automation"),
    q: str = Query("", description="Search query (min 3 chars for filtering)"),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Autocomplete from known normalized equipment models in the org."""
    normalizer = EquipmentNormalizer(db)
    models = await normalizer.get_known_models(ctx.organization_id, type, q)
    return models


@router.post("/normalize")
async def normalize_equipment(
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Normalize a raw equipment text string into structured fields.

    Body: {"raw_text": "Pentair Intelliflo VS-SVRS 3HP", "equipment_type": "pump"}
    """
    raw_text = (body.get("raw_text") or "").strip()
    equipment_type = (body.get("equipment_type") or "equipment").strip()

    if not raw_text:
        return EquipmentNormalizer._empty_result()

    normalizer = EquipmentNormalizer(db)
    result = await normalizer.normalize(raw_text, equipment_type)

    # Also find matching models in the org
    matches = await normalizer.find_matching_models(result, ctx.organization_id)
    result["existing_matches"] = matches

    return result
