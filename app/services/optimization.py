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
        service_day: Optional[str] = None,
        optimization_speed: str = "quick"
    ) -> Dict:
        """
        Optimize routes in refine mode - keeps tech assignments, only optimizes order.

        Args:
            customers: List of customers (already filtered to have assigned techs)
            techs: List of available techs
            service_day: Specific day to optimize
            optimization_speed: 'quick' (30s) or 'thorough' (120s)

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
            distance_matrix, time_matrix = await routing_service.get_distance_matrix(locations)

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

            # Set search parameters based on optimization_speed
            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            )

            # Configure metaheuristic and time limit based on speed setting
            if optimization_speed == "thorough":
                search_parameters.local_search_metaheuristic = (
                    routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
                )
                time_limit_seconds = 120
            else:  # quick
                search_parameters.local_search_metaheuristic = (
                    routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC
                )
                time_limit_seconds = 30

            search_parameters.time_limit.seconds = time_limit_seconds

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
                            "customer_name": customer.display_name or customer.name or "Unknown",
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

    async def _optimize_with_day_reassignment(
        self,
        customers: List[Customer],
        techs: List[Tech],
        unlocked_customer_ids: Optional[List[str]],
        optimization_speed: str
    ) -> Dict:
        """
        Optimize routes with ability to reassign unlocked customers to different days.

        Args:
            customers: All customers
            techs: All techs
            unlocked_customer_ids: List of customer IDs that can be reassigned to different days
            optimization_speed: 'quick' or 'thorough'

        Returns:
            Dict with optimized routes across all days
        """
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
        unlocked_ids = set(unlocked_customer_ids or [])

        logger.info(f"Starting cross-day optimization with {len(customers)} customers, {len(techs)} techs, {len(unlocked_ids)} unlocked")

        # Build initial day assignments for all customers
        customer_day_assignments = {}
        multi_day_customers = {}

        for customer in customers:
            if customer.service_days_per_week == 1 and customer.service_day:
                # Single-day customer
                customer_day_assignments[customer.id] = [customer.service_day.lower()]
            elif customer.service_schedule:
                # Multi-day customer - store their pattern
                day_abbrev_to_full = {
                    'Mo': 'monday', 'Tu': 'tuesday', 'We': 'wednesday',
                    'Th': 'thursday', 'Fr': 'friday', 'Sa': 'saturday', 'Su': 'sunday'
                }
                assigned_days = [
                    day_abbrev_to_full[abbr]
                    for abbr in customer.service_schedule.split(',')
                    if abbr in day_abbrev_to_full
                ]
                customer_day_assignments[customer.id] = assigned_days
                multi_day_customers[customer.id] = {
                    'frequency': customer.service_days_per_week,
                    'original_days': assigned_days
                }
            else:
                logger.warning(f"Customer {customer.id} has no valid service_day or service_schedule")

        logger.info(f"Built day assignments for {len(customer_day_assignments)} customers ({len(multi_day_customers)} multi-day)")

        # Optimize with current assignments first to get baseline
        logger.info("Running initial optimization with current day assignments")
        initial_routes = await self._optimize_all_days_separately(
            customers, techs, days, customer_day_assignments, optimization_speed
        )

        logger.info(f"Initial optimization complete: {len(initial_routes.get('routes', []))} routes generated")

        if not unlocked_ids:
            # No customers to reassign, return initial optimization
            return initial_routes

        # Try to improve by reassigning unlocked customers
        logger.info(f"Attempting to reassign {len(unlocked_ids)} unlocked customers for better optimization")

        # Build day-by-day customer counts and workload
        day_workloads = {day: 0 for day in days}
        for customer in customers:
            if customer.id in customer_day_assignments:
                for day in customer_day_assignments[customer.id]:
                    day_workloads[day] += 1

        # For each unlocked customer, try moving to less busy days
        for customer in customers:
            if customer.id not in unlocked_ids:
                continue

            if customer.id in multi_day_customers:
                # Multi-day customer: try shifting entire schedule
                freq = multi_day_customers[customer.id]['frequency']
                current_days = customer_day_assignments[customer.id]

                # Try different day combinations with same frequency
                best_days = current_days
                min_workload_variance = self._calculate_workload_variance(
                    day_workloads, current_days, []
                )

                # Generate alternative schedules
                from itertools import combinations
                for new_days in combinations(days, freq):
                    new_days = list(new_days)
                    # Calculate what workload would be with this change
                    variance = self._calculate_workload_variance(
                        day_workloads, current_days, new_days
                    )
                    if variance < min_workload_variance:
                        min_workload_variance = variance
                        best_days = new_days

                # Update assignment if we found better days
                if best_days != current_days:
                    # Update workloads
                    for day in current_days:
                        day_workloads[day] -= 1
                    for day in best_days:
                        day_workloads[day] += 1
                    customer_day_assignments[customer.id] = best_days
                    logger.info(f"Reassigned multi-day customer {customer.display_name} from {current_days} to {best_days}")

            else:
                # Single-day customer: try moving to least busy compatible day
                current_day = customer_day_assignments[customer.id][0]
                min_workload = day_workloads[current_day]
                best_day = current_day

                for day in days:
                    if day_workloads[day] < min_workload:
                        min_workload = day_workloads[day]
                        best_day = day

                # Move to less busy day if found
                if best_day != current_day:
                    day_workloads[current_day] -= 1
                    day_workloads[best_day] += 1
                    customer_day_assignments[customer.id] = [best_day]
                    logger.info(f"Reassigned customer {customer.display_name} from {current_day} to {best_day}")

        # Re-optimize with new assignments
        logger.info("Re-optimizing with reassigned customers")
        final_routes = await self._optimize_all_days_separately(
            customers, techs, days, customer_day_assignments, optimization_speed
        )

        return final_routes

    def _calculate_workload_variance(
        self,
        day_workloads: Dict[str, int],
        old_days: List[str],
        new_days: List[str]
    ) -> float:
        """Calculate variance in workload distribution after a potential reassignment."""
        # Create copy of workloads
        test_workloads = dict(day_workloads)

        # Remove from old days
        for day in old_days:
            test_workloads[day] -= 1

        # Add to new days
        for day in new_days:
            test_workloads[day] += 1

        # Calculate variance
        values = list(test_workloads.values())
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance

    async def _optimize_all_days_separately(
        self,
        customers: List[Customer],
        techs: List[Tech],
        days: List[str],
        customer_day_assignments: Dict[str, List[str]],
        optimization_speed: str = "quick"
    ) -> Dict:
        """Optimize each day separately using the provided day assignments."""
        all_routes = []
        total_customers = 0
        total_distance = 0
        total_duration = 0

        for day in days:
            # Get customers assigned to this day
            day_customer_ids = [
                cust_id for cust_id, assigned_days in customer_day_assignments.items()
                if day in assigned_days
            ]

            day_customers = [c for c in customers if c.id in day_customer_ids]

            if not day_customers:
                continue

            logger.info(f"Optimizing {len(day_customers)} customers for {day}")

            day_result = await self._optimize_single_day(
                day_customers, techs, day, optimization_speed
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
                "optimization_mode": "cross_day_reassignment"
            }
        }

    async def optimize_routes(
        self,
        customers: List[Customer],
        techs: List[Tech],
        service_day: Optional[str] = None,
        allow_day_reassignment: bool = False,
        unlocked_customer_ids: Optional[set] = None,
        optimization_mode: str = "full",
        optimization_speed: str = "quick"
    ) -> Dict:
        """
        Optimize routes for given customers and techs.

        Args:
            customers: List of customers to route
            techs: List of available techs (will use efficiency_multiplier for capacity)
            service_day: Specific day to optimize (or None for all)
            allow_day_reassignment: If True, can move customers to different days
            unlocked_customer_ids: Set of customer IDs that can be reassigned to different days
            optimization_mode: 'refine' keeps tech assignments, 'full' allows reassignment
            optimization_speed: 'quick' (30s) or 'thorough' (120s)

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
                customers, techs, service_day, optimization_speed
            )

        # If no specific day selected, handle based on reassignment setting
        if not service_day:
            if allow_day_reassignment:
                # TRUE FULL OPTIMIZATION: Optimize all customers across all days with day reassignment
                logger.info("Running full cross-day optimization with day reassignment")
                return await self._optimize_with_day_reassignment(
                    customers, techs, unlocked_customer_ids, optimization_speed
                )
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
                        day_customers, techs, day, optimization_speed
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

        return await self._optimize_single_day(valid_customers, techs, service_day, optimization_speed)

    def _setup_multi_depot_locations(
        self,
        customers: List[Customer],
        techs: List[Tech]
    ) -> Tuple[List[Tuple[float, float]], List[int], List[int], Dict, int]:
        """
        Setup locations list with multi-depot support.

        Args:
            customers: List of customers with valid coordinates
            techs: List of techs

        Returns:
            Tuple of (locations, start_indices, end_indices, customer_indices, customer_start_idx)
        """
        locations = []
        start_indices = []
        end_indices = []

        # Add tech depots first
        for tech_idx, tech in enumerate(techs):
            # Add start depot
            locations.append((tech.start_latitude, tech.start_longitude))
            start_location_idx = len(locations) - 1
            start_indices.append(start_location_idx)

            # Check if end location is different from start
            if (tech.end_latitude != tech.start_latitude or
                tech.end_longitude != tech.start_longitude):
                # Add separate end depot
                locations.append((tech.end_latitude, tech.end_longitude))
                end_indices.append(len(locations) - 1)
            else:
                # End at same location as start
                end_indices.append(start_location_idx)

        # Add customers after depots
        customer_start_idx = len(locations)
        customer_indices = {}  # Map customer to location index

        for customer in customers:
            locations.append((customer.latitude, customer.longitude))
            customer_indices[customer.id] = len(locations) - 1

        # Log location setup for debugging
        logger.info(
            f"Multi-depot setup: {len(techs)} techs, {len(customers)} customers, "
            f"{len(locations)} total locations"
        )
        logger.info(f"Start indices: {start_indices}, End indices: {end_indices}, Customer start: {customer_start_idx}")

        return locations, start_indices, end_indices, customer_indices, customer_start_idx

    def _create_routing_model(
        self,
        manager: pywrapcp.RoutingIndexManager,
        distance_matrix: List[List[int]],
        time_matrix: List[List[int]],
        customers: List[Customer],
        techs: List[Tech],
        customer_start_idx: int,
        optimization_speed: str
    ) -> pywrapcp.RoutingModel:
        """
        Create and configure OR-Tools routing model.

        Args:
            manager: Routing index manager
            distance_matrix: Distance matrix in meters
            time_matrix: Time matrix in minutes
            customers: List of customers
            techs: List of techs
            customer_start_idx: Index where customer locations start
            optimization_speed: 'quick' or 'thorough'

        Returns:
            Configured routing model
        """
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
                customer = customers[customer_idx]
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

        # Add distance dimension for tracking only (no span cost)
        routing.AddDimension(
            transit_callback_index,
            0,  # No slack
            200000,  # Maximum 200km per route (approx 124 miles)
            True,  # Force start cumul to zero
            'Distance'
        )

        # Add time span cost to balance workload across techs
        # Higher coefficient prioritizes balanced workload over minimizing total distance
        # Quick: 5000 (maximum balance priority), Thorough: 4000 (maximum balance)
        time_dimension = routing.GetDimensionOrDie('Time')
        time_coeff = 5000 if optimization_speed == "quick" else 4000
        for vehicle_id in range(len(techs)):
            time_dimension.SetSpanCostCoefficientForVehicle(time_coeff, vehicle_id)

        # Add capacity dimension using efficiency_multiplier
        # Each customer has demand=1, each tech has capacity based on their efficiency
        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            # Customers have demand=1, depots have demand=0
            return 1 if from_node >= customer_start_idx else 0

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

        # Set per-vehicle capacities based on max_customers_per_day * efficiency_multiplier
        vehicle_capacities = []
        for tech in techs:
            effective_capacity = int(tech.max_customers_per_day * tech.efficiency_multiplier)
            vehicle_capacities.append(effective_capacity)
            logger.info(f"Tech {tech.name}: capacity={tech.max_customers_per_day} * efficiency={tech.efficiency_multiplier} = {effective_capacity} customers")

        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # No slack
            vehicle_capacities,  # Per-vehicle capacity limits
            True,  # Start cumul to zero
            'Capacity'
        )

        return routing

    def _configure_search_parameters(
        self,
        optimization_speed: str
    ) -> pywrapcp.DefaultRoutingSearchParameters:
        """
        Configure OR-Tools search parameters based on speed setting.

        Args:
            optimization_speed: 'quick' or 'thorough'

        Returns:
            Configured search parameters
        """
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        # Use PATH_CHEAPEST_ARC - good for distance minimization
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )

        # Configure metaheuristic and time limit based on speed setting
        if optimization_speed == "thorough":
            # Thorough mode: Use guided local search for better results (slower)
            search_parameters.local_search_metaheuristic = (
                routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            )
            time_limit_seconds = 120
        else:  # quick
            # Quick mode: Use automatic metaheuristic for faster results
            search_parameters.local_search_metaheuristic = (
                routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC
            )
            time_limit_seconds = 30

        search_parameters.time_limit.seconds = time_limit_seconds

        # Log optimization parameters
        logger.info(
            f"Optimization: {optimization_speed} mode, minimize distance (arc cost), "
            f"max time=480min/route, time_limit={time_limit_seconds}s"
        )

        return search_parameters

    def _extract_solution(
        self,
        solution: pywrapcp.Assignment,
        routing: pywrapcp.RoutingModel,
        manager: pywrapcp.RoutingIndexManager,
        techs: List[Tech],
        customers: List[Customer],
        customer_start_idx: int,
        service_day: Optional[str]
    ) -> Tuple[List[Dict], float, int]:
        """
        Extract routes from OR-Tools solution.

        Args:
            solution: OR-Tools solution
            routing: Routing model
            manager: Routing index manager
            techs: List of techs
            customers: List of customers
            customer_start_idx: Index where customer locations start
            service_day: Service day being optimized

        Returns:
            Tuple of (routes, total_distance, total_duration)
        """
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
                    customer = customers[customer_idx]
                    route_customers.append({
                        "customer_id": str(customer.id),
                        "customer_name": customer.display_name or customer.name or "Unknown",
                        "address": customer.address,
                        "latitude": customer.latitude,
                        "longitude": customer.longitude,
                        "service_duration": customer.base_service_duration,
                        "sequence": len(route_customers) + 1
                    })

                previous_index = index
                index = solution.Value(routing.NextVar(index))
                arc_distance = routing.GetArcCostForVehicle(
                    previous_index, index, vehicle_id
                )
                route_distance += arc_distance

            # Calculate route metrics
            route_distance_miles = route_distance / 1609.34

            logger.info(
                f"Route for {tech.name}: {len(route_customers)} stops, "
                f"total_distance={route_distance}m ({route_distance_miles:.1f}mi)"
            )

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

        return routes, total_distance, total_duration

    async def _optimize_single_day(
        self,
        customers: List[Customer],
        techs: List[Tech],
        service_day: Optional[str] = None,
        optimization_speed: str = "quick"
    ) -> Dict:
        """
        Optimize routes for a single day.

        Args:
            customers: List of customers to route (already filtered)
            techs: List of available techs
            service_day: Day being optimized
            optimization_speed: 'quick' (30s) or 'thorough' (120s)

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

        # Setup multi-depot locations
        locations, start_indices, end_indices, customer_indices, customer_start_idx = \
            self._setup_multi_depot_locations(valid_customers, techs)

        # Get distance and time matrices from routing service
        distance_matrix, time_matrix = await routing_service.get_distance_matrix(locations)

        # Debug: Log sample distances to verify units
        if len(distance_matrix) > 2:
            logger.info(f"Sample distances: depot0->depot1={distance_matrix[0][1]}m, depot0->customer0={distance_matrix[0][customer_start_idx]}m")
            if len(distance_matrix) > customer_start_idx + 1:
                logger.info(f"customer0->customer1={distance_matrix[customer_start_idx][customer_start_idx+1]}m")

        # Create routing model with per-vehicle start/end depots
        manager = pywrapcp.RoutingIndexManager(
            len(locations),
            len(techs),
            start_indices,
            end_indices
        )

        # Create and configure routing model
        routing = self._create_routing_model(
            manager,
            distance_matrix,
            time_matrix,
            valid_customers,
            techs,
            customer_start_idx,
            optimization_speed
        )

        # Configure search parameters
        search_parameters = self._configure_search_parameters(optimization_speed)

        # Solve
        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            return {
                "routes": [],
                "message": "No solution found within time limit"
            }

        # Extract solution
        routes, total_distance, total_duration = self._extract_solution(
            solution,
            routing,
            manager,
            techs,
            valid_customers,
            customer_start_idx,
            service_day
        )

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
