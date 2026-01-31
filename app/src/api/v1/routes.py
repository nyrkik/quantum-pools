"""Route endpoints — optimization, CRUD, OSRM polylines."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.models.property import Property
from src.models.customer import Customer
from src.models.tech import Tech
from src.schemas.route import (
    RouteOptimizationRequest,
    RouteOptimizationResponse,
    RouteResponse,
    RouteStopResponse,
    StopReorderRequest,
    StopReassignRequest,
)
from src.services.route_service import RouteService
from src.services.route_optimization_service import optimize_routes
from src.services import osrm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routes", tags=["routes"])


def _route_to_response(route) -> RouteResponse:
    stops = []
    for s in sorted(route.stops, key=lambda x: x.sequence):
        prop = s.property
        cust = prop.customer if prop else None
        stops.append(RouteStopResponse(
            id=s.id,
            property_id=s.property_id,
            sequence=s.sequence,
            estimated_service_duration=s.estimated_service_duration,
            estimated_drive_time_from_previous=s.estimated_drive_time_from_previous,
            estimated_distance_from_previous=s.estimated_distance_from_previous,
            property_address=prop.full_address if prop else None,
            customer_name=cust.full_name if cust else None,
            lat=prop.lat if prop else None,
            lng=prop.lng if prop else None,
        ))
    return RouteResponse(
        id=route.id,
        tech_id=route.tech_id,
        tech_name=route.tech.full_name if route.tech else None,
        tech_color=route.tech.color if route.tech else None,
        service_day=route.service_day,
        total_duration_minutes=route.total_duration_minutes,
        total_distance_miles=route.total_distance_miles,
        total_stops=route.total_stops,
        optimization_algorithm=route.optimization_algorithm,
        stops=stops,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


@router.post("/optimize", response_model=RouteOptimizationResponse)
async def optimize(
    body: RouteOptimizationRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Run VRP optimization. Returns results without persisting."""
    # Load techs
    tech_query = select(Tech).where(Tech.organization_id == ctx.organization_id, Tech.is_active == True)
    if body.tech_ids:
        tech_query = tech_query.where(Tech.id.in_(body.tech_ids))
    tech_result = await db.execute(tech_query)
    techs = list(tech_result.scalars().all())

    # Load properties with customers
    prop_query = (
        select(Property)
        .options(joinedload(Property.customer))
        .where(Property.organization_id == ctx.organization_id, Property.is_active == True)
        .where(Property.lat.isnot(None), Property.lng.isnot(None))
    )
    if body.service_day and body.mode != "cross_day":
        prop_query = prop_query.where(Property.service_day_pattern == body.service_day)

    prop_result = await db.execute(prop_query)
    properties = list(prop_result.unique().scalars().all())

    # Convert to dicts for optimizer
    prop_dicts = []
    for p in properties:
        cust = p.customer
        prop_dicts.append({
            "id": p.id,
            "lat": p.lat,
            "lng": p.lng,
            "estimated_service_minutes": p.estimated_service_minutes,
            "difficulty_rating": cust.difficulty_rating if cust else 1,
            "customer_name": cust.full_name if cust else "",
            "address": p.full_address,
            "service_day_pattern": p.service_day_pattern or "",
            "is_locked_to_day": p.is_locked_to_day,
        })

    tech_dicts = []
    for t in techs:
        tech_dicts.append({
            "id": t.id,
            "first_name": t.first_name,
            "last_name": t.last_name,
            "color": t.color,
            "start_lat": t.start_lat,
            "start_lng": t.start_lng,
            "end_lat": t.end_lat,
            "end_lng": t.end_lng,
            "max_stops_per_day": t.max_stops_per_day,
            "efficiency_factor": t.efficiency_factor,
            "working_days": t.working_days,
        })

    result = optimize_routes(
        properties=prop_dicts,
        techs=tech_dicts,
        mode=body.mode,
        service_day=body.service_day,
        speed=body.speed,
        avg_speed_mph=body.avg_speed_mph,
    )

    return RouteOptimizationResponse(**result)


@router.post("/save", response_model=list[RouteResponse])
async def save_routes(
    routes_data: list[dict],
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist optimization results."""
    svc = RouteService(db)
    routes = await svc.save_routes(ctx.organization_id, routes_data)
    # Reload with relationships
    loaded = []
    for r in routes:
        day_routes = await svc.get_routes_for_day(ctx.organization_id, r.service_day, r.tech_id)
        loaded.extend(day_routes)
    return [_route_to_response(r) for r in loaded]


@router.get("/day/{service_day}", response_model=list[RouteResponse])
async def get_day_routes(
    service_day: str,
    tech_id: Optional[str] = Query(None),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RouteService(db)
    routes = await svc.get_routes_for_day(ctx.organization_id, service_day, tech_id)
    return [_route_to_response(r) for r in routes]


@router.get("/week", response_model=list[RouteResponse])
async def get_week_routes(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RouteService(db)
    routes = await svc.get_routes_for_week(ctx.organization_id)
    return [_route_to_response(r) for r in routes]


@router.put("/stops/{stop_id}/reorder")
async def reorder_stop(
    stop_id: str,
    body: StopReorderRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RouteService(db)
    await svc.reorder_stop(ctx.organization_id, stop_id, body.new_sequence)
    return {"status": "ok"}


@router.post("/stops/{stop_id}/reassign")
async def reassign_stop(
    stop_id: str,
    body: StopReassignRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RouteService(db)
    await svc.reassign_stop(ctx.organization_id, stop_id, body.new_tech_id, body.new_service_day)
    return {"status": "ok"}


@router.get("/day/{service_day}/tech/{tech_id}/polyline")
async def get_polyline(
    service_day: str,
    tech_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get OSRM driving polyline for a tech's route on a given day."""
    svc = RouteService(db)
    routes = await svc.get_routes_for_day(ctx.organization_id, service_day, tech_id)
    if not routes:
        return {"polyline": [], "distance_meters": 0, "duration_seconds": 0}

    route = routes[0]
    tech = route.tech

    coords = []
    # Start at tech depot
    if tech and tech.start_lat and tech.start_lng:
        coords.append((tech.start_lat, tech.start_lng))

    for stop in sorted(route.stops, key=lambda s: s.sequence):
        prop = stop.property
        if prop and prop.lat and prop.lng:
            coords.append((prop.lat, prop.lng))

    # End at tech end depot
    if tech:
        end_lat = tech.end_lat or tech.start_lat
        end_lng = tech.end_lng or tech.start_lng
        if end_lat and end_lng:
            coords.append((end_lat, end_lng))

    return await osrm_service.get_route_polyline(coords)


@router.delete("/{route_id}", status_code=204)
async def delete_route(
    route_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RouteService(db)
    await svc.delete_route(ctx.organization_id, route_id)
