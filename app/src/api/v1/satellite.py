"""Satellite analysis endpoints — per-BOW pool detection and vegetation analysis."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.schemas.satellite import (
    SatelliteAnalysisResponse,
    SatelliteImageResponse,
    SetPinRequest,
    AnalyzeRequest,
    CaptureImageRequest,
    PoolBowWithCoordsResponse,
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


@router.get("/pool-bows", response_model=list[PoolBowWithCoordsResponse])
async def get_pool_bows(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    return await svc.get_pool_bows_with_coords(ctx.organization_id)


@router.get("/bows/{bow_id}", response_model=SatelliteAnalysisResponse)
async def get_analysis(
    bow_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    analysis = await svc.get_analysis(ctx.organization_id, bow_id)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this pool")
    return SatelliteAnalysisResponse.model_validate(analysis)


@router.put("/bows/{bow_id}/pin", response_model=SatelliteAnalysisResponse)
async def set_pool_pin(
    bow_id: str,
    body: SetPinRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    try:
        analysis = await svc.set_pool_pin(ctx.organization_id, bow_id, body.pool_lat, body.pool_lng)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return SatelliteAnalysisResponse.model_validate(analysis)


@router.post("/bows/{bow_id}/analyze", response_model=SatelliteAnalysisResponse)
async def analyze_bow(
    bow_id: str,
    body: AnalyzeRequest | None = None,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    try:
        analysis = await svc.analyze_bow(
            ctx.organization_id, bow_id,
            force=body.force if body else False,
            pool_lat=body.pool_lat if body else None,
            pool_lng=body.pool_lng if body else None,
        )
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
        bow_ids=body.bow_ids,
        force=body.force_reanalyze,
    )
    return BulkAnalysisResponse(
        total=result["total"],
        analyzed=result["analyzed"],
        skipped=result["skipped"],
        failed=result["failed"],
        results=[SatelliteAnalysisResponse.model_validate(r) for r in result["results"]],
    )


def _image_to_response(img) -> SatelliteImageResponse:
    return SatelliteImageResponse(
        id=img.id,
        property_id=img.property_id,
        filename=img.filename,
        url=f"/uploads/satellite/{img.property_id}/{img.filename}",
        center_lat=img.center_lat,
        center_lng=img.center_lng,
        zoom=img.zoom,
        is_hero=img.is_hero,
        created_at=img.created_at,
    )


@router.get("/images/heroes", response_model=dict[str, SatelliteImageResponse])
async def get_hero_images(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all hero images keyed by property_id."""
    from sqlalchemy import select
    from src.models.satellite_image import SatelliteImage
    result = await db.execute(
        select(SatelliteImage).where(
            SatelliteImage.organization_id == ctx.organization_id,
            SatelliteImage.is_hero == True,
        )
    )
    heroes = result.scalars().all()
    return {img.property_id: _image_to_response(img) for img in heroes}


@router.get("/properties/{property_id}/images", response_model=list[SatelliteImageResponse])
async def list_images(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    images = await svc.list_images(ctx.organization_id, property_id)
    return [_image_to_response(img) for img in images]


@router.post("/properties/{property_id}/images/capture", response_model=SatelliteImageResponse)
async def capture_image(
    property_id: str,
    body: CaptureImageRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    try:
        img = await svc.capture_image(
            ctx.organization_id, property_id,
            body.center_lat, body.center_lng, body.zoom,
        )
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _image_to_response(img)


@router.put("/properties/{property_id}/images/{image_id}/hero", response_model=SatelliteImageResponse)
async def set_hero_image(
    property_id: str,
    image_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    try:
        img = await svc.set_hero_image(ctx.organization_id, property_id, image_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _image_to_response(img)


@router.delete("/properties/{property_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    property_id: str,
    image_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    svc = SatelliteService(db)
    try:
        await svc.delete_image(ctx.organization_id, property_id, image_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
