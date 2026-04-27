"""Equipment CRUD + normalization."""

import uuid
import logging
from datetime import date, datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from sqlalchemy.orm import selectinload
from src.models.equipment_item import EquipmentItem
from src.models.water_feature import WaterFeature
from src.services.parts.equipment_normalizer import EquipmentNormalizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/equipment", tags=["equipment"])


# --- Schemas ---

class EquipmentItemCreate(BaseModel):
    equipment_type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    part_number: Optional[str] = None
    system_group: Optional[str] = None
    serial_number: Optional[str] = None
    horsepower: Optional[float] = None
    notes: Optional[str] = None
    catalog_equipment_id: Optional[str] = None
    install_date: Optional[date] = None


class EquipmentItemUpdate(BaseModel):
    equipment_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    part_number: Optional[str] = None
    system_group: Optional[str] = None
    serial_number: Optional[str] = None
    horsepower: Optional[float] = None
    notes: Optional[str] = None
    catalog_equipment_id: Optional[str] = None
    install_date: Optional[date] = None


class EquipmentItemResponse(BaseModel):
    id: str
    water_feature_id: str
    equipment_type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    part_number: Optional[str] = None
    system_group: Optional[str] = None
    serial_number: Optional[str] = None
    normalized_name: Optional[str] = None
    horsepower: Optional[float] = None
    notes: Optional[str] = None
    is_active: bool = True
    catalog_equipment_id: Optional[str] = None
    catalog_canonical_name: Optional[str] = None
    install_date: Optional[date] = None
    source_inspection_id: Optional[str] = None
    source_slot: Optional[str] = None

    model_config = {"from_attributes": True}


# --- CRUD Endpoints ---

@router.get("/wf/{wf_id}", response_model=List[EquipmentItemResponse])
async def list_equipment(
    wf_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EquipmentItem)
        .options(selectinload(EquipmentItem.catalog_equipment))
        .where(
            EquipmentItem.organization_id == ctx.organization_id,
            EquipmentItem.water_feature_id == wf_id,
            EquipmentItem.is_active == True,
        )
        .order_by(EquipmentItem.system_group.nulls_last(), EquipmentItem.equipment_type)
    )
    from src.presenters.equipment_presenter import EquipmentPresenter
    items = result.scalars().all()
    return await EquipmentPresenter(db).many(list(items))


