"""
Route optimization API endpoints.
Provides route generation and management operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.customer import Customer
from app.models.tech import Tech
from app.models.route import Route, RouteStop
from app.schemas.route import (
    RouteOptimizationRequest,
    RouteOptimizationResponse,
    RouteSaveRequest,
    SavedRouteResponse
)
from app.services.optimization import optimization_service
from app.services.pdf_export import pdf_export_service

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post(
    "/optimize",
    response_model=RouteOptimizationResponse,
    summary="Optimize routes for customers and drivers"
)
async def optimize_routes(
    request: RouteOptimizationRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate optimized routes using Google OR-Tools VRP solver.

    - **service_day**: Specific day to optimize (optional)
    - **num_drivers**: Number of drivers to use (optional, uses all active)
    - **allow_day_reassignment**: Allow moving customers to different days
    - **optimization_mode**: 'refine' keeps driver assignments, 'full' allows reassignment

    The optimizer considers:
    - Distance between locations
    - Service duration (based on type and difficulty)
    - Tech working hours
    - Time windows (if specified)
    - Locked service days
    """
    # Get active customers for this organization
    customer_query = select(Customer)\
        .where(Customer.organization_id == auth.organization_id)\
        .where(Customer.is_active == True)

    # For refine mode, only include customers with assigned drivers
    if request.optimization_mode == "refine":
        customer_query = customer_query.where(Customer.assigned_tech_id.isnot(None))

    if request.service_day and not request.allow_day_reassignment:
        # Map day name to abbreviation for schedule checking
        day_abbrev_map = {
            'monday': 'Mo',
            'tuesday': 'Tu',
            'wednesday': 'We',
            'thursday': 'Th',
            'friday': 'Fr',
            'saturday': 'Sa',
            'sunday': 'Su'
        }
        day_lower = request.service_day.lower()
        day_abbrev = day_abbrev_map.get(day_lower)

        # Filter by either:
        # 1. Primary service_day matches (for single-day customers)
        # 2. Day abbreviation is in service_schedule (for multi-day customers)
        if day_abbrev:
            customer_query = customer_query.where(
                or_(
                    Customer.service_day == day_lower,
                    Customer.service_schedule.like(f'%{day_abbrev}%')
                )
            )
        else:
            customer_query = customer_query.where(
                Customer.service_day == day_lower
            )

    customer_result = await db.execute(customer_query)
    customers = list(customer_result.scalars().all())

    # Get active drivers for this organization
    driver_query = select(Tech)\
        .where(Tech.organization_id == auth.organization_id)\
        .where(Tech.is_active == True)
    if request.num_drivers:
        driver_query = driver_query.limit(request.num_drivers)

    driver_result = await db.execute(driver_query)
    drivers = list(driver_result.scalars().all())

    if not customers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active customers found for optimization"
        )

    if not drivers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active drivers found for optimization"
        )

    # Run optimization
    result = await optimization_service.optimize_routes(
        customers=customers,
        drivers=drivers,
        service_day=request.service_day,
        allow_day_reassignment=request.allow_day_reassignment,
        optimization_mode=request.optimization_mode
    )

    return result


@router.post(
    "/save",
    response_model=dict,
    summary="Save optimized routes to database"
)
async def save_routes(
    request: RouteSaveRequest,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Save optimized routes to the database.

    This will:
    - Delete existing routes for the service day
    - Create new routes with stops in optimized order
    """
    # Verify all drivers belong to this organization
    tech_ids = [UUID(route["tech_id"]) for route in request.routes]
    if tech_ids:
        driver_check = await db.execute(
            select(Tech)
            .where(Tech.id.in_(tech_ids))
            .where(Tech.organization_id == auth.organization_id)
        )
        valid_drivers = {str(d.id) for d in driver_check.scalars().all()}

        for route in request.routes:
            if route["tech_id"] not in valid_drivers:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Tech {route['tech_id']} not found or does not belong to your organization"
                )

    # Delete existing routes for this service day and organization
    # Must filter through driver's organization
    existing_routes = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.service_day == request.service_day.lower())
        .where(Tech.organization_id == auth.organization_id)
    )
    for route in existing_routes.scalars().all():
        await db.delete(route)

    saved_routes = []

    for route_data in request.routes:
        # Create route
        route = Route(
            tech_id=UUID(route_data["tech_id"]),
            service_day=request.service_day.lower(),
            total_duration_minutes=route_data.get("total_duration_minutes"),
            total_distance_miles=route_data.get("total_distance_miles"),
            total_customers=len(route_data.get("stops", [])),
            optimization_algorithm="google-or-tools"
        )
        db.add(route)
        await db.flush()  # Get route ID

        # Create route stops
        for stop_data in route_data.get("stops", []):
            stop = RouteStop(
                route_id=route.id,
                customer_id=UUID(stop_data["customer_id"]),
                sequence=stop_data["sequence"],
                estimated_service_duration=stop_data.get("service_duration")
            )
            db.add(stop)

        saved_routes.append(str(route.id))

    await db.commit()

    return {
        "message": f"Successfully saved {len(saved_routes)} routes",
        "route_ids": saved_routes,
        "service_day": request.service_day
    }


@router.get(
    "/day/{service_day}",
    response_model=list[SavedRouteResponse],
    summary="Get saved routes for a specific day"
)
async def get_routes_by_day(
    service_day: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all saved routes for a specific service day.
    """
    result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.service_day == service_day.lower())
        .where(Tech.organization_id == auth.organization_id)
        .order_by(Route.created_at.desc())
    )
    routes = result.scalars().all()

    return routes


