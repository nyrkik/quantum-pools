export interface InspectionFacilityListItem {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  facility_id: string | null;
  facility_type: string | null;
  program_identifier: string | null;
  permit_id: string | null;
  matched_property_id: string | null;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  is_closed: boolean;
  closure_reasons: string[];
}

export interface Inspection {
  id: string;
  facility_id: string;
  inspection_id: string | null;
  inspection_date: string | null;
  inspection_type: string | null;
  inspector_name: string | null;
  program_identifier: string | null;
  permit_id: string | null;
  total_violations: number;
  major_violations: number;
  pool_capacity_gallons: number | null;
  flow_rate_gpm: number | null;
  pdf_path: string | null;
  report_notes: string | null;
  closure_status: string | null;
  closure_required: boolean;
  reinspection_required: boolean;
  water_chemistry: { free_chlorine?: number; combined_chlorine?: number; ph?: number; cyanuric_acid_ppm?: number } | null;
  has_pdf: boolean;
  created_at: string;
  violations?: InspectionViolation[];
}

export interface InspectionViolation {
  id: string;
  violation_code: string | null;
  violation_title: string | null;
  observations: string | null;
  is_major_violation: boolean;
  severity_level: string | null;
  shorthand_summary: string | null;
}

export interface InspectionEquipment {
  id: string;
  pool_capacity_gallons: number | null;
  flow_rate_gpm: number | null;
  filter_pump_1_make: string | null;
  filter_pump_1_model: string | null;
  filter_pump_1_hp: string | null;
  filter_pump_2_make: string | null;
  filter_pump_2_model: string | null;
  filter_pump_2_hp: string | null;
  filter_pump_3_make: string | null;
  filter_pump_3_model: string | null;
  filter_pump_3_hp: string | null;
  jet_pump_1_make: string | null;
  jet_pump_1_model: string | null;
  jet_pump_1_hp: string | null;
  filter_1_type: string | null;
  filter_1_make: string | null;
  filter_1_model: string | null;
  filter_1_capacity_gpm: number | null;
  sanitizer_1_type: string | null;
  sanitizer_1_details: string | null;
  sanitizer_2_type: string | null;
  sanitizer_2_details: string | null;
  main_drain_type: string | null;
  main_drain_model: string | null;
  main_drain_install_date: string | null;
  equalizer_model: string | null;
  equalizer_install_date: string | null;
  pump_notes: string | null;
  filter_notes: string | null;
  sanitizer_notes: string | null;
  main_drain_notes: string | null;
  equalizer_notes: string | null;
}

export interface InspectionProgram {
  permit_id: string | null;
  program_identifier: string;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  is_closed: boolean;
}

export interface InspectionFacilityDetail {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  state: string;
  zip_code: string | null;
  phone: string | null;
  facility_id: string | null;
  permit_holder: string | null;
  facility_type: string | null;
  matched_property_id: string | null;
  matched_at: string | null;
  inspections: Inspection[];
  programs: InspectionProgram[];
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  matched_property_address: string | null;
  matched_customer_name: string | null;
  matched_customer_id?: string | null;
  matched_wf_names?: Record<string, string>;
}

export interface DashboardData {
  my_inspections_this_week: {
    facility_name: string;
    facility_id: string;
    inspection_date: string | null;
    total_violations: number;
    major_violations: number;
    closure_required: boolean;
    is_matched: boolean;
  }[];
  season_alerts: {
    facility_name: string;
    facility_id: string;
    alert_type: string;
    description: string;
    last_inspection_date: string | null;
  }[];
  fresh_leads: {
    facility_name: string;
    facility_id: string;
    address: string;
    inspection_date: string | null;
    total_violations: number;
    closure_required: boolean;
  }[];
  trending_worse: {
    facility_name: string;
    facility_id: string;
    recent_violations: number;
    previous_violations: number;
    trend: string;
  }[];
}

export type FacilityStatus = "compliant" | "violations" | "reinspection" | "closure";

export type DashboardTile = "inspections" | "alerts" | "leads" | "trending" | null;

export interface InspectionLookup {
  id: string;
  facility_id: string;
  facility_name: string;
  city: string | null;
  purchased_at: string;
  expires_at: string;
  days_remaining: number;
}

export interface SearchResult extends InspectionFacilityListItem {
  redacted?: boolean;
  has_lookup?: boolean;
}

export interface RedactedDetail {
  id: string;
  name: string;
  city: string | null;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  unlock_price_cents: number;
}

export interface ScraperHealth {
  state?: string;
  last_success?: string;
  last_error?: string;
  consecutive_failures?: number;
  total_scrapes?: number;
}
