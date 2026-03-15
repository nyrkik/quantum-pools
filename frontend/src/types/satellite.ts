export interface SatelliteAnalysis {
  id: string;
  property_id: string;
  body_of_water_id: string | null;
  pool_detected: boolean;
  estimated_pool_sqft: number | null;
  pool_confidence: number;
  vegetation_pct: number;
  canopy_overhang_pct: number;
  hardscape_pct: number;
  shadow_pct: number;
  pool_lat: number | null;
  pool_lng: number | null;
  image_url: string | null;
  image_zoom: number;
  analysis_version: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PoolBowWithCoords {
  id: string;
  property_id: string;
  bow_name: string | null;
  water_type: string;
  address: string;
  customer_name: string;
  customer_type: string;
  pool_sqft: number | null;
  lat: number | null;
  lng: number | null;
  pool_lat: number | null;
  pool_lng: number | null;
  has_analysis: boolean;
  tech_name: string | null;
  tech_color: string | null;
}

export interface BulkAnalysisRequest {
  bow_ids?: string[] | null;
  force_reanalyze?: boolean;
}

export interface BulkAnalysisResponse {
  total: number;
  analyzed: number;
  skipped: number;
  failed: number;
  results: SatelliteAnalysis[];
}