@router.delete(
    "/day/{service_day}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all routes for a specific day"
)
async def delete_routes_by_day(
    service_day: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete all routes for a specific service day.
    """
    # Get routes for this day that belong to this organization's drivers
    routes_to_delete = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.service_day == service_day.lower())
        .where(Tech.organization_id == auth.organization_id)
    )

    # Delete each route
    for route in routes_to_delete.scalars().all():
        await db.delete(route)

    await db.commit()


@router.get(
    "/{route_id}",
    summary="Get route details with all stops"
)
async def get_route_details(
    route_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a route including all stops.
    """
    # Get route and verify organization ownership through driver
    route_result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.id == route_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    route = route_result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with ID {route_id} not found"
        )

    # Get stops with customer info
    stops_result = await db.execute(
        select(RouteStop, Customer)
        .join(Customer)
        .where(RouteStop.route_id == route_id)
        .order_by(RouteStop.sequence)
    )

    stops = []
    for stop, customer in stops_result:
        stops.append({
            "sequence": stop.sequence,
            "customer_id": str(customer.id),
            "customer_name": customer.name,
            "address": customer.address,
            "service_duration": stop.estimated_service_duration,
            "latitude": customer.latitude,
            "longitude": customer.longitude
        })

    return {
        "route_id": str(route.id),
        "tech_id": str(route.tech_id),
        "service_day": route.service_day,
        "total_customers": route.total_customers,
        "total_distance_miles": route.total_distance_miles,
        "total_duration_minutes": route.total_duration_minutes,
        "created_at": route.created_at,
        "stops": stops
    }