@router.post("/wf/{wf_id}", response_model=EquipmentItemResponse, status_code=201)
async def create_equipment(
    wf_id: str,
    body: EquipmentItemCreate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify WF belongs to org
    wf = await db.execute(
        select(WaterFeature).where(
            WaterFeature.id == wf_id,
            WaterFeature.organization_id == ctx.organization_id,
        )
    )
    if not wf.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Water feature not found")

    display = f"{body.brand or ''} {body.model or ''}".strip() or None

    item = EquipmentItem(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        water_feature_id=wf_id,
        equipment_type=body.equipment_type,
        brand=body.brand or None,
        model=body.model or None,
        part_number=body.part_number or None,
        system_group=body.system_group or None,
        serial_number=body.serial_number or None,
        horsepower=body.horsepower,
        notes=body.notes or None,
        normalized_name=display,
        catalog_equipment_id=body.catalog_equipment_id,
        install_date=body.install_date,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return EquipmentItemResponse.model_validate(item)


@router.put("/{item_id}", response_model=EquipmentItemResponse)
async def update_equipment(
    item_id: str,
    body: EquipmentItemUpdate,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EquipmentItem).where(
            EquipmentItem.id == item_id,
            EquipmentItem.organization_id == ctx.organization_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Snapshot original values before mutation (for AgentLearningService corrections)
    pre = {
        "brand": item.brand, "model": item.model, "horsepower": item.horsepower,
        "equipment_type": item.equipment_type, "system_group": item.system_group,
        "catalog_equipment_id": item.catalog_equipment_id, "notes": item.notes,
    }
    was_inspection_sourced = item.source_inspection_id is not None

    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(item, k, v if v != "" else None)

    # Refresh normalized_name
    display = f"{item.brand or ''} {item.model or ''}".strip() or None
    item.normalized_name = display

    await db.commit()
    await db.refresh(item)

    # Log correction if this was an inspection-sourced item being edited
    if was_inspection_sourced:
        try:
            from src.services.agent_learning_service import (
                AGENT_EQUIPMENT_RESOLVER,
                AgentLearningService,
            )
            post = {
                "brand": item.brand, "model": item.model, "horsepower": item.horsepower,
                "equipment_type": item.equipment_type, "system_group": item.system_group,
                "catalog_equipment_id": item.catalog_equipment_id, "notes": item.notes,
            }
            if pre != post:
                learner = AgentLearningService(db)
                import json
                await learner.record_correction(
                    org_id=ctx.organization_id,
                    agent_type=AGENT_EQUIPMENT_RESOLVER,
                    correction_type="edit",
                    original_output=json.dumps(pre, default=str),
                    corrected_output=json.dumps(post, default=str),
                    input_context=f"slot={item.source_slot} inspection={item.source_inspection_id}",
                    category=item.equipment_type,
                    source_id=item.id,
                    source_type="equipment_item",
                )
                await db.commit()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(f"equipment_resolver edit correction logging failed: {e}")

    return EquipmentItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def delete_equipment(
    item_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EquipmentItem).where(
            EquipmentItem.id == item_id,
            EquipmentItem.organization_id == ctx.organization_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Equipment not found")

    was_inspection_sourced = item.source_inspection_id is not None
    pre_snapshot = {
        "brand": item.brand, "model": item.model,
        "equipment_type": item.equipment_type, "system_group": item.system_group,
        "source_slot": item.source_slot,
    }

    item.is_active = False
    await db.commit()

    if was_inspection_sourced:
        try:
            from src.services.agent_learning_service import (
                AGENT_EQUIPMENT_RESOLVER,
                AgentLearningService,
            )
            import json
            learner = AgentLearningService(db)
            await learner.record_correction(
                org_id=ctx.organization_id,
                agent_type=AGENT_EQUIPMENT_RESOLVER,
                correction_type="rejection",
                original_output=json.dumps(pre_snapshot, default=str),
                input_context=f"slot={item.source_slot} inspection={item.source_inspection_id}",
                category=item.equipment_type,
                source_id=item.id,
                source_type="equipment_item",
            )
            await db.commit()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(f"equipment_resolver delete correction logging failed: {e}")


@router.post("/wf/{wf_id}/copy-from/{source_wf_id}", response_model=List[EquipmentItemResponse])
async def copy_equipment(
    wf_id: str,
    source_wf_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Copy all active equipment from source WF to target WF."""
    org_id = ctx.organization_id

    # Verify both WFs belong to org
    for fid in [wf_id, source_wf_id]:
        wf = await db.execute(
            select(WaterFeature).where(WaterFeature.id == fid, WaterFeature.organization_id == org_id)
        )
        if not wf.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Water feature {fid} not found")

    # Get source equipment
    source_result = await db.execute(
        select(EquipmentItem).where(
            EquipmentItem.organization_id == org_id,
            EquipmentItem.water_feature_id == source_wf_id,
            EquipmentItem.is_active == True,
        )
    )
    source_items = source_result.scalars().all()

    # Soft-delete existing equipment on target
    existing = await db.execute(
        select(EquipmentItem).where(
            EquipmentItem.organization_id == org_id,
            EquipmentItem.water_feature_id == wf_id,
            EquipmentItem.is_active == True,
        )
    )
    for item in existing.scalars().all():
        item.is_active = False

    # Copy
    created = []
    for src in source_items:
        item = EquipmentItem(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            water_feature_id=wf_id,
            equipment_type=src.equipment_type,
            brand=src.brand,
            model=src.model,
            part_number=src.part_number,
            system_group=src.system_group,
            serial_number=None,
            horsepower=src.horsepower,
            notes=src.notes,
            normalized_name=src.normalized_name,
        )
        db.add(item)
        created.append(item)

    await db.commit()
    for item in created:
        await db.refresh(item)
    return [EquipmentItemResponse.model_validate(e) for e in created]


# --- Normalization Endpoints (existing) ---

@router.get("/models")
async def get_equipment_models(
    type: str = Query(..., description="Equipment type"),
    q: str = Query("", description="Search query"),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    normalizer = EquipmentNormalizer(db)
    models = await normalizer.get_known_models(ctx.organization_id, type, q)
    return models


@router.post("/normalize")
async def normalize_equipment(
    body: dict,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    raw_text = (body.get("raw_text") or "").strip()
    equipment_type = (body.get("equipment_type") or "equipment").strip()

    if not raw_text:
        return EquipmentNormalizer._empty_result()

    normalizer = EquipmentNormalizer(db)
    result = await normalizer.normalize(raw_text, equipment_type)
    matches = await normalizer.find_matching_models(result, ctx.organization_id)
    result["existing_matches"] = matches
    return result
