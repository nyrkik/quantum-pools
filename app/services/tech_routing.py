"""
Single-tech route generation service.
Creates optimized stop sequences for individual techs using TSP (Traveling Salesman Problem).
"""

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from typing import List, Dict, Tuple
from datetime import datetime, date
from uuid import UUID
import logging

from app.models.customer import Customer
from app.models.tech import Tech
from app.models.tech_route import TechRoute
from app.services.routing import routing_service

logger = logging.getLogger(__name__)


class TechRoutingService:
    """Service for generating optimized routes for a single tech."""

    async def generate_route_for_tech(
        self,
        tech: Tech,
        customers: List[Customer],
        service_day: str,
        route_date: date,
        organization_id: UUID
    ) -> TechRoute:
        """
        Generate an optimized route for a single tech and their customers.

        Args:
            tech: Tech to route
            customers: List of customers assigned to this tech
            service_day: Day of week (monday, tuesday, etc.)
            route_date: Specific date for this route
            organization_id: Organization ID

        Returns:
            TechRoute object with optimized stop sequence
        """
        logger.info(f"Generating route for tech {tech.name} with {len(customers)} customers")

        if not customers:
            # No customers, return empty route
            return TechRoute(
                organization_id=organization_id,
                tech_id=tech.id,
                service_day=service_day,
                route_date=route_date,
                stop_sequence=[],
                total_distance=0.0,
                total_duration=0
            )

        if len(customers) == 1:
            # Only one customer, no optimization needed
            return TechRoute(
                organization_id=organization_id,
                tech_id=tech.id,
                service_day=service_day,
                route_date=route_date,
                stop_sequence=[str(customers[0].id)],
                total_distance=0.0,
                total_duration=customers[0].visit_duration
            )

        # Build locations list: [tech_start, customer1, customer2, ..., tech_end]
        locations = [(tech.start_latitude, tech.start_longitude)]
        customer_map = {}  # Map index to customer

        for idx, customer in enumerate(customers):
            if customer.latitude and customer.longitude:
                locations.append((customer.latitude, customer.longitude))
                customer_map[len(locations) - 1] = customer
            else:
                logger.warning(f"Customer {customer.id} has no coordinates, skipping from route")

        # Add tech end location
        locations.append((tech.end_latitude, tech.end_longitude))

        # Get distance and time matrices
        distance_matrix, time_matrix = await routing_service.get_distance_matrix(locations)

        # Solve TSP
        solution = self._solve_tsp(
            distance_matrix=distance_matrix,
            time_matrix=time_matrix,
            customer_map=customer_map,
            customers=customers
        )

        if not solution:
            logger.error(f"Failed to find solution for tech {tech.name}")
            # Return route with customers in original order as fallback
            return TechRoute(
                organization_id=organization_id,
                tech_id=tech.id,
                service_day=service_day,
                route_date=route_date,
                stop_sequence=[str(c.id) for c in customers],
                total_distance=0.0,
                total_duration=sum(c.visit_duration for c in customers)
            )

        # Create TechRoute from solution
        tech_route = TechRoute(
            organization_id=organization_id,
            tech_id=tech.id,
            service_day=service_day,
            route_date=route_date,
            stop_sequence=solution['stop_sequence'],
            total_distance=solution['total_distance'],
            total_duration=solution['total_duration']
        )

        logger.info(
            f"Route generated for {tech.name}: {len(solution['stop_sequence'])} stops, "
            f"{solution['total_distance']:.1f} miles, {solution['total_duration']} minutes"
        )

        return tech_route

    def _solve_tsp(
        self,
        distance_matrix: List[List[int]],
        time_matrix: List[List[int]],
        customer_map: Dict[int, Customer],
        customers: List[Customer]
    ) -> Dict:
        """
        Solve TSP for a single tech's route using OR-Tools.

        Args:
            distance_matrix: Matrix of distances in meters
            time_matrix: Matrix of travel times in minutes
            customer_map: Map of location index to customer object
            customers: List of all customers (for service durations)

        Returns:
            Dict with stop_sequence, total_distance, total_duration
        """
        num_locations = len(distance_matrix)

        # Create routing model
        manager = pywrapcp.RoutingIndexManager(num_locations, 1, [0], [num_locations - 1])
        routing = pywrapcp.RoutingModel(manager)

        # Distance callback
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Add time dimension for service durations
        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel_time = time_matrix[from_node][to_node]

            # Add service duration at from_node (if it's a customer)
            service_time = 0
            if from_node in customer_map:
                customer = customer_map[from_node]
                service_time = customer.visit_duration

            return travel_time + service_time

        time_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.AddDimension(
            time_callback_index,
            60,    # Allow up to 60 minutes slack
            600,   # Max 10 hours (in minutes)
            True,  # fix_start_cumul_to_zero
            'Time'
        )

        # Search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = 5  # Quick solve for single tech

        # Solve
        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            return None

        # Extract solution
        stop_sequence = []
        total_distance = 0
        total_duration = 0

        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)

            # Skip start and end depot nodes
            if node != 0 and node != num_locations - 1:
                if node in customer_map:
                    customer = customer_map[node]
                    stop_sequence.append(str(customer.id))
                    total_duration += customer.visit_duration

            next_index = solution.Value(routing.NextVar(index))
            if not routing.IsEnd(next_index):
                next_node = manager.IndexToNode(next_index)
                total_distance += distance_matrix[node][next_node]
                total_duration += time_matrix[node][next_node]

            index = next_index

        # Convert distance from meters to miles
        total_distance_miles = total_distance / 1609.34

        return {
            'stop_sequence': stop_sequence,
            'total_distance': total_distance_miles,
            'total_duration': total_duration
        }


# Global instance
tech_routing_service = TechRoutingService()
