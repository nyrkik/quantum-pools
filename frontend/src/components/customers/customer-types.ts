import type { PropertyPhoto } from "@/types/photo";

export interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  company_name: string | null;
  customer_type: string;
  email: string | null;
  phone: string | null;
  monthly_rate: number;
  balance: number;
  billing_address: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_zip: string | null;
  service_frequency: string | null;
  preferred_day: string | null;
  billing_frequency: string;
  payment_method: string | null;
  payment_terms_days: number;
  difficulty_rating: number;
  status: string;
  notes: string | null;
  is_active: boolean;
  property_count: number;
  created_at: string;
}

export interface WaterFeature {
  id: string;
  property_id: string;
  name: string | null;
  water_type: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  pool_surface: string | null;
  pool_length_ft: number | null;
  pool_width_ft: number | null;
  pool_depth_shallow: number | null;
  pool_depth_deep: number | null;
  pool_depth_avg: number | null;
  pool_shape: string | null;
  pool_volume_method: string | null;
  dimension_source: string | null;
  dimension_source_date: string | null;
  perimeter_ft: number | null;
  sanitizer_type: string | null;
  pump_type: string | null;
  filter_type: string | null;
  heater_type: string | null;
  chlorinator_type: string | null;
  automation_system: string | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
  notes: string | null;
  is_active: boolean;
}

export interface Property {
  id: string;
  customer_id: string;
  name: string | null;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  pool_surface: string | null;
  pool_length_ft: number | null;
  pool_width_ft: number | null;
  pool_depth_shallow: number | null;
  pool_depth_deep: number | null;
  pool_depth_avg: number | null;
  pool_shape: string | null;
  pool_volume_method: string | null;
  has_spa: boolean;
  has_water_feature: boolean;
  pump_type: string | null;
  filter_type: string | null;
  heater_type: string | null;
  chlorinator_type: string | null;
  automation_system: string | null;
  gate_code: string | null;
  access_instructions: string | null;
  dog_on_property: boolean;
  monthly_rate: number | null;
  estimated_service_minutes: number;
  is_locked_to_day: boolean;
  service_day_pattern: string | null;
  notes: string | null;
  is_active: boolean;
  water_features: WaterFeatureSummary[];
}

export interface WaterFeatureSummary {
  id: string;
  name: string | null;
  water_type: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  pool_surface: string | null;
  pool_length_ft: number | null;
  pool_width_ft: number | null;
  pool_depth_shallow: number | null;
  pool_depth_deep: number | null;
  pool_shape: string | null;
  sanitizer_type: string | null;
  pump_type: string | null;
  filter_type: string | null;
  heater_type: string | null;
  chlorinator_type: string | null;
  automation_system: string | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
  dimension_source?: string | null;
}

export interface EquipmentItem {
  id: string;
  water_feature_id: string;
  equipment_type: string;
  brand: string | null;
  model: string | null;
  part_number: string | null;
  system_group: string | null;
  serial_number: string | null;
  normalized_name: string | null;
  horsepower: number | null;
  notes: string | null;
  is_active: boolean;
  catalog_equipment_id: string | null;
  catalog_canonical_name: string | null;
}

export interface CatalogEntry {
  id: string;
  canonical_name: string;
  equipment_type: string;
  manufacturer: string | null;
  model_number: string | null;
  category: string | null;
  specs: Record<string, unknown> | null;
  aliases: string[];
  is_common: boolean;
  source: string;
  parts?: CatalogPart[];
}

export interface CatalogPart {
  id: string;
  name: string;
  brand: string | null;
  sku: string | null;
  category: string | null;
  description: string | null;
  product_url: string | null;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  subject: string | null;
  status: string;
  issue_date: string;
  total: number;
  balance: number;
}

export interface RateSplitData {
  total_rate: number;
  method: string | null;
  allocations: Array<{
    wf_id: string;
    wf_name: string | null;
    water_type: string;
    gallons: number | null;
    proposed_rate: number;
    current_rate: number | null;
  }>;
}

export type { PropertyPhoto };
