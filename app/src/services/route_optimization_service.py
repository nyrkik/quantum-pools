"""
Route optimization service using Google OR-Tools VRP solver.

Property-based routing: RouteStop references property_id.
Service duration = property.estimated_service_minutes + (difficulty_rating - 1) * 5
"""

import logging
import math
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes used by the optimizer (plain dicts from the caller)
# ---------------------------------------------------------------------------
# PropertyData: id, lat, lng, estimated_service_minutes, difficulty_rating,
#               customer_name, address, service_day_pattern, is_locked_to_day
# TechData:     id, first_name, last_name, color, start_lat, start_lng,
#               end_lat, end_lng, max_stops_per_day, efficiency_factor,
#               working_days
# ---------------------------------------------------------------------------


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Return Haversine distance in meters (int) between two lat/lng points."""
    R = 6_371_000  # Earth radius in meters
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return int(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _build_distance_matrix(locations: List[Tuple[float, float]]) -> List[List[int]]:
    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_meters(locations[i][0], locations[i][1], locations[j][0], locations[j][1])
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix


def _build_time_matrix(distance_matrix: List[List[int]], avg_speed_mph: float = 30.0) -> List[List[int]]:
    """Convert distance (meters) to travel time (minutes) at avg_speed_mph."""
    speed_mps = avg_speed_mph * 1609.34 / 3600  # mph -> m/s
    n = len(distance_matrix)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = max(1, int(distance_matrix[i][j] / speed_mps / 60))
    return matrix


def _service_duration(prop: dict) -> int:
    base = prop.get("estimated_service_minutes", 30)
    diff = prop.get("difficulty_rating", 1)
    return base + max(0, (diff - 1)) * 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def optimize_routes(
    properties: List[dict],
    techs: List[dict],
    mode: str = "full_per_day",
    service_day: Optional[str] = None,
    speed: str = "quick",
    avg_speed_mph: float = 30.0,
) -> dict:
    """
    Main entry point for route optimization.

    modes:
        refine          — keep tech assignments, reorder stops per tech
        full_per_day    — reassign properties among techs for a given day
        cross_day       — also allow moving unlocked properties between days

    Returns:
        {"routes": [...], "summary": {...}}
    """
    if not properties:
        return {"routes": [], "summary": _empty_summary(mode)}
    if not techs:
        return {"routes": [], "summary": _empty_summary(mode)}

    # Filter properties with valid coordinates
    valid_props = [p for p in properties if p.get("lat") and p.get("lng")]
    if not valid_props:
        return {"routes": [], "summary": _empty_summary(mode)}

    if mode == "refine":
        return _optimize_refine(valid_props, techs, speed, avg_speed_mph)
    elif mode == "cross_day":
        return _optimize_cross_day(valid_props, techs, speed, avg_speed_mph)
    else:
        # full_per_day
        return _optimize_full_day(valid_props, techs, service_day or "monday", speed, avg_speed_mph)


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _optimize_refine(
    properties: List[dict],
    techs: List[dict],
    speed: str,
    avg_speed_mph: float,
) -> dict:
    """Keep tech assignments, optimize stop order per tech (single-vehicle TSP each)."""
    all_routes = []
    total_dist = 0.0
    total_dur = 0
    total_stops = 0

    # Group properties by currently assigned tech
    # Caller should set "assigned_tech_id" on each property dict
    tech_map = {t["id"]: t for t in techs}
    by_tech: Dict[str, List[dict]] = {}
    for p in properties:
        tid = p.get("assigned_tech_id")
        if tid and tid in tech_map:
            by_tech.setdefault(tid, []).append(p)

    for tech_id, tech_props in by_tech.items():
        tech = tech_map[tech_id]
        result = _solve_single_tech(tech, tech_props, speed, avg_speed_mph)
        if result:
            all_routes.append(result)
            total_dist += result["total_distance_miles"]
            total_dur += result["total_duration_minutes"]
            total_stops += result["total_stops"]

    return {
        "routes": all_routes,
        "summary": {
            "total_routes": len(all_routes),
            "total_stops": total_stops,
            "total_distance_miles": round(total_dist, 2),
            "total_duration_minutes": total_dur,
            "optimization_mode": "refine",
        },
    }


def _optimize_full_day(
    properties: List[dict],
    techs: List[dict],
    service_day: str,
    speed: str,
    avg_speed_mph: float,
) -> dict:
    """Multi-vehicle VRP across all techs for a given day."""
    valid_techs = [t for t in techs if t.get("start_lat") and t.get("start_lng")]
    if not valid_techs:
        return {"routes": [], "summary": _empty_summary("full_per_day")}

    routes, summary = _solve_multi_vehicle(properties, valid_techs, service_day, speed, avg_speed_mph)
    return {"routes": routes, "summary": summary}


def _optimize_cross_day(
    properties: List[dict],
    techs: List[dict],
    speed: str,
    avg_speed_mph: float,
) -> dict:
    """Reassign unlocked properties across days for load balancing, then VRP each day."""
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

    # Separate locked vs unlocked
    locked = [p for p in properties if p.get("is_locked_to_day")]
    unlocked = [p for p in properties if not p.get("is_locked_to_day")]

    # Count workload per day from locked properties
    day_counts: Dict[str, int] = {d: 0 for d in days}
    for p in locked:
        pd = (p.get("service_day_pattern") or "").lower()
        if pd in day_counts:
            day_counts[pd] += 1

    # Assign unlocked to least-busy days
    for p in unlocked:
        least_day = min(days, key=lambda d: day_counts[d])
        p["service_day_pattern"] = least_day
        day_counts[least_day] += 1

    all_props = locked + unlocked
    all_routes = []
    total_dist = 0.0
    total_dur = 0
    total_stops = 0

    valid_techs = [t for t in techs if t.get("start_lat") and t.get("start_lng")]
    if not valid_techs:
        return {"routes": [], "summary": _empty_summary("cross_day")}

    for day in days:
        day_props = [p for p in all_props if (p.get("service_day_pattern") or "").lower() == day]
        if not day_props:
            continue
        routes, summary = _solve_multi_vehicle(day_props, valid_techs, day, speed, avg_speed_mph)
        all_routes.extend(routes)
        total_dist += summary.get("total_distance_miles", 0)
        total_dur += summary.get("total_duration_minutes", 0)
        total_stops += summary.get("total_stops", 0)

    return {
        "routes": all_routes,
        "summary": {
            "total_routes": len(all_routes),
            "total_stops": total_stops,
            "total_distance_miles": round(total_dist, 2),
            "total_duration_minutes": total_dur,
            "optimization_mode": "cross_day",
        },
    }


# ---------------------------------------------------------------------------
# OR-Tools solvers
# ---------------------------------------------------------------------------


def _solve_single_tech(
    tech: dict,
    properties: List[dict],
    speed: str,
    avg_speed_mph: float,
) -> Optional[dict]:
    """Solve TSP for a single tech — reorder stops only."""
    if not properties:
        return None

    # Locations: [depot, prop0, prop1, ...]
    depot = (tech["start_lat"], tech["start_lng"])
    locations = [depot] + [(p["lat"], p["lng"]) for p in properties]

    dist_matrix = _build_distance_matrix(locations)
    time_matrix = _build_time_matrix(dist_matrix, avg_speed_mph)

    end_lat = tech.get("end_lat") or tech["start_lat"]
    end_lng = tech.get("end_lng") or tech["start_lng"]
    same_depot = (abs(end_lat - tech["start_lat"]) < 1e-6 and abs(end_lng - tech["start_lng"]) < 1e-6)

    if same_depot:
        manager = pywrapcp.RoutingIndexManager(len(locations), 1, 0)
    else:
        # Add end depot
        locations.append((end_lat, end_lng))
        dist_matrix = _build_distance_matrix(locations)
        time_matrix = _build_time_matrix(dist_matrix, avg_speed_mph)
        manager = pywrapcp.RoutingIndexManager(len(locations), 1, [0], [len(locations) - 1])

    routing = pywrapcp.RoutingModel(manager)

    def dist_cb(from_idx, to_idx):
        return dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

    transit_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def time_cb(from_idx, to_idx):
        f, t = manager.IndexToNode(from_idx), manager.IndexToNode(to_idx)
        travel = time_matrix[f][t]
        svc = 0
        if 1 <= t <= len(properties):
            svc = _service_duration(properties[t - 1])
        return travel + svc

    time_idx = routing.RegisterTransitCallback(time_cb)
    routing.AddDimension(time_idx, 60, 480, False, "Time")

    params = _search_params(speed)
    solution = routing.SolveWithParameters(params)
    if not solution:
        return None

    return _extract_single_route(solution, routing, manager, tech, properties, dist_matrix, time_matrix)


def _solve_multi_vehicle(
    properties: List[dict],
    techs: List[dict],
    service_day: str,
    speed: str,
    avg_speed_mph: float,
) -> Tuple[List[dict], dict]:
    """Multi-vehicle VRP across all techs."""
    # Build locations: tech starts/ends first, then properties
    locations: List[Tuple[float, float]] = []
    start_indices: List[int] = []
    end_indices: List[int] = []

    for tech in techs:
        start_idx = len(locations)
        locations.append((tech["start_lat"], tech["start_lng"]))
        start_indices.append(start_idx)

        end_lat = tech.get("end_lat") or tech["start_lat"]
        end_lng = tech.get("end_lng") or tech["start_lng"]
        if abs(end_lat - tech["start_lat"]) < 1e-6 and abs(end_lng - tech["start_lng"]) < 1e-6:
            end_indices.append(start_idx)
        else:
            locations.append((end_lat, end_lng))
            end_indices.append(len(locations) - 1)

    prop_start = len(locations)
    for p in properties:
        locations.append((p["lat"], p["lng"]))

    dist_matrix = _build_distance_matrix(locations)
    time_matrix = _build_time_matrix(dist_matrix, avg_speed_mph)

    num_vehicles = len(techs)
    manager = pywrapcp.RoutingIndexManager(len(locations), num_vehicles, start_indices, end_indices)
    routing = pywrapcp.RoutingModel(manager)

    # Distance callback
    def dist_cb(from_idx, to_idx):
        return dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

    transit_idx = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Time callback (travel + service)
    def time_cb(from_idx, to_idx):
        f, t = manager.IndexToNode(from_idx), manager.IndexToNode(to_idx)
        travel = time_matrix[f][t]
        svc = 0
        if t >= prop_start:
            svc = _service_duration(properties[t - prop_start])
        return travel + svc

    time_idx = routing.RegisterTransitCallback(time_cb)
    routing.AddDimension(time_idx, 60, 480, False, "Time")

    # Distance dimension (max ~200km per route)
    routing.AddDimension(transit_idx, 0, 200_000, True, "Distance")

    # Workload balance via span cost
    time_dim = routing.GetDimensionOrDie("Time")
    for v in range(num_vehicles):
        time_dim.SetSpanCostCoefficientForVehicle(4500, v)

    # Capacity dimension
    def demand_cb(from_idx):
        node = manager.IndexToNode(from_idx)
        return 1 if node >= prop_start else 0

    demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    caps = [int(t.get("max_stops_per_day", 20) * t.get("efficiency_factor", 1.0)) for t in techs]
    routing.AddDimensionWithVehicleCapacity(demand_idx, 0, caps, True, "Capacity")

    params = _search_params(speed)
    solution = routing.SolveWithParameters(params)

    if not solution:
        logger.warning(f"No VRP solution found for {service_day}")
        return [], _empty_summary("full_per_day")

    return _extract_multi_routes(solution, routing, manager, techs, properties, prop_start, service_day, dist_matrix, time_matrix)


def _search_params(speed: str):
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    if speed == "thorough":
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.seconds = 120
    else:
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC
        params.time_limit.seconds = 30
    return params


# ---------------------------------------------------------------------------
# Solution extraction
# ---------------------------------------------------------------------------


def _extract_single_route(
    solution, routing, manager, tech: dict, properties: List[dict],
    dist_matrix: List[List[int]], time_matrix: List[List[int]],
) -> dict:
    stops = []
    total_dist = 0
    index = routing.Start(0)
    prev_node = manager.IndexToNode(index)

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if 1 <= node <= len(properties):
            prop = properties[node - 1]
            drive_dist = dist_matrix[prev_node][node] / 1609.34
            drive_time = time_matrix[prev_node][node]
            stops.append({
                "property_id": prop["id"],
                "property_address": prop.get("address", ""),
                "customer_name": prop.get("customer_name", ""),
                "lat": prop["lat"],
                "lng": prop["lng"],
                "sequence": len(stops) + 1,
                "estimated_service_duration": _service_duration(prop),
                "estimated_drive_time_from_previous": drive_time,
                "estimated_distance_from_previous": round(drive_dist, 2),
            })
            prev_node = node
        next_idx = solution.Value(routing.NextVar(index))
        arc = routing.GetArcCostForVehicle(index, next_idx, 0)
        total_dist += arc
        index = next_idx

    time_dim = routing.GetDimensionOrDie("Time")
    total_dur = solution.Value(time_dim.CumulVar(routing.End(0)))

    return {
        "tech_id": tech["id"],
        "tech_name": f"{tech['first_name']} {tech['last_name']}",
        "tech_color": tech.get("color", "#3B82F6"),
        "service_day": properties[0].get("service_day_pattern", ""),
        "stops": stops,
        "total_stops": len(stops),
        "total_distance_miles": round(total_dist / 1609.34, 2),
        "total_duration_minutes": total_dur,
    }


def _extract_multi_routes(
    solution, routing, manager, techs, properties, prop_start, service_day,
    dist_matrix, time_matrix,
) -> Tuple[List[dict], dict]:
    routes = []
    total_dist = 0.0
    total_dur = 0
    total_stops = 0

    for v in range(len(techs)):
        tech = techs[v]
        stops = []
        route_dist = 0
        index = routing.Start(v)
        prev_node = manager.IndexToNode(index)

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node >= prop_start:
                pi = node - prop_start
                prop = properties[pi]
                drive_dist = dist_matrix[prev_node][node] / 1609.34
                drive_time = time_matrix[prev_node][node]
                stops.append({
                    "property_id": prop["id"],
                    "property_address": prop.get("address", ""),
                    "customer_name": prop.get("customer_name", ""),
                    "lat": prop["lat"],
                    "lng": prop["lng"],
                    "sequence": len(stops) + 1,
                    "estimated_service_duration": _service_duration(prop),
                    "estimated_drive_time_from_previous": drive_time,
                    "estimated_distance_from_previous": round(drive_dist, 2),
                })
                prev_node = node

            next_idx = solution.Value(routing.NextVar(index))
            arc = routing.GetArcCostForVehicle(index, next_idx, v)
            route_dist += arc
            index = next_idx

        if not stops:
            continue

        time_dim = routing.GetDimensionOrDie("Time")
        route_dur = solution.Value(time_dim.CumulVar(routing.End(v)))

        route_dist_miles = round(route_dist / 1609.34, 2)
        routes.append({
            "tech_id": tech["id"],
            "tech_name": f"{tech['first_name']} {tech['last_name']}",
            "tech_color": tech.get("color", "#3B82F6"),
            "service_day": service_day,
            "stops": stops,
            "total_stops": len(stops),
            "total_distance_miles": route_dist_miles,
            "total_duration_minutes": route_dur,
        })
        total_dist += route_dist_miles
        total_dur += route_dur
        total_stops += len(stops)

    summary = {
        "total_routes": len(routes),
        "total_stops": total_stops,
        "total_distance_miles": round(total_dist, 2),
        "total_duration_minutes": total_dur,
        "optimization_mode": "full_per_day",
    }
    return routes, summary


def _empty_summary(mode: str) -> dict:
    return {
        "total_routes": 0,
        "total_stops": 0,
        "total_distance_miles": 0,
        "total_duration_minutes": 0,
        "optimization_mode": mode,
    }
