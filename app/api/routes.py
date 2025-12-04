"""
Route optimization API endpoints.
Provides route generation and management operations.
"""

import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
from datetime import date, timedelta

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.customer import Customer
from app.models.tech import Tech
from app.models.route import Route, RouteStop
from app.models.temp_assignment import TempTechAssignment
from app.models.tech_route import TechRoute
from app.schemas.route import (
    RouteOptimizationRequest,
    RouteOptimizationResponse,
    RouteSaveRequest,
    SavedRouteResponse
)
from app.services.optimization import optimization_service
from app.services.pdf_export import pdf_export_service
from app.services.tech_routing import tech_routing_service

logger = logging.getLogger(__name__)

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

    Supports three optimization scopes:
    - **selected_day**: Optimize selected techs for a specific day
    - **entire_week**: Optimize selected techs for all days Mon-Sat (no day changes)
    - **complete_rerouting**: Optimize all techs, all days with optional day reassignment

    The optimizer considers:
    - Distance between locations
    - Service duration (based on type and difficulty)
    - Tech working hours and efficiency multipliers
    - Time windows (if specified)
    - Day assignment locks
    """
    logger.info(
        f"Optimization request: scope={request.optimization_scope}, "
        f"selected_techs={request.selected_tech_ids}, "
        f"service_day={request.service_day}, "
        f"mode={request.optimization_mode}, "
        f"speed={request.optimization_speed}"
    )

    # Base customer query
    customer_query = select(Customer).where(Customer.organization_id == auth.organization_id)

    if request.include_pending:
        customer_query = customer_query.where(
            or_(Customer.status == 'active', Customer.status == 'pending')
        )
    else:
        customer_query = customer_query.where(Customer.is_active == True)

    if not request.include_unassigned:
        customer_query = customer_query.where(Customer.assigned_tech_id.isnot(None))

    # Base tech query
    driver_query = select(Tech).where(
        Tech.organization_id == auth.organization_id,
        Tech.is_active == True
    )

    # Handle different optimization scopes
    if request.optimization_scope == "selected_day":
        # Scope 1: Selected techs, selected day only
        if not request.service_day:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="service_day required for selected_day scope"
            )
        if not request.selected_tech_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_tech_ids required for selected_day scope"
            )

        # Filter techs by selection
        driver_query = driver_query.where(Tech.id.in_([UUID(tid) for tid in request.selected_tech_ids]))

        # Filter customers by day
        day_lower = request.service_day.lower()
        day_abbrev_map = {'monday': 'Mo', 'tuesday': 'Tu', 'wednesday': 'We',
                          'thursday': 'Th', 'friday': 'Fr', 'saturday': 'Sa', 'sunday': 'Su'}
        day_abbrev = day_abbrev_map.get(day_lower)

        if day_abbrev:
            customer_query = customer_query.where(
                or_(Customer.service_day == day_lower, Customer.service_schedule.like(f'%{day_abbrev}%'))
            )

        customer_result = await db.execute(customer_query)
        customers = list(customer_result.scalars().all())

        driver_result = await db.execute(driver_query)
        drivers = list(driver_result.scalars().all())

        if not customers or not drivers:
            return {"routes": [], "message": "No customers or techs found for optimization"}

        result = await optimization_service.optimize_routes(
            customers=customers,
            techs=drivers,
            service_day=request.service_day,
            allow_day_reassignment=False,
            optimization_mode=request.optimization_mode,
            optimization_speed=request.optimization_speed
        )

        return result

    elif request.optimization_scope == "entire_week":
        # Scope 2: Selected techs, all days Mon-Sat separately (no day changes)
        if not request.selected_tech_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_tech_ids required for entire_week scope"
            )

        # Filter techs by selection
        driver_query = driver_query.where(Tech.id.in_([UUID(tid) for tid in request.selected_tech_ids]))
        driver_result = await db.execute(driver_query)
        drivers = list(driver_result.scalars().all())

        if not drivers:
            return {"routes": [], "message": "No techs found for optimization"}

        # Get all customers (no day filter yet)
        customer_result = await db.execute(customer_query)
        all_customers = list(customer_result.scalars().all())

        if not all_customers:
            return {"routes": [], "message": "No customers found for optimization"}

        # Optimize each day separately
        all_routes = []
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
        day_abbrev_map = {'monday': 'Mo', 'tuesday': 'Tu', 'wednesday': 'We',
                          'thursday': 'Th', 'friday': 'Fr', 'saturday': 'Sa'}

        for day in days:
            day_customers = [
                c for c in all_customers
                if c.service_day == day or (c.service_schedule and day_abbrev_map[day] in c.service_schedule)
            ]

            if not day_customers:
                continue

            day_result = await optimization_service.optimize_routes(
                customers=day_customers,
                techs=drivers,
                service_day=day,
                allow_day_reassignment=False,
                optimization_mode=request.optimization_mode,
                optimization_speed=request.optimization_speed
            )

            if day_result and "routes" in day_result:
                all_routes.extend(day_result["routes"])

        return {"routes": all_routes, "summary": {"total_routes": len(all_routes)}}

    elif request.optimization_scope == "complete_rerouting":
        # Scope 3: All techs, all days - just optimize each day separately
        all_routes = []
        # Build days list based on flags (weekdays by default)
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        if request.include_saturday:
            days.append('saturday')
        if request.include_sunday:
            days.append('sunday')

        for day in days:
            # Get customers for this day
            day_customer_query = customer_query.where(
                or_(
                    Customer.service_day == day,
                    Customer.service_schedule.like(f'%{day[:2].capitalize()}%')
                )
            )
            customer_result = await db.execute(day_customer_query)
            day_customers = list(customer_result.scalars().all())

            if not day_customers:
                continue

            # Get all techs
            driver_result = await db.execute(driver_query)
            day_techs = list(driver_result.scalars().all())

            if not day_techs:
                continue

            try:
                day_result = await optimization_service.optimize_routes(
                    customers=day_customers,
                    techs=day_techs,
                    service_day=day,
                    allow_day_reassignment=False,
                    unlocked_customer_ids=None,
                    optimization_mode=request.optimization_mode,
                    optimization_speed=request.optimization_speed
                )

                if day_result and "routes" in day_result:
                    all_routes.extend(day_result["routes"])
            except Exception as e:
                logger.error(f"Optimization failed for {day}: {str(e)}")
                logger.error(traceback.format_exc())
                # Continue with other days

        return {"routes": all_routes, "summary": {"total_routes": len(all_routes)}}

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid optimization_scope: {request.optimization_scope}"
        )


@router.post(
    "/temp-assignment",
    response_model=dict,
    summary="Create temporary tech assignment for a customer"
)
async def create_temp_assignment(
    request: dict,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a temporary tech assignment that persists for the current day only.
    This allows reassigning customers to different techs without updating the permanent record.

    Automatically re-routes affected techs and returns updated routes.
    """
    customer_id = UUID(request.get("customer_id"))
    new_tech_id = UUID(request.get("tech_id"))
    service_day = request.get("service_day")
    today = date.today()

    # Clean up old temp assignments (older than 6 days)
    cutoff_date = today - timedelta(days=6)
    await db.execute(
        delete(TempTechAssignment).where(
            TempTechAssignment.organization_id == auth.organization_id,
            TempTechAssignment.assignment_date < cutoff_date
        )
    )

    # Get old tech ID if there was a previous temp assignment
    old_temp_result = await db.execute(
        select(TempTechAssignment).where(
            TempTechAssignment.organization_id == auth.organization_id,
            TempTechAssignment.customer_id == customer_id,
            TempTechAssignment.service_day == service_day,
            TempTechAssignment.assignment_date == today
        )
    )
    old_temp = old_temp_result.scalar_one_or_none()
    old_tech_id = old_temp.tech_id if old_temp else None

    # Get customer's permanent assignment to check if we need to re-route original tech
    customer_result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = customer_result.scalar_one()

    # If no old temp assignment, old tech is the permanent assignment
    if not old_tech_id:
        old_tech_id = customer.assigned_tech_id

    # Delete existing temp assignment for this customer/day
    await db.execute(
        delete(TempTechAssignment).where(
            TempTechAssignment.organization_id == auth.organization_id,
            TempTechAssignment.customer_id == customer_id,
            TempTechAssignment.service_day == service_day
        )
    )

    # Only create temp assignment if different from permanent assignment
    if new_tech_id != customer.assigned_tech_id:
        temp_assignment = TempTechAssignment(
            organization_id=auth.organization_id,
            customer_id=customer_id,
            tech_id=new_tech_id,
            service_day=service_day,
            assignment_date=today
        )
        db.add(temp_assignment)

    await db.commit()

    # Collect affected tech IDs (both old and new, excluding None)
    affected_tech_ids = set()
    if old_tech_id:
        affected_tech_ids.add(old_tech_id)
    if new_tech_id:
        affected_tech_ids.add(new_tech_id)

    # Delete routes for affected techs
    await db.execute(
        delete(TechRoute).where(
            TechRoute.organization_id == auth.organization_id,
            TechRoute.tech_id.in_(list(affected_tech_ids)),
            TechRoute.service_day == service_day,
            TechRoute.route_date == today
        )
    )
    await db.commit()

    # Generate new routes for affected techs
    updated_routes = []

    for tech_id in affected_tech_ids:
        # Load tech
        tech_result = await db.execute(
            select(Tech).where(Tech.id == tech_id)
        )
        tech = tech_result.scalar_one_or_none()
        if not tech:
            continue

        # Get customers for this tech on this day (with temp assignments applied)
        # Start with customers that have this day in their schedule
        day_abbrev_map = {
            'monday': 'Mo', 'tuesday': 'Tu', 'wednesday': 'We',
            'thursday': 'Th', 'friday': 'Fr', 'saturday': 'Sa', 'sunday': 'Su'
        }
        day_abbrev = day_abbrev_map.get(service_day.lower())

        customers_query = select(Customer).where(
            Customer.organization_id == auth.organization_id,
            Customer.is_active == True,
            or_(
                Customer.service_day == service_day.lower(),
                Customer.service_schedule.like(f'%{day_abbrev}%') if day_abbrev else False
            )
        )
        customers_result = await db.execute(customers_query)
        all_customers = list(customers_result.scalars().all())

        # Get temp assignments for today/this day
        temp_assignments_query = select(TempTechAssignment).where(
            TempTechAssignment.organization_id == auth.organization_id,
            TempTechAssignment.service_day == service_day,
            TempTechAssignment.assignment_date == today
        )
        temp_assignments_result = await db.execute(temp_assignments_query)
        temp_assignments = {ta.customer_id: ta.tech_id for ta in temp_assignments_result.scalars().all()}

        # Filter to customers assigned to this tech (permanent or temp)
        tech_customers = []
        for c in all_customers:
            # Check if temp assignment exists
            if c.id in temp_assignments:
                if temp_assignments[c.id] == tech_id:
                    tech_customers.append(c)
            elif c.assigned_tech_id == tech_id:
                tech_customers.append(c)

        # Generate route (with auto-created visits)
        tech_route = await tech_routing_service.generate_route_for_tech(
            tech=tech,
            customers=tech_customers,
            service_day=service_day,
            route_date=today,
            organization_id=auth.organization_id,
            db_session=db
        )

        # Save route
        db.add(tech_route)
        await db.commit()
        await db.refresh(tech_route)

        # Convert to response format
        updated_routes.append({
            "tech_id": str(tech_id),
            "tech_name": tech.name,
            "tech_color": tech.color,
            "stop_sequence": tech_route.stop_sequence,
            "total_distance": tech_route.total_distance,
            "total_duration": tech_route.total_duration
        })

    return {
        "message": "Temporary assignment created and routes updated",
        "id": str(temp_assignment.id),
        "updated_routes": updated_routes
    }


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
        "name": driver.name
    }

    # Generate PDF
    pdf_buffer = pdf_export_service.generate_route_sheet(route_data, driver_info)

    # Return as downloadable file
    filename = f"route_{driver.name.replace(' ', '_')}_{route.service_day}.pdf"

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
    drivers_dict = {str(driver.id): {"name": driver.name} for driver in drivers_list}

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


