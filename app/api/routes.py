"""
Route optimization API endpoints.
Provides route generation and management operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models.customer import Customer
from app.models.driver import Driver
from app.models.route import Route, RouteStop
from app.schemas.route import (
    RouteOptimizationRequest,
    RouteOptimizationResponse,
    RouteSaveRequest,
    SavedRouteResponse
)
from app.services.optimization import optimization_service

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post(
    "/optimize",
    response_model=RouteOptimizationResponse,
    summary="Optimize routes for customers and drivers"
)
async def optimize_routes(
    request: RouteOptimizationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate optimized routes using Google OR-Tools VRP solver.

    - **service_day**: Specific day to optimize (optional)
    - **num_drivers**: Number of drivers to use (optional, uses all active)
    - **allow_day_reassignment**: Allow moving customers to different days

    The optimizer considers:
    - Distance between locations
    - Service duration (based on type and difficulty)
    - Driver working hours
    - Time windows (if specified)
    - Locked service days
    """
    # Get active customers
    customer_query = select(Customer).where(Customer.is_active == True)
    if request.service_day and not request.allow_day_reassignment:
        customer_query = customer_query.where(
            Customer.service_day == request.service_day.lower()
        )

    customer_result = await db.execute(customer_query)
    customers = list(customer_result.scalars().all())

    # Get active drivers
    driver_query = select(Driver).where(Driver.is_active == True)
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
        allow_day_reassignment=request.allow_day_reassignment
    )

    return result


@router.post(
    "/save",
    response_model=dict,
    summary="Save optimized routes to database"
)
async def save_routes(
    request: RouteSaveRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Save optimized routes to the database.

    This will:
    - Delete existing routes for the service day
    - Create new routes with stops in optimized order
    """
    # Delete existing routes for this service day
    await db.execute(
        delete(Route).where(Route.service_day == request.service_day.lower())
    )

    saved_routes = []

    for route_data in request.routes:
        # Create route
        route = Route(
            driver_id=UUID(route_data["driver_id"]),
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
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all saved routes for a specific service day.
    """
    result = await db.execute(
        select(Route)
        .where(Route.service_day == service_day.lower())
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
    db: AsyncSession = Depends(get_db)
):
    """
    Delete all routes for a specific service day.
    """
    await db.execute(
        delete(Route).where(Route.service_day == service_day.lower())
    )
    await db.commit()


@router.get(
    "/{route_id}",
    summary="Get route details with all stops"
)
async def get_route_details(
    route_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a route including all stops.
    """
    # Get route
    route_result = await db.execute(
        select(Route).where(Route.id == route_id)
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
        "driver_id": str(route.driver_id),
        "service_day": route.service_day,
        "total_customers": route.total_customers,
        "total_distance_miles": route.total_distance_miles,
        "total_duration_minutes": route.total_duration_minutes,
        "created_at": route.created_at,
        "stops": stops
    }
