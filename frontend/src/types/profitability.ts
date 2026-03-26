export interface OrgCostSettings {
  id: string;
  organization_id: string;
  burdened_labor_rate: number;
  vehicle_cost_per_mile: number;
  chemical_cost_per_gallon: number;
  monthly_overhead: number;
  target_margin_pct: number;
  residential_overhead_per_account: number;
  commercial_overhead_per_account: number;
  avg_drive_minutes: number;
  avg_drive_miles: number;
  visits_per_month: number;
  semi_annual_discount_type: string;
  semi_annual_discount_value: number;
  annual_discount_type: string;
  annual_discount_value: number;
  default_parts_markup_pct: number;
  created_at: string;
  updated_at: string;
}

export interface OrgCostSettingsUpdate {
  burdened_labor_rate?: number;
  vehicle_cost_per_mile?: number;
  chemical_cost_per_gallon?: number;
  monthly_overhead?: number;
  target_margin_pct?: number;
  residential_overhead_per_account?: number;
  commercial_overhead_per_account?: number;
  avg_drive_minutes?: number;
  avg_drive_miles?: number;
  visits_per_month?: number;
  semi_annual_discount_type?: string;
  semi_annual_discount_value?: number;
  annual_discount_type?: string;
  annual_discount_value?: number;
  default_parts_markup_pct?: number;
}

export interface PropertyDifficulty {
  id: string;
  property_id: string;
  shallow_sqft: number | null;
  deep_sqft: number | null;
  has_deep_end: boolean;
  spa_sqft: number | null;
  diving_board_count: number;
  pump_flow_gpm: number | null;
  is_indoor: boolean;
  equipment_age_years: number | null;
  shade_exposure: string | null;
  tree_debris_level: string | null;
  enclosure_type: string | null;
  chem_feeder_type: string | null;
  access_difficulty_score: number;
  customer_demands_score: number;
  chemical_demand_score: number;
  callback_frequency_score: number;
  equipment_effectiveness: number;
  pool_design_score: number;
  override_composite: number | null;
  notes: string | null;
  composite_score: number;
  difficulty_multiplier: number;
  created_at: string;
  updated_at: string;
}

export interface PropertyDifficultyUpdate {
  shallow_sqft?: number | null;
  deep_sqft?: number | null;
  has_deep_end?: boolean;
  spa_sqft?: number | null;
  diving_board_count?: number;
  pump_flow_gpm?: number | null;
  is_indoor?: boolean;
  equipment_age_years?: number | null;
  shade_exposure?: string | null;
  tree_debris_level?: string | null;
  enclosure_type?: string | null;
  chem_feeder_type?: string | null;
  access_difficulty_score?: number;
  customer_demands_score?: number;
  chemical_demand_score?: number;
  callback_frequency_score?: number;
  equipment_effectiveness?: number;
  pool_design_score?: number;
  override_composite?: number | null;
  notes?: string | null;
}

export interface Jurisdiction {
  id: string;
  name: string;
  method_key: string;
  shallow_sqft_per_bather: number;
  deep_sqft_per_bather: number;
  spa_sqft_per_bather: number;
  depth_based: boolean;
  notes: string | null;
}

export interface BatherLoadRequest {
  pool_sqft?: number | null;
  pool_gallons?: number | null;
  shallow_sqft?: number | null;
  deep_sqft?: number | null;
  has_deep_end?: boolean;
  spa_sqft?: number | null;
  diving_board_count?: number;
  pump_flow_gpm?: number | null;
  is_indoor?: boolean;
  jurisdiction_id?: string | null;
}

export interface BatherLoadResult {
  max_bathers: number;
  pool_bathers: number;
  spa_bathers: number;
  diving_bathers: number;
  deck_bonus_bathers: number;
  flow_rate_bathers: number | null;
  jurisdiction_name: string;
  method_key: string;
  estimated_fields: string[];
  pool_sqft_used: number;
  shallow_sqft_used: number;
  deep_sqft_used: number;
}

export interface CostBreakdown {
  chemical_cost: number;
  labor_cost: number;
  travel_cost: number;
  overhead_cost: number;
  total_cost: number;
  revenue: number;
  profit: number;
  margin_pct: number;
  suggested_rate: number;
  rate_gap: number;
}

export interface WfCost {
  wf_id: string;
  wf_name: string | null;
  water_type: string;
  gallons: number;
  service_minutes: number;
  monthly_rate: number;
  chemical_cost: number;
  labor_cost: number;
  travel_cost: number;
  overhead_cost: number;
  total_cost: number;
  profit: number;
  margin_pct: number;
  suggested_rate: number;
  rate_gap: number;
  difficulty_score: number;
}

export interface ProfitabilityAccount {
  customer_id: string;
  customer_name: string;
  customer_type: string;
  property_id: string;
  property_address: string;
  monthly_rate: number;
  pool_gallons: number | null;
  pool_sqft: number | null;
  estimated_service_minutes: number;
  difficulty_score: number;
  difficulty_multiplier: number;
  cost_breakdown: CostBreakdown;
  margin_pct: number;
  rate_per_gallon: number | null;
  wf_costs: WfCost[];
}

export interface ProfitabilityOverview {
  total_accounts: number;
  total_revenue: number;
  total_cost: number;
  total_profit: number;
  avg_margin_pct: number;
  below_target_count: number;
  target_margin_pct: number;
  accounts: ProfitabilityAccount[];
}

export interface WhaleCurvePoint {
  rank: number;
  customer_name: string;
  customer_id: string;
  cumulative_profit_pct: number;
  individual_profit: number;
}

export interface PricingSuggestion {
  customer_id: string;
  customer_name: string;
  property_address: string;
  current_rate: number;
  suggested_rate: number;
  rate_gap: number;
  current_margin_pct: number;
  target_margin_pct: number;
  difficulty_score: number;
}
