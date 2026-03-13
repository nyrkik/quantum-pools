"""Pool measurement endpoints — photo upload, Claude Vision analysis, apply to property."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.schemas.measurement import MeasurementResponse, MeasurementApplyResponse
from src.services.pool_measurement_service import PoolMeasurementService
from src.services.upload_service import save_file

router = APIRouter(prefix="/measurements", tags=["measurements"])


@router.post("/properties/{property_id}/upload", response_model=MeasurementResponse)
async def upload_photos(
    property_id: str,
    scale_reference: str = Form("yardstick"),
    body_of_water_id: str = Form(default=""),
    overview_photos: list[UploadFile] = File(...),
    depth_photos: list[UploadFile] = File(default=[]),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload pool photos for measurement. At least one overview photo required."""
    if not overview_photos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one overview photo is required")

    photo_paths = []
    for f in overview_photos:
        path = await save_file(f, f"measurements/{property_id}")
        photo_paths.append({"filename": f.filename, "path": path, "type": "overview"})
    for f in depth_photos:
        path = await save_file(f, f"measurements/{property_id}")
        photo_paths.append({"filename": f.filename, "path": path, "type": "depth"})

    svc = PoolMeasurementService(db)
    try:
        measurement = await svc.upload_photos(
            ctx.organization_id, property_id, photo_paths, scale_reference, ctx.user.id,
            body_of_water_id=body_of_water_id or None,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MeasurementResponse.model_validate(measurement)


@router.post("/{measurement_id}/analyze", response_model=MeasurementResponse)
async def analyze_measurement(
    measurement_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger Claude Vision analysis on uploaded photos."""
    svc = PoolMeasurementService(db)
    try:
        measurement = await svc.analyze(ctx.organization_id, measurement_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MeasurementResponse.model_validate(measurement)


@router.post("/{measurement_id}/apply", response_model=MeasurementApplyResponse)
async def apply_measurement(
    measurement_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Write measurement results to the property record."""
    svc = PoolMeasurementService(db)
    try:
        measurement, prop = await svc.apply_to_property(ctx.organization_id, measurement_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MeasurementApplyResponse(
        measurement_id=measurement.id,
        property_id=prop.id,
        pool_length_ft=prop.pool_length_ft,
        pool_width_ft=prop.pool_width_ft,
        pool_depth_shallow=prop.pool_depth_shallow,
        pool_depth_deep=prop.pool_depth_deep,
        pool_depth_avg=prop.pool_depth_avg,
        pool_sqft=prop.pool_sqft,
        pool_gallons=prop.pool_gallons,
        pool_shape=prop.pool_shape,
        pool_volume_method=prop.pool_volume_method,
    )


@router.get("/properties/{property_id}", response_model=list[MeasurementResponse])
async def list_measurements(
    property_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all measurements for a property."""
    svc = PoolMeasurementService(db)
    measurements = await svc.list_for_property(ctx.organization_id, property_id)
    return [MeasurementResponse.model_validate(m) for m in measurements]


@router.get("/{measurement_id}", response_model=MeasurementResponse)
async def get_measurement(
    measurement_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single measurement."""
    svc = PoolMeasurementService(db)
    measurement = await svc.get_measurement(ctx.organization_id, measurement_id)
    if not measurement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Measurement not found")
    return MeasurementResponse.model_validate(measurement)
