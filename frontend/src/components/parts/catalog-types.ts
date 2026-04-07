import {
  Package,
  Filter,
  Cog,
  Flame,
  Droplets,
  Cpu,
  Wrench,
  Beaker,
  CircleDot,
  Settings2,
  Box,
  Clock,
} from "lucide-react";

// --- Types ---

export type CatalogType = "equipment" | "parts" | "chemicals" | "services";

export interface CatalogPart {
  id: string;
  sku: string;
  name: string;
  brand: string | null;
  category: string | null;
  subcategory: string | null;
  description: string | null;
  image_url: string | null;
  product_url: string | null;
  is_chemical: boolean;
  for_equipment_id?: string | null;
}

export interface EquipmentEntry {
  id: string;
  canonical_name: string;
  equipment_type: string;
  manufacturer: string | null;
  model_number: string | null;
  category: string | null;
  image_url: string | null;
  specs: Record<string, unknown> | null;
  parts?: CatalogPart[];
}

export interface ServiceItem {
  id: string;
  name: string;
  default_amount: number;
  category: string;
  is_taxable: boolean;
}

export interface Vendor {
  id: string;
  name: string;
  provider_type: string;
  search_url_template: string | null;
}

// --- Constants ---

export const CATEGORY_ICONS: Record<string, React.ElementType> = {
  "Pumps & Motors": Cog, "Filters & Media": Filter, "Heaters": Flame,
  "Water Treatment": Droplets, "Cleaners & Sweeps": Wrench,
  "Plumbing & Fittings": Settings2, "Automation & Electrical": Cpu,
  "Seals & O-Rings": CircleDot, "Safety & Compliance": Box,
  "Chemicals": Beaker,
  "time": Clock, "chemical": Beaker, "material": Package, "other": Box,
};

export const EQUIP_TYPE_ICONS: Record<string, React.ElementType> = {
  pump: Cog, filter: Filter, heater: Flame, chlorinator: Droplets,
  automation: Cpu, booster_pump: Cog, jet_pump: Cog, chemical_feeder: Droplets, equipment: Box,
};

export const EQUIP_TYPE_LABELS: Record<string, string> = {
  pump: "Pumps", filter: "Filters", heater: "Heaters", chlorinator: "Chlorinators",
  automation: "Automation", booster_pump: "Booster Pumps", jet_pump: "Jet Pumps",
  chemical_feeder: "Chemical Feeders", equipment: "Other Equipment",
};

export const PARTS_ORDER = [
  "Pumps & Motors", "Filters & Media", "Heaters", "Water Treatment",
  "Cleaners & Sweeps", "Plumbing & Fittings", "Automation & Electrical",
  "Seals & O-Rings", "Safety & Compliance",
];

export const EQUIP_ORDER = ["pump", "filter", "heater", "chlorinator", "automation", "booster_pump", "jet_pump", "chemical_feeder", "equipment"];

export const SERVICE_CATEGORY_LABELS: Record<string, string> = {
  time: "Labor & Time", chemical: "Chemical Service", material: "Materials", other: "Other",
};

export function getCategoryIcon(cat: string) {
  return CATEGORY_ICONS[cat] || Package;
}
