export interface RouteStop {
  id: string;
  property_id: string;
  sequence: number;
  estimated_service_duration: number;
  estimated_drive_time_from_previous: number;
  estimated_distance_from_previous: number;
  property_address?: string;
  customer_name?: string;
  lat?: number;
  lng?: number;
}

export interface Route {
  id: string;
  tech_id: string;
  tech_name?: string;
  tech_color?: string;
  service_day: string;
  total_duration_minutes: number;
  total_distance_miles: number;
  total_stops: number;
  optimization_algorithm?: string;
  stops: RouteStop[];
  created_at: string;
  updated_at: string;
}

export interface OptimizationStop {
  property_id: string;
  property_address: string;
  customer_name: string;
  lat: number;
  lng: number;
  sequence: number;
  estimated_service_duration: number;
  estimated_drive_time_from_previous: number;
  estimated_distance_from_previous: number;
}

export interface OptimizationRoute {
  tech_id: string;
  tech_name: string;
  tech_color: string;
  service_day: string;
  stops: OptimizationStop[];
  total_stops: number;
  total_distance_miles: number;
  total_duration_minutes: number;
}

export interface OptimizationSummary {
  total_routes: number;
  total_stops: number;
  total_distance_miles: number;
  total_duration_minutes: number;
  optimization_mode: string;
}

export interface OptimizationResponse {
  routes: OptimizationRoute[];
  summary: OptimizationSummary;
}

export interface OptimizationRequest {
  mode: "refine" | "full_per_day" | "cross_day";
  speed: "quick" | "thorough";
  service_day?: string;
  tech_ids?: string[];
  avg_speed_mph?: number;
}

export interface PolylineResponse {
  polyline: [number, number][];
  distance_meters: number;
  duration_seconds: number;
}