@router.get(
    "/tech-routes/{service_day}",
    summary="Get tech routes for a specific day"
)
async def get_tech_routes_for_day(
    service_day: str,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all tech routes for a specific service day.
    Auto-generates routes if they don't exist.
    Returns routes with stop sequences for drawing on the map.
    """
    today = date.today()

    # Get all tech routes for this day and organization
    result = await db.execute(
        select(TechRoute)
        .options(selectinload(TechRoute.tech))
        .where(TechRoute.organization_id == auth.organization_id)
        .where(TechRoute.service_day == service_day)
        .where(TechRoute.route_date == today)
    )
    tech_routes = list(result.scalars().all())

    # If no routes exist, auto-generate them
    if not tech_routes:
        logger.info(f"No routes found for {service_day}, auto-generating...")

        # Get all techs for this organization
        techs_result = await db.execute(
            select(Tech)
            .where(Tech.organization_id == auth.organization_id)
            .where(Tech.is_active == True)
        )
        techs = techs_result.scalars().all()

        # Get all customers with temp assignments applied
        temp_assignments_result = await db.execute(
            select(TempTechAssignment)
            .where(TempTechAssignment.organization_id == auth.organization_id)
            .where(TempTechAssignment.service_day == service_day)
            .where(TempTechAssignment.assignment_date == today)
        )
        temp_assignments_by_customer = {
            str(ta.customer_id): ta for ta in temp_assignments_result.scalars().all()
        }

        # Generate route for each tech
        for tech in techs:
            # Get customers for this tech and day (with temp assignments applied)
            customers_query = (
                select(Customer)
                .where(Customer.organization_id == auth.organization_id)
                .where(Customer.is_active == True)
            )

            customers_result = await db.execute(customers_query)
            all_customers = customers_result.scalars().all()

            # Day abbreviation mapping for service_schedule check
            day_abbrev_map = {
                'monday': 'Mo', 'tuesday': 'Tu', 'wednesday': 'We',
                'thursday': 'Th', 'friday': 'Fr', 'saturday': 'Sa', 'sunday': 'Su'
            }
            day_abbrev = day_abbrev_map.get(service_day.lower())

            # Filter customers for this tech and day
            tech_customers = []
            for customer in all_customers:
                # Check if customer is scheduled for this day
                is_scheduled_today = (
                    customer.service_day == service_day or
                    (day_abbrev and customer.service_schedule and day_abbrev in customer.service_schedule)
                )

                if not is_scheduled_today:
                    continue

                # Check if there's a temp assignment for this customer
                temp_assignment = temp_assignments_by_customer.get(str(customer.id))

                if temp_assignment:
                    # Use temp assignment
                    if temp_assignment.tech_id == tech.id:
                        tech_customers.append(customer)
                else:
                    # Use permanent assignment
                    if customer.assigned_tech_id == tech.id:
                        tech_customers.append(customer)

            # Generate route if tech has customers (with auto-created visits)
            if tech_customers:
                tech_route = await tech_routing_service.generate_route_for_tech(
                    tech=tech,
                    customers=tech_customers,
                    service_day=service_day,
                    route_date=today,
                    organization_id=auth.organization_id,
                    db_session=db
                )

                db.add(tech_route)
                tech_routes.append(tech_route)

        await db.commit()

        # Reload with relationships
        if tech_routes:
            result = await db.execute(
                select(TechRoute)
                .options(selectinload(TechRoute.tech))
                .where(TechRoute.organization_id == auth.organization_id)
                .where(TechRoute.service_day == service_day)
                .where(TechRoute.route_date == today)
            )
            tech_routes = list(result.scalars().all())

    if not tech_routes:
        return []

    # Get all active customers for this organization to look up details
    customer_result = await db.execute(
        select(Customer)
        .where(Customer.organization_id == auth.organization_id)
        .where(Customer.is_active == True)
    )
    customers_by_id = {str(c.id): c for c in customer_result.scalars().all()}

    # Build response
    routes = []
    for tech_route in tech_routes:
        # Get customer details for each stop in sequence
        stops = []
        for customer_id in tech_route.stop_sequence:
            customer = customers_by_id.get(customer_id)
            if customer:
                # Format address as "street, city"
                address_parts = customer.address.split(',')
                short_address = ', '.join(address_parts[:2]).strip() if len(address_parts) >= 2 else customer.address

                stops.append({
                    "customer_id": customer_id,
                    "customer_name": customer.display_name or customer.name,
                    "address": short_address,
                    "latitude": customer.latitude,
                    "longitude": customer.longitude
                })

        routes.append({
            "tech_id": str(tech_route.tech_id),
            "driver_id": str(tech_route.tech_id),
            "driver_name": tech_route.tech.name,
            "driver_color": tech_route.tech.color,
            "service_day": tech_route.service_day,
            "start_location": {
                "address": tech_route.tech.start_location_address,
                "latitude": tech_route.tech.start_latitude,
                "longitude": tech_route.tech.start_longitude
            },
            "end_location": {
                "address": tech_route.tech.end_location_address,
                "latitude": tech_route.tech.end_latitude,
                "longitude": tech_route.tech.end_longitude
            },
            "stop_sequence": tech_route.stop_sequence,
            "stops": stops,
            "total_distance": tech_route.total_distance,
            "total_duration": tech_route.total_duration
        })

    return routes