@router.get(
    "/{route_id}/pdf",
    summary="Download PDF route sheet for a single route"
)
async def download_route_pdf(
    route_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and download a printable PDF route sheet for a single route.

    The PDF includes:
    - Tech information
    - Route summary (total stops, distance, time)
    - Detailed stop list with addresses and service times
    """
    # Get route and verify organization ownership through driver
    route_result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.id == route_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    route = route_result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with ID {route_id} not found"
        )

    # Get driver info
    driver_result = await db.execute(
        select(Tech).where(Tech.id == route.tech_id)
    )
    driver = driver_result.scalar_one_or_none()

    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tech not found for route {route_id}"
        )

    # Get stops with customer info
    stops_result = await db.execute(
        select(RouteStop, Customer)
        .join(Customer)
        .where(RouteStop.route_id == route_id)
        .order_by(RouteStop.sequence)
    )

    stops = []
    for stop, customer in stops_result:
        stops.append({
            "sequence": stop.sequence,
            "customer_id": str(customer.id),
            "customer_name": customer.name,
            "address": customer.address,
            "service_type": customer.service_type,
            "service_duration": stop.estimated_service_duration,
            "latitude": customer.latitude,
            "longitude": customer.longitude
        })

    # Prepare data for PDF
    route_data = {
        "service_day": route.service_day,
        "total_customers": route.total_customers,
        "total_distance_miles": route.total_distance_miles,
        "total_duration_minutes": route.total_duration_minutes,
        "stops": stops
    }

    driver_info = {
        "name": tech.name
    }

    # Generate PDF
    pdf_buffer = pdf_export_service.generate_route_sheet(route_data, driver_info)

    # Return as downloadable file
    filename = f"route_{tech.name.replace(' ', '_')}_{route.service_day}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get(
    "/day/{service_day}/pdf",
    summary="Download PDF with all routes for a service day"
)
async def download_day_routes_pdf(
    service_day: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and download a multi-page PDF with all routes for a service day.

    Each route gets its own page with complete route information.
    """
    # Get all routes for this day that belong to this organization's drivers
    routes_result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.service_day == service_day.lower())
        .where(Tech.organization_id == auth.organization_id)
        .order_by(Route.created_at.desc())
    )
    routes = list(routes_result.scalars().all())

    if not routes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No routes found for {service_day}"
        )

    # Get all drivers for these routes
    tech_ids = [route.tech_id for route in routes]
    drivers_result = await db.execute(
        select(Tech).where(Tech.id.in_(tech_ids))
    )
    drivers_list = drivers_result.scalars().all()
    drivers_dict = {str(tech.id): {"name": tech.name} for driver in drivers_list}

    # Build route data for each route
    routes_data = []
    for route in routes:
        # Get stops with customer info
        stops_result = await db.execute(
            select(RouteStop, Customer)
            .join(Customer)
            .where(RouteStop.route_id == route.id)
            .order_by(RouteStop.sequence)
        )

        stops = []
        for stop, customer in stops_result:
            stops.append({
                "sequence": stop.sequence,
                "customer_id": str(customer.id),
                "customer_name": customer.name,
                "address": customer.address,
                "service_type": customer.service_type,
                "service_duration": stop.estimated_service_duration,
                "latitude": customer.latitude,
                "longitude": customer.longitude
            })

        routes_data.append({
            "tech_id": str(route.tech_id),
            "service_day": route.service_day,
            "total_customers": route.total_customers,
            "total_distance_miles": route.total_distance_miles,
            "total_duration_minutes": route.total_duration_minutes,
            "stops": stops
        })

    # Generate multi-route PDF
    pdf_buffer = pdf_export_service.generate_multi_route_pdf(routes_data, drivers_dict)

    # Return as downloadable file
    filename = f"routes_{service_day}_{len(routes)}_drivers.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.patch(
    "/{route_id}/stops",
    summary="Update route stops order or reassign stops"
)
async def update_route_stops(
    route_id: UUID,
    stops_update: dict,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the sequence of stops in a route or move stops between routes.

    Request body format:
    {
        "stops": [
            {"stop_id": "uuid", "sequence": 1},
            {"stop_id": "uuid", "sequence": 2},
            ...
        ]
    }
    """
    # Get route and verify organization ownership through driver
    route_result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.id == route_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    route = route_result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with ID {route_id} not found"
        )

    # Update stop sequences
    stops_data = stops_update.get("stops", [])

    for stop_data in stops_data:
        stop_id = UUID(stop_data["stop_id"])
        new_sequence = stop_data["sequence"]

        # Update the stop
        stop_result = await db.execute(
            select(RouteStop).where(RouteStop.id == stop_id)
        )
        stop = stop_result.scalar_one_or_none()

        if stop:
            stop.sequence = new_sequence

    # Update route customer count
    stops_count_result = await db.execute(
        select(RouteStop).where(RouteStop.route_id == route_id)
    )
    route.total_customers = len(list(stops_count_result.scalars().all()))

    await db.commit()

    return {
        "message": "Route stops updated successfully",
        "route_id": str(route_id),
        "updated_stops": len(stops_data)
    }


@router.post(
    "/{route_id}/stops/{stop_id}/move",
    summary="Move a stop to a different route"
)
async def move_stop_to_route(
    route_id: UUID,
    stop_id: UUID,
    move_data: dict,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Move a stop from one route to another.

    Request body format:
    {
        "target_route_id": "uuid",
        "sequence": 1
    }
    """
    target_route_id = UUID(move_data["target_route_id"])
    new_sequence = move_data.get("sequence", 1)

    # Get the stop
    stop_result = await db.execute(
        select(RouteStop).where(RouteStop.id == stop_id)
    )
    stop = stop_result.scalar_one_or_none()

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop with ID {stop_id} not found"
        )

    # Get target route and verify organization ownership
    target_route_result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.id == target_route_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    target_route = target_route_result.scalar_one_or_none()

    if not target_route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target route with ID {target_route_id} not found"
        )

    # Get source route and verify organization ownership
    source_route_result = await db.execute(
        select(Route)
        .join(Tech)
        .where(Route.id == stop.route_id)
        .where(Tech.organization_id == auth.organization_id)
    )
    source_route = source_route_result.scalar_one_or_none()

    if not source_route:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Source route does not belong to your organization"
        )

    # Update stop's route and sequence
    old_route_id = stop.route_id
    stop.route_id = target_route_id
    stop.sequence = new_sequence

    # Resequence remaining stops in source route
    source_stops_result = await db.execute(
        select(RouteStop)
        .where(RouteStop.route_id == old_route_id)
        .order_by(RouteStop.sequence)
    )
    source_stops = list(source_stops_result.scalars().all())
    for idx, source_stop in enumerate(source_stops, start=1):
        source_stop.sequence = idx

    # Update customer counts
    if source_route:
        source_route.total_customers = len(source_stops)

    target_stops_result = await db.execute(
        select(RouteStop).where(RouteStop.route_id == target_route_id)
    )
    target_route.total_customers = len(list(target_stops_result.scalars().all()))

    await db.commit()

    return {
        "message": "Stop moved successfully",
        "stop_id": str(stop_id),
        "from_route": str(old_route_id),
        "to_route": str(target_route_id),
        "new_sequence": new_sequence
    }
