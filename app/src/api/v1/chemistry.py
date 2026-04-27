"""Chemistry API — LSI + dosing calculator endpoints.

Phase 3d.2. Two endpoints, both under `/v1/chemistry/water-features/{bow_id}/`:

- GET /lsi      — current LSI from the most recent ChemicalReading on
                  the BOW. 404 if no readings exist.
- POST /dosing  — stateless calculator. Body is a partial reading set;
                  response is the dosing-engine's recommendations plus
                  an LSI value if enough fields were supplied.

Both gated by `chemicals.view`. POST is a calculator, not a write —
intentionally not gated by `chemicals.create`.

The dosing engine + LSI calculator are pure functions (no DB, no AI).
This router is a thin HTTP shell.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import OrgUserContext, require_permissions
from src.core.database import get_db
from src.models.chemical_reading import ChemicalReading
from src.models.water_feature import WaterFeature
from src.services.dosing_engine import calculate_dosing, calculate_lsi


router = APIRouter(prefix="/chemistry", tags=["chemistry"])


class DosingRequest(BaseModel):
    """Stateless calculator inputs. All fields optional — the engine
    skips any parameter the caller didn't supply."""
    ph: float | None = None
    free_chlorine: float | None = None
    combined_chlorine: float | None = None
    alkalinity: int | None = None
    calcium_hardness: int | None = None
    cyanuric_acid: int | None = None
    phosphates: int | None = None
    pool_gallons: int


async def _load_bow_scoped(
    db: AsyncSession, bow_id: str, ctx: OrgUserContext,
) -> WaterFeature:
    wf = await db.get(WaterFeature, bow_id)
    if wf is None or wf.organization_id != ctx.organization_id:
        # 404 either way — don't leak existence cross-org.
        raise HTTPException(404, "water feature not found")
    return wf


@router.get("/water-features/{bow_id}/lsi")
async def get_lsi(
    bow_id: str,
    ctx: OrgUserContext = Depends(require_permissions("chemicals.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """LSI from the most recent ChemicalReading for this BOW.

    Returns the value, classification, and the inputs used (including
    the hardcoded 75°F temp constant) so the UI can label the
    assumption transparently.

    404 when no readings exist OR when the latest reading is missing
    any of the required fields (pH + Ca + alk).
    """
    await _load_bow_scoped(db, bow_id, ctx)

    reading = (await db.execute(
        select(ChemicalReading)
        .where(ChemicalReading.water_feature_id == bow_id)
        .order_by(desc(ChemicalReading.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if reading is None:
        raise HTTPException(404, "no chemical readings exist for this water feature")

    if (
        reading.ph is None
        or reading.calcium_hardness is None
        or reading.alkalinity is None
    ):
        raise HTTPException(
            422,
            "latest reading is missing pH, calcium hardness, or alkalinity — "
            "all three are required for LSI",
        )

    try:
        result = calculate_lsi(
            ph=reading.ph,
            calcium_hardness=reading.calcium_hardness,
            alkalinity=reading.alkalinity,
            cyanuric_acid=reading.cyanuric_acid,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    return {
        **result,
        "reading_id": reading.id,
        "taken_at": reading.created_at.isoformat() if reading.created_at else None,
    }


@router.post("/water-features/{bow_id}/dosing")
async def calculate_dosing_endpoint(
    bow_id: str,
    body: DosingRequest,
    ctx: OrgUserContext = Depends(require_permissions("chemicals.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Stateless dosing calculator. Caller supplies whatever readings
    they have (typically as the tech enters values during a visit) and
    gets recommendations back. No DB write — the visit save flow is
    the canonical store."""
    await _load_bow_scoped(db, bow_id, ctx)

    if body.pool_gallons <= 0:
        raise HTTPException(422, "pool_gallons must be > 0")

    dosing = calculate_dosing(
        pool_gallons=body.pool_gallons,
        ph=body.ph,
        free_chlorine=body.free_chlorine,
        combined_chlorine=body.combined_chlorine,
        alkalinity=body.alkalinity,
        calcium_hardness=body.calcium_hardness,
        cyanuric_acid=body.cyanuric_acid,
        phosphates=body.phosphates,
    )

    # Attach an LSI value if the caller supplied enough fields.
    lsi_payload: Optional[dict] = None
    if (
        body.ph is not None
        and body.calcium_hardness is not None
        and body.alkalinity is not None
    ):
        try:
            lsi_payload = calculate_lsi(
                ph=body.ph,
                calcium_hardness=body.calcium_hardness,
                alkalinity=body.alkalinity,
                cyanuric_acid=body.cyanuric_acid,
            )
        except ValueError:
            # Degenerate input — drop the LSI silently rather than
            # crashing the whole dosing call.
            lsi_payload = None

    return {**dosing, "lsi": lsi_payload}
