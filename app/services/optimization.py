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
from app.models.driver import Driver
from app.config import settings

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

    async def optimize_routes(
        self,
        customers: List[Customer],
        drivers: List[Driver],
        service_day: Optional[str] = None,
        allow_day_reassignment: bool = False
    ) -> Dict:
        """
        Optimize routes for given customers and drivers.

        Args:
            customers: List of customers to route
            drivers: List of available drivers
            service_day: Specific day to optimize (or None for all)
            allow_day_reassignment: If True, can move customers to different days

        Returns:
            Dict with optimized routes per driver
        """
        if not customers:
            return {"routes": [], "message": "No customers to optimize"}

        if not drivers:
            return {"routes": [], "message": "No drivers available"}

        # Filter customers by service day if specified
        if service_day and not allow_day_reassignment:
            customers = [c for c in customers if c.service_day.lower() == service_day.lower()]

        # Filter out customers without geocoded coordinates
        valid_customers = [c for c in customers if c.latitude and c.longitude]

        if not valid_customers:
            return {
                "routes": [],
                "message": "No customers with valid GPS coordinates"
            }

        logger.info(
            f"Optimizing routes for {len(valid_customers)} customers "
            f"and {len(drivers)} drivers"
        )

        # Build locations list: [depot, customer1, customer2, ..., customerN]
        # For simplicity, use first driver's start location as depot
        depot_location = (drivers[0].start_latitude, drivers[0].start_longitude)

        locations = [depot_location]  # Index 0 = depot
        customer_indices = {}  # Map customer to location index

        for idx, customer in enumerate(valid_customers, start=1):
            locations.append((customer.latitude, customer.longitude))
            customer_indices[customer.id] = idx

        # Create distance and time matrices
        distance_matrix = self._create_distance_matrix(locations)
        time_matrix = self._create_time_matrix(distance_matrix)

        # Create routing model
        manager = pywrapcp.RoutingIndexManager(
            len(locations),
            len(drivers),
            0  # Depot index
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

            # Add service time if not depot
            service_time = 0
            if to_node > 0:  # Not depot
                customer = valid_customers[to_node - 1]
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

        for vehicle_id in range(len(drivers)):
            driver = drivers[vehicle_id]
            route_customers = []
            route_distance = 0
            route_duration = 0

            index = routing.Start(vehicle_id)

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
                    "driver_id": str(driver.id),
                    "driver_name": driver.name,
                    "service_day": service_day or "multiple",
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
