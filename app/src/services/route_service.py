"""Route service — CRUD operations for routes and route stops."""

import uuid
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from src.core.exceptions import NotFoundError
from src.models.route import Route, RouteStop
from src.models.property import Property
from src.models.customer import Customer
from src.models.tech import Tech


class RouteService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_routes(self, org_id: str, routes_data: List[dict]) -> List[Route]:
        """Persist optimization results. Deletes existing routes for same org/day/tech first."""
        saved = []
        for rd in routes_data:
            # Delete existing route for this tech+day
            existing = await self.db.execute(
                select(Route).where(
                    Route.organization_id == org_id,
                    Route.tech_id == rd["tech_id"],
                    Route.service_day == rd["service_day"],
                )
            )
            for old in existing.scalars().all():
                await self.db.delete(old)

            route = Route(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                tech_id=rd["tech_id"],
                service_day=rd["service_day"],
                total_duration_minutes=rd.get("total_duration_minutes", 0),
                total_distance_miles=rd.get("total_distance_miles", 0.0),
                total_stops=rd.get("total_stops", 0),
                optimization_algorithm=rd.get("optimization_algorithm", "ortools_vrp"),
            )
            self.db.add(route)
            await self.db.flush()

            for stop_data in rd.get("stops", []):
                stop = RouteStop(
                    id=str(uuid.uuid4()),
                    route_id=route.id,
                    property_id=stop_data["property_id"],
                    sequence=stop_data["sequence"],
                    estimated_service_duration=stop_data.get("estimated_service_duration", 30),
                    estimated_drive_time_from_previous=stop_data.get("estimated_drive_time_from_previous", 0),
                    estimated_distance_from_previous=stop_data.get("estimated_distance_from_previous", 0.0),
                )
                self.db.add(stop)

            await self.db.flush()
            saved.append(route)

        return saved

    async def get_routes_for_day(
        self, org_id: str, service_day: str, tech_id: Optional[str] = None
    ) -> List[Route]:
        query = (
            select(Route)
            .options(
                selectinload(Route.stops).selectinload(RouteStop.property).joinedload(Property.customer),
                joinedload(Route.tech),
            )
            .where(Route.organization_id == org_id, Route.service_day == service_day)
        )
        if tech_id:
            query = query.where(Route.tech_id == tech_id)

        result = await self.db.execute(query.order_by(Route.tech_id))
        return list(result.unique().scalars().all())

    async def get_routes_for_week(self, org_id: str) -> List[Route]:
        """Get all routes for an org grouped by day."""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        query = (
            select(Route)
            .options(
                selectinload(Route.stops).selectinload(RouteStop.property).joinedload(Property.customer),
                joinedload(Route.tech),
            )
            .where(Route.organization_id == org_id, Route.service_day.in_(days))
            .order_by(Route.service_day, Route.tech_id)
        )
        result = await self.db.execute(query)
        return list(result.unique().scalars().all())

    async def reorder_stop(self, org_id: str, stop_id: str, new_sequence: int) -> RouteStop:
        """Reorder a stop within its route."""
        result = await self.db.execute(
            select(RouteStop)
            .join(Route)
            .where(RouteStop.id == stop_id, Route.organization_id == org_id)
        )
        stop = result.scalar_one_or_none()
        if not stop:
            raise NotFoundError("RouteStop", stop_id)

        old_seq = stop.sequence

        # Get all stops in the same route
        all_stops_result = await self.db.execute(
            select(RouteStop)
            .where(RouteStop.route_id == stop.route_id)
            .order_by(RouteStop.sequence)
        )
        all_stops = list(all_stops_result.scalars().all())

        # Shift sequences
        if new_sequence > old_seq:
            for s in all_stops:
                if old_seq < s.sequence <= new_sequence:
                    s.sequence -= 1
        elif new_sequence < old_seq:
            for s in all_stops:
                if new_sequence <= s.sequence < old_seq:
                    s.sequence += 1

        stop.sequence = new_sequence
        await self.db.flush()
        return stop

    async def reassign_stop(
        self, org_id: str, stop_id: str, new_tech_id: str, new_service_day: str
    ) -> RouteStop:
        """Move a stop to a different tech/day route."""
        result = await self.db.execute(
            select(RouteStop)
            .join(Route)
            .where(RouteStop.id == stop_id, Route.organization_id == org_id)
            .options(joinedload(RouteStop.route))
        )
        stop = result.unique().scalar_one_or_none()
        if not stop:
            raise NotFoundError("RouteStop", stop_id)

        old_route_id = stop.route_id

        # Find or create the target route
        target_result = await self.db.execute(
            select(Route).where(
                Route.organization_id == org_id,
                Route.tech_id == new_tech_id,
                Route.service_day == new_service_day,
            )
        )
        target_route = target_result.scalar_one_or_none()

        if not target_route:
            target_route = Route(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                tech_id=new_tech_id,
                service_day=new_service_day,
            )
            self.db.add(target_route)
            await self.db.flush()

        # Get max sequence in target route
        max_seq_result = await self.db.execute(
            select(RouteStop.sequence)
            .where(RouteStop.route_id == target_route.id)
            .order_by(RouteStop.sequence.desc())
            .limit(1)
        )
        max_seq = max_seq_result.scalar() or 0

        # Move stop
        stop.route_id = target_route.id
        stop.sequence = max_seq + 1

        # Resequence old route
        old_stops_result = await self.db.execute(
            select(RouteStop)
            .where(RouteStop.route_id == old_route_id)
            .order_by(RouteStop.sequence)
        )
        for idx, s in enumerate(old_stops_result.scalars().all(), 1):
            s.sequence = idx

        # Update totals on both routes
        await self._update_route_totals(old_route_id)
        await self._update_route_totals(target_route.id)

        await self.db.flush()
        return stop

    async def delete_route(self, org_id: str, route_id: str) -> None:
        result = await self.db.execute(
            select(Route).where(Route.id == route_id, Route.organization_id == org_id)
        )
        route = result.scalar_one_or_none()
        if not route:
            raise NotFoundError("Route", route_id)
        await self.db.delete(route)
        await self.db.flush()

    async def _update_route_totals(self, route_id: str) -> None:
        stops_result = await self.db.execute(
            select(RouteStop).where(RouteStop.route_id == route_id)
        )
        stops = list(stops_result.scalars().all())

        route_result = await self.db.execute(select(Route).where(Route.id == route_id))
        route = route_result.scalar_one_or_none()
        if route:
            route.total_stops = len(stops)
            route.total_distance_miles = sum(s.estimated_distance_from_previous for s in stops)
            route.total_duration_minutes = sum(
                s.estimated_service_duration + s.estimated_drive_time_from_previous for s in stops
            )
