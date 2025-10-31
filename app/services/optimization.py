"""
Route optimization service using Google OR-Tools.
Solves Vehicle Routing Problem (VRP) with time windows and constraints.
"""

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from typing import List, Dict, Optional, Tuple
from datetime import datetime, time, timedelta
import logging
import math

from app.models.customer import Customer
from app.models.tech import Tech
from app.config import settings
from app.services.routing import routing_service

logger = logging.getLogger(__name__)


class RouteOptimizationService:
    """Service for optimizing routes using Google OR-Tools VRP solver."""

    def __init__(self):
        """Initialize optimization service."""
        self.time_limit_seconds = settings.optimization_time_limit_seconds

    def _calculate_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate Haversine distance between two GPS coordinates in miles.

        Args:
            lat1, lon1: First location coordinates
            lat2, lon2: Second location coordinates

        Returns:
            Distance in miles
        """
        R = 3959  # Earth radius in miles

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _create_distance_matrix(
        self,
        locations: List[Tuple[float, float]]
    ) -> List[List[int]]:
        """
        Create distance matrix between all locations.

        Args:
            locations: List of (latitude, longitude) tuples

        Returns:
            Matrix of distances in meters (for OR-Tools)
        """
        num_locations = len(locations)
        distance_matrix = [[0] * num_locations for _ in range(num_locations)]

        for i in range(num_locations):
            for j in range(num_locations):
                if i != j:
                    distance_miles = self._calculate_distance(
                        locations[i][0], locations[i][1],
                        locations[j][0], locations[j][1]
                    )
                    # Convert to meters and round to integer
                    distance_matrix[i][j] = int(distance_miles * 1609.34)

        return distance_matrix

    def _create_time_matrix(
        self,
        distance_matrix: List[List[int]],
        avg_speed_mph: float = 30.0
    ) -> List[List[int]]:
        """
        Create time matrix from distance matrix.

        Args:
            distance_matrix: Matrix of distances in meters
            avg_speed_mph: Average driving speed in mph

        Returns:
            Matrix of travel times in minutes
        """
        num_locations = len(distance_matrix)
        time_matrix = [[0] * num_locations for _ in range(num_locations)]

        for i in range(num_locations):
            for j in range(num_locations):
                # Convert meters to miles, divide by speed, convert to minutes
                distance_miles = distance_matrix[i][j] / 1609.34
                time_hours = distance_miles / avg_speed_mph
                time_matrix[i][j] = int(time_hours * 60)

        return time_matrix

    def _customer_services_on_day(self, customer: Customer, service_day: str) -> bool:
        """
        Check if a customer needs service on a specific day.

        Args:
            customer: Customer to check
            service_day: Day to check (e.g., 'monday')

        Returns:
            True if customer needs service on this day
        """
        # Single-day customers
        if customer.service_days_per_week == 1:
            return customer.service_day.lower() == service_day.lower()

        # Multi-day customers - check if day is in their schedule
        if customer.service_schedule:
            # Map full day names to abbreviations
            day_abbrev = {
                'monday': 'Mo',
                'tuesday': 'Tu',
                'wednesday': 'We',
                'thursday': 'Th',
                'friday': 'Fr',
                'saturday': 'Sa',
                'sunday': 'Su'
            }
            day_code = day_abbrev.get(service_day.lower())
            return day_code and day_code in customer.service_schedule

        return False

    async def _optimize_refine_mode(
        self,
        customers: List[Customer],
        techs: List[Tech],
        service_day: Optional[str] = None
    ) -> Dict:
        """
        Optimize routes in refine mode - keeps tech assignments, only optimizes order.

        Args:
            customers: List of customers (already filtered to have assigned techs)
            techs: List of available techs
            service_day: Specific day to optimize

        Returns:
            Dict with optimized routes per tech
        """
        # Group customers by assigned tech
        tech_customers_map = {}
        for customer in customers:
            if customer.assigned_tech_id:
                if customer.assigned_tech_id not in tech_customers_map:
                    tech_customers_map[customer.assigned_tech_id] = []
                tech_customers_map[customer.assigned_tech_id].append(customer)

        # Create tech lookup
        tech_lookup = {tech.id: tech for tech in techs}

        # Optimize each tech's route separately
        all_routes = []
        total_distance = 0
        total_duration = 0
        total_customers = 0

        for tech_id, tech_customers in tech_customers_map.items():
            tech = tech_lookup.get(tech_id)
            if not tech:
                continue

            # Filter customers by service day if needed
            if service_day:
                tech_customers = [
                    c for c in tech_customers
                    if self._customer_services_on_day(c, service_day)
                ]

            if not tech_customers:
                continue

            # Filter out customers without coordinates
            valid_customers = [
                c for c in tech_customers
                if c.latitude and c.longitude
            ]

            if not valid_customers:
                continue

            # Build locations: [depot, customer1, customer2, ...]
            depot_location = (tech.start_latitude, tech.start_longitude)
            locations = [depot_location]

            for customer in valid_customers:
                locations.append((customer.latitude, customer.longitude))

            # Get distance and time matrices from routing service
            import asyncio
            distance_matrix, time_matrix = asyncio.run(
                routing_service.get_distance_matrix(locations)
            )

            # Create routing model for single tech
            manager = pywrapcp.RoutingIndexManager(
                len(locations),
                1,  # Single tech
                0   # Depot index
            )
            routing = pywrapcp.RoutingModel(manager)

            # Distance callback
            def distance_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                return distance_matrix[from_node][to_node]

            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # Time callback
            def time_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                travel_time = time_matrix[from_node][to_node]

                service_time = 0
                if to_node > 0:
                    customer = valid_customers[to_node - 1]
                    service_time = customer.base_service_duration

                return travel_time + service_time

            time_callback_index = routing.RegisterTransitCallback(time_callback)

            # Add time dimension
            routing.AddDimension(
                time_callback_index,
                60,   # Allow 60 minutes waiting time
                480,  # Maximum 8 hours per route
                False,
                'Time'
            )

            # Set search parameters
            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            )
            search_parameters.time_limit.seconds = self.time_limit_seconds

            # Solve
            solution = routing.SolveWithParameters(search_parameters)

            if solution:
                # Extract route
                route_customers = []
                route_distance = 0
                index = routing.Start(0)

                while not routing.IsEnd(index):
                    node_index = manager.IndexToNode(index)

                    if node_index > 0:  # Not depot
                        customer = valid_customers[node_index - 1]
                        route_customers.append({
                            "customer_id": str(customer.id),
                            "customer_name": customer.name,
                            "address": customer.address,
                            "latitude": customer.latitude,
                            "longitude": customer.longitude,
                            "service_duration": customer.base_service_duration,
                            "sequence": len(route_customers) + 1
                        })

                    previous_index = index
                    index = solution.Value(routing.NextVar(index))
                    route_distance += routing.GetArcCostForVehicle(
                        previous_index, index, 0
                    )

                # Calculate metrics
                route_distance_miles = route_distance / 1609.34
                time_dimension = routing.GetDimensionOrDie('Time')
                time_var = time_dimension.CumulVar(routing.End(0))
                route_duration = solution.Value(time_var)

                if route_customers:
                    all_routes.append({
                        "driver_id": str(tech.id),
                        "driver_name": tech.name,
                        "driver_color": tech.color if hasattr(tech, 'color') else '#3498db',
                        "service_day": service_day or "multiple",
                        "start_location": {
                            "address": tech.start_location_address,
                            "latitude": tech.start_latitude,
                            "longitude": tech.start_longitude
                        },
                        "end_location": {
                            "address": tech.end_location_address,
                            "latitude": tech.end_latitude,
                            "longitude": tech.end_longitude
                        },
                        "stops": route_customers,
                        "total_customers": len(route_customers),
                        "total_distance_miles": round(route_distance_miles, 2),
                        "total_duration_minutes": route_duration
                    })

                    total_distance += route_distance_miles
                    total_duration += route_duration
                    total_customers += len(route_customers)

        return {
            "routes": all_routes,
            "summary": {
                "total_routes": len(all_routes),
                "total_customers": total_customers,
                "total_distance_miles": round(total_distance, 2),
                "total_duration_minutes": total_duration,
                "optimization_time_seconds": self.time_limit_seconds,
                "optimization_mode": "refine"
            }
        }

    async def optimize_routes(
        self,
        customers: List[Customer],
        techs: List[Tech],
        service_day: Optional[str] = None,
        allow_day_reassignment: bool = False,
        optimization_mode: str = "full"
    ) -> Dict:
        """
        Optimize routes for given customers and techs.

        Args:
            customers: List of customers to route
            techs: List of available techs
            service_day: Specific day to optimize (or None for all)
            allow_day_reassignment: If True, can move customers to different days
            optimization_mode: 'refine' keeps tech assignments, 'full' allows reassignment

        Returns:
            Dict with optimized routes per tech
        """
        if not customers:
            return {"routes": [], "message": "No customers to optimize"}

        if not techs:
            return {"routes": [], "message": "No techs available"}

        # Handle refine mode: optimize each tech's assigned customers separately
        if optimization_mode == "refine":
            return await self._optimize_refine_mode(
                customers, techs, service_day
            )

        # If no specific day selected, handle based on reassignment setting
        if not service_day:
            if allow_day_reassignment:
                # TRUE FULL OPTIMIZATION: Optimize all customers across all days
                # This is computationally expensive but provides best overall optimization
                logger.info("Running full cross-day optimization - this may take several minutes")
                # For now, return a message. Full cross-day optimization with day assignment
                # is a complex problem that requires additional constraints.
                return {
                    "routes": [],
                    "message": "Full cross-day optimization with day reassignment is not yet implemented. "
                               "Please either select a specific day or uncheck 'Allow day reassignment' "
                               "to optimize each day separately."
                }
            else:
                # Optimize each day separately (maintains current day assignments)
                logger.info("Optimizing all days separately")
                all_routes = []
                total_customers = 0
                total_distance = 0
                total_duration = 0

                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']

                for day in days:
                    day_customers = [c for c in customers if self._customer_services_on_day(c, day)]

                    if not day_customers:
                        continue

                    logger.info(f"Optimizing {len(day_customers)} customers for {day}")

                    day_result = await self._optimize_single_day(
                        day_customers, techs, day
                    )

                    if day_result and "routes" in day_result:
                        all_routes.extend(day_result["routes"])
                        if "summary" in day_result:
                            total_customers += day_result["summary"].get("total_customers", 0)
                            total_distance += day_result["summary"].get("total_distance_miles", 0)
                            total_duration += day_result["summary"].get("total_duration_minutes", 0)

                return {
                    "routes": all_routes,
                    "summary": {
                        "total_routes": len(all_routes),
                        "total_customers": total_customers,
                        "total_distance_miles": round(total_distance, 2),
                        "total_duration_minutes": total_duration,
                        "optimization_time_seconds": self.time_limit_seconds,
                        "optimization_mode": "full_per_day"
                    }
                }

        # Filter customers by service day if specified
        if service_day and not allow_day_reassignment:
            customers = [c for c in customers if self._customer_services_on_day(c, service_day)]

        # Filter out customers without geocoded coordinates
        valid_customers = [c for c in customers if c.latitude and c.longitude]

        if not valid_customers:
            return {
                "routes": [],
                "message": "No customers with valid GPS coordinates"
            }

        logger.info(
            f"Optimizing routes for {len(valid_customers)} customers "
            f"and {len(techs)} techs"
        )

        return await self._optimize_single_day(valid_customers, techs, service_day)

    async def _optimize_single_day(
        self,
        customers: List[Customer],
        techs: List[Tech],
        service_day: Optional[str] = None
    ) -> Dict:
        """
        Optimize routes for a single day.

        Args:
            customers: List of customers to route (already filtered)
            techs: List of available techs
            service_day: Day being optimized

        Returns:
            Dict with optimized routes
        """
        # Filter out customers without geocoded coordinates
        valid_customers = [c for c in customers if c.latitude and c.longitude]

        if not valid_customers:
            return {
                "routes": [],
                "message": "No customers with valid GPS coordinates"
            }

        # Build locations list with multi-depot support:
        # [tech0_start, tech1_start, ..., customer1, customer2, ...]
        locations = []
        start_indices = []
        end_indices = []

        # Add tech depots first
        for tech_idx, tech in enumerate(techs):
            # Add start depot
            locations.append((tech.start_latitude, tech.start_longitude))
            start_indices.append(tech_idx)

            # Check if end location is different from start
            if (tech.end_latitude != tech.start_latitude or
                tech.end_longitude != tech.start_longitude):
                # Add separate end depot
                locations.append((tech.end_latitude, tech.end_longitude))
                end_indices.append(len(locations) - 1)
            else:
                # End at same location as start
                end_indices.append(tech_idx)

        # Add customers after depots
        customer_start_idx = len(locations)
        customer_indices = {}  # Map customer to location index

        for customer in valid_customers:
            locations.append((customer.latitude, customer.longitude))
            customer_indices[customer.id] = len(locations) - 1

        # Get distance and time matrices from routing service
        import asyncio
        distance_matrix, time_matrix = asyncio.run(
            routing_service.get_distance_matrix(locations)
        )

        # Create routing model with per-vehicle start/end depots
        manager = pywrapcp.RoutingIndexManager(
            len(locations),
            len(techs),
            start_indices,
            end_indices
        )
        routing = pywrapcp.RoutingModel(manager)

        # Create distance callback
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Add time dimension with service duration
        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel_time = time_matrix[from_node][to_node]

            # Add service time if this is a customer node (not depot)
            service_time = 0
            if to_node >= customer_start_idx:  # Customer node
                customer_idx = to_node - customer_start_idx
                customer = valid_customers[customer_idx]
                service_time = customer.base_service_duration

            return travel_time + service_time

        time_callback_index = routing.RegisterTransitCallback(time_callback)

        # Set time dimension (8 hour workday = 480 minutes)
        routing.AddDimension(
            time_callback_index,
            60,  # Allow 60 minutes waiting time
            480,  # Maximum 8 hours per route
            False,  # Don't force start cumul to zero
            'Time'
        )

        # Set search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.time_limit.seconds = self.time_limit_seconds

        # Solve
        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            return {
                "routes": [],
                "message": "No solution found within time limit"
            }

        # Extract solution
        routes = []
        total_distance = 0
        total_duration = 0

        for vehicle_id in range(len(techs)):
            tech = techs[vehicle_id]
            route_customers = []
            route_distance = 0
            route_duration = 0

            index = routing.Start(vehicle_id)

            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)

                # Only process customer nodes, skip depot nodes
                if node_index >= customer_start_idx:
                    customer_idx = node_index - customer_start_idx
                    customer = valid_customers[customer_idx]
                    route_customers.append({
                        "customer_id": str(customer.id),
                        "customer_name": customer.name,
                        "address": customer.address,
                        "latitude": customer.latitude,
                        "longitude": customer.longitude,
                        "service_duration": customer.base_service_duration,
                        "sequence": len(route_customers) + 1
                    })

                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(
                    previous_index, index, vehicle_id
                )

            # Calculate route metrics
            route_distance_miles = route_distance / 1609.34

            # Sum up service times for duration
            for stop in route_customers:
                route_duration += stop["service_duration"]

            # Add driving time
            time_dimension = routing.GetDimensionOrDie('Time')
            time_var = time_dimension.CumulVar(routing.End(vehicle_id))
            route_duration = solution.Value(time_var)

            if route_customers:  # Only include routes with customers
                routes.append({
                    "driver_id": str(tech.id),
                    "driver_name": tech.name,
                    "driver_color": tech.color if hasattr(tech, 'color') else '#3498db',
                    "service_day": service_day or "multiple",
                    "start_location": {
                        "address": tech.start_location_address,
                        "latitude": tech.start_latitude,
                        "longitude": tech.start_longitude
                    },
                    "end_location": {
                        "address": tech.end_location_address,
                        "latitude": tech.end_latitude,
                        "longitude": tech.end_longitude
                    },
                    "stops": route_customers,
                    "total_customers": len(route_customers),
                    "total_distance_miles": round(route_distance_miles, 2),
                    "total_duration_minutes": route_duration
                })

                total_distance += route_distance_miles
                total_duration += route_duration

        return {
            "routes": routes,
            "summary": {
                "total_routes": len(routes),
                "total_customers": len(valid_customers),
                "total_distance_miles": round(total_distance, 2),
                "total_duration_minutes": total_duration,
                "optimization_time_seconds": self.time_limit_seconds
            }
        }


# Global optimization service instance
optimization_service = RouteOptimizationService()
