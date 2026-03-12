"""Satellite analysis endpoints — pool detection and vegetation analysis."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.schemas.satellite import (
    SatelliteAnalysisResponse,
    BulkAnalysisRequest,
    BulkAnalysisResponse,
)
from src.services.satellite_service import SatelliteService

router = APIRouter(prefix="/satellite", tags=["satellite"])


@router.get("/all", response_model=list[SatelliteAnalysisResponse])
async def get_all_analyses(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from src.models.satellite_analysis import SatelliteAnalysis
    result = await db.execute(
        select(SatelliteAnalysis).where(
            SatelliteAnalysis.organization_id == ctx.organization_id
        )
    )
    analyses = result.scalars().all()
    return [SatelliteAnalysisResponse.model_validate(a) for a in analyses]


@router.get("/properties/{property_id}", response_model=SatelliteAnalysisResponse)
async def get_analysis(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    analysis = await svc.get_analysis(ctx.organization_id, property_id)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this property")
    return SatelliteAnalysisResponse.model_validate(analysis)


@router.post("/properties/{property_id}/analyze", response_model=SatelliteAnalysisResponse)
async def analyze_property(
    property_id: str,
    force: bool = False,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    try:
        analysis = await svc.analyze_property(ctx.organization_id, property_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return SatelliteAnalysisResponse.model_validate(analysis)


@router.post("/bulk-analyze", response_model=BulkAnalysisResponse)
async def bulk_analyze(
    body: BulkAnalysisRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    result = await svc.bulk_analyze(
        ctx.organization_id,
        property_ids=body.property_ids,
        force=body.force_reanalyze,
    )
    return BulkAnalysisResponse(
        total=result["total"],
        analyzed=result["analyzed"],
        skipped=result["skipped"],
        failed=result["failed"],
        results=[SatelliteAnalysisResponse.model_validate(r) for r in result["results"]],
    )
