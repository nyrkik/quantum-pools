import type { SatelliteAnalysis, PoolBowWithCoords } from "@/types/satellite";

export type StatusFilter = "analyzed" | "pinned" | "not_analyzed";
export type MapMode = "pools" | "routes" | "profitability";

export interface PortfolioMedians {
  rate_per_gallon: number | null;
  cost: number;
  margin_pct: number;
  difficulty: number;
}

export interface DimensionComparison {
  estimates: { id: string; source: string; estimated_sqft: number | null; perimeter_ft: number | null; notes: string | null; created_at: string }[];
  active_source: string | null;
  active_sqft: number | null;
  discrepancy_pct: number | null;
  discrepancy_level: string | null;
}

export const SOURCE_LABELS: Record<string, string> = {
  inspection: "Inspection",
  perimeter: "Perimeter",
  measurement: "Measured",
  satellite: "Satellite",
  manual: "Manual",
};

export const SOURCE_COLORS: Record<string, string> = {
  inspection: "bg-green-100 text-green-800",
  perimeter: "bg-green-100 text-green-800",
  measurement: "bg-blue-100 text-blue-800",
  satellite: "bg-yellow-100 text-yellow-800",
  manual: "bg-gray-100 text-gray-600",
};

export const POOL_SHAPES = [
  { value: "rectangle", label: "Rectangle" },
  { value: "irregular_rectangle", label: "Irregular Rectangle" },
  { value: "round", label: "Round" },
  { value: "oval", label: "Oval" },
  { value: "irregular_oval", label: "Irregular Oval" },
  { value: "kidney", label: "Kidney" },
  { value: "L-shape", label: "L-Shape" },
  { value: "freeform", label: "Freeform" },
];

export const MAP_MODES = [
  { key: "pools" as MapMode, label: "Pools" },
  { key: "routes" as MapMode, label: "Routes" },
  { key: "profitability" as MapMode, label: "Profitability" },
] as const;

export function getBowStatus(wf: PoolBowWithCoords, analysisMap: Map<string | null, SatelliteAnalysis>): StatusFilter {
  const a = analysisMap.get(wf.id);
  if (a?.pool_detected && wf.pool_lat) return "pinned";
  if (a?.pool_detected) return "analyzed";
  return "not_analyzed";
}

export function bestStatus(statuses: StatusFilter[]): StatusFilter {
  if (statuses.includes("pinned")) return "pinned";
  if (statuses.includes("analyzed")) return "analyzed";
  return "not_analyzed";
}

export const ALLOC_LABELS: Record<string, string> = { gallons: "vol", sqft: "area", service_time: "time", type_weight: "type", sole: "" };
