"""Dimension estimate endpoints — perimeter measurement, estimate tracking, discrepancy analysis."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.schemas.dimension import (
    DimensionEstimateResponse,
    PerimeterMeasurementRequest,
    DimensionComparisonResponse,
)
from src.services.dimension_service import DimensionService

router = APIRouter(prefix="/dimensions", tags=["dimensions"])


@router.post("/bows/{bow_id}/perimeter", response_model=DimensionEstimateResponse)
async def add_perimeter_measurement(
    bow_id: str,
    body: PerimeterMeasurementRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a perimeter-based dimension estimate. Auto-calculates sqft from perimeter + shape."""
    svc = DimensionService(db)
    estimate = await svc.add_perimeter_estimate(
        org_id=ctx.organization_id,
        bow_id=bow_id,
        perimeter_ft=body.perimeter_ft,
        pool_shape=body.pool_shape,
        user_id=ctx.user.id,
    )
    return DimensionEstimateResponse.model_validate(estimate)


@router.get("/bows/{bow_id}/estimates", response_model=list[DimensionEstimateResponse])
async def list_estimates(
    bow_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all dimension estimates for a body of water."""
    svc = DimensionService(db)
    estimates = await svc.get_estimates(ctx.organization_id, bow_id)
    return [DimensionEstimateResponse.model_validate(e) for e in estimates]


@router.get("/bows/{bow_id}/comparison", response_model=DimensionComparisonResponse)
async def get_comparison(
    bow_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dimension comparison with discrepancy analysis."""
    svc = DimensionService(db)
    data = await svc.get_comparison(ctx.organization_id, bow_id)
    return DimensionComparisonResponse(
        estimates=[DimensionEstimateResponse.model_validate(e) for e in data["estimates"]],
        active_source=data["active_source"],
        active_sqft=data["active_sqft"],
        discrepancy_pct=data["discrepancy_pct"],
        discrepancy_level=data["discrepancy_level"],
    )


@router.delete("/{estimate_id}", status_code=204)
async def delete_estimate(
    estimate_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a dimension estimate."""
    svc = DimensionService(db)
    await svc.delete_estimate(ctx.organization_id, estimate_id)
