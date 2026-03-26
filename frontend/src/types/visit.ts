export interface VisitCustomer {
  id: string;
  name: string;
  company?: string;
  phone?: string;
  email?: string;
}

export interface VisitProperty {
  id: string;
  address: string;
  city?: string;
  gate_code?: string;
  access_instructions?: string;
  dog_on_property?: boolean;
}

export interface VisitWaterFeature {
  id: string;
  name: string;
  water_type: string;
  pool_gallons?: number;
  pool_type?: string;
}

export interface VisitChecklistItem {
  id: string;
  name: string;
  category: string;
  completed: boolean;
  completed_at?: string;
  notes?: string;
}

export interface VisitReading {
  id: string;
  water_feature_id: string;
  ph?: number;
  free_chlorine?: number;
  total_chlorine?: number;
  alkalinity?: number;
  calcium_hardness?: number;
  cya?: number;
  phosphates?: number;
  salt?: number;
  water_temp?: number;
}

export interface VisitPhoto {
  id: string;
  photo_url: string;
  category: string;
  caption?: string;
  water_feature_id?: string;
}

export interface VisitCharge {
  id: string;
  description: string;
  amount: number;
  status: string;
}

export interface Visit {
  id: string;
  status: string;
  started_at: string;
  notes?: string;
  tech_id: string;
  property_id: string;
  customer_id: string;
}

export interface LastReadings {
  [waterFeatureId: string]: {
    ph?: number;
    free_chlorine?: number;
    total_chlorine?: number;
    alkalinity?: number;
    calcium_hardness?: number;
    cya?: number;
    phosphates?: number;
    salt?: number;
    water_temp?: number;
  };
}

export interface VisitContext {
  visit: Visit;
  customer: VisitCustomer;
  property: VisitProperty;
  water_features: VisitWaterFeature[];
  checklist: VisitChecklistItem[];
  readings: VisitReading[];
  last_readings: LastReadings;
  photos: VisitPhoto[];
  charges: VisitCharge[];
  elapsed_seconds: number;
}
