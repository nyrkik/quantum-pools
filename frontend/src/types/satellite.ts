export interface SatelliteAnalysis {
  id: string;
  property_id: string;
  pool_detected: boolean;
  estimated_pool_sqft: number | null;
  pool_confidence: number;
  vegetation_pct: number;
  canopy_overhang_pct: number;
  hardscape_pct: number;
  shadow_pct: number;
  image_url: string | null;
  image_zoom: number;
  analysis_version: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface BulkAnalysisRequest {
  property_ids?: string[] | null;
  force_reanalyze?: boolean;
}

export interface BulkAnalysisResponse {
  total: number;
  analyzed: number;
  skipped: number;
  failed: number;
  results: SatelliteAnalysis[];
}
