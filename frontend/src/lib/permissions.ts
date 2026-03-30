import { useDevMode } from "./dev-mode";
import { useAuth } from "./auth-context";

export type Role = "owner" | "admin" | "manager" | "technician" | "readonly" | "custom";

export type FeatureSlug =
  | "core_operations"
  | "route_optimization"
  | "invoicing"
  | "profitability"
  | "satellite_analysis"
  | "inspection_intelligence"
  | "chemical_costs"
  | "customer_portal";

export type Scope = "own" | "team" | "all";

export interface Permissions {
  role: Role;
  features: Set<string>;
  /** Raw server permissions: slug -> scope */
  serverPerms: Record<string, string>;
  /** Check if user has a specific permission slug */
  can: (slug: string) => boolean;
  /** Get scope for a permission slug */
  scope: (slug: string) => Scope | null;

  // Navigation (backward compat — derived from server permissions)
  canViewInvoices: boolean;
  canViewProfitability: boolean;
  canViewSatellite: boolean;
  canViewSettings: boolean;
  canViewRoutes: boolean;
  canViewInspection: boolean;
  canViewInbox: boolean;
  canViewTeam: boolean;
  canViewChemicalCosts: boolean;
  // Customer / Property
  canEditCustomers: boolean;
  canCreateCustomers: boolean;
  canDeleteCustomers: boolean;
  canViewRates: boolean;
  canViewBalance: boolean;
  canEditRates: boolean;
  // WF
  canViewDimensions: boolean;
  canViewDifficulty: boolean;
  // Route
  canManageRoutes: boolean;
  // Tech
  canManageTechs: boolean;
  // Feature check helper
  hasFeature: (slug: FeatureSlug) => boolean;
}

/** Feature subscription gates — permission requires both server perm AND feature subscription */
const FEATURE_GATES: Record<string, FeatureSlug> = {
  "invoices.view": "invoicing",
  "invoices.create": "invoicing",
  "invoices.edit": "invoicing",
  "invoices.delete": "invoicing",
  "payments.view": "invoicing",
  "payments.create": "invoicing",
  "profitability.view": "profitability",
  "profitability.edit_settings": "profitability",
  "satellite.view": "satellite_analysis",
  "satellite.analyze": "satellite_analysis",
  "routes.view": "route_optimization",
  "routes.manage": "route_optimization",
  "inspection.view": "inspection_intelligence",
  "inspection.manage": "inspection_intelligence",
  "chemical_costs.view": "chemical_costs",
  "chemical_costs.edit": "chemical_costs",
};

/** Fallback role->permissions for when server hasn't returned permissions yet (initial load) */
const FALLBACK_ROLE_PERMS: Record<string, string[]> = {
  owner: ["*"],
  admin: [
    "customers.view", "customers.create", "customers.edit", "customers.delete",
    "customers.view_rates", "customers.edit_rates", "customers.view_balance",
    "properties.view", "properties.create", "properties.edit", "properties.delete",
    "properties.view_dimensions", "properties.view_difficulty",
    "water_features.view", "water_features.create", "water_features.edit", "water_features.delete", "water_features.measure",
    "routes.view", "routes.manage", "visits.view", "visits.create", "visits.edit", "visits.delete",
    "chemicals.view", "chemicals.create", "chemicals.edit",
    "invoices.view", "invoices.create", "invoices.edit", "invoices.delete",
    "payments.view", "payments.create",
    "techs.view", "techs.manage",
    "profitability.view", "profitability.edit_settings",
    "satellite.view", "satellite.analyze",
    "inspection.view", "inspection.manage", "chemical_costs.view", "chemical_costs.edit",
    "inbox.view", "inbox.manage", "jobs.view", "jobs.create", "jobs.edit", "jobs.manage",
    "team.view", "team.manage", "settings.view",
    "branding.view", "branding.edit", "billing.view",
    "notifications.view",
  ],
  manager: [
    "customers.view", "customers.create", "customers.edit", "customers.delete",
    "properties.view", "properties.create", "properties.edit", "properties.delete",
    "properties.view_dimensions", "properties.view_difficulty",
    "water_features.view", "water_features.create", "water_features.edit", "water_features.delete", "water_features.measure",
    "routes.view", "routes.manage", "visits.view", "visits.create", "visits.edit", "visits.delete",
    "chemicals.view", "chemicals.create", "chemicals.edit",
    "techs.view", "profitability.view",
    "satellite.view", "satellite.analyze",
    "inspection.view", "inspection.manage", "chemical_costs.view",
    "jobs.view", "jobs.create", "jobs.edit", "jobs.manage",
    "notifications.view",
  ],
  technician: [
    "customers.view", "properties.view", "water_features.view",
    "routes.view", "visits.view", "visits.create", "visits.edit",
    "chemicals.view", "chemicals.create", "chemicals.edit",
    "techs.view", "inspection.view",
    "jobs.view", "jobs.edit",
    "notifications.view",
  ],
  readonly: [
    "customers.view", "customers.view_rates", "customers.view_balance",
    "properties.view", "properties.view_dimensions", "properties.view_difficulty",
    "water_features.view", "routes.view", "visits.view", "chemicals.view",
    "invoices.view", "payments.view", "techs.view",
    "profitability.view", "satellite.view", "inspection.view", "chemical_costs.view",
    "jobs.view", "notifications.view",
  ],
};

function buildPermissions(
  role: Role,
  serverPerms: Record<string, string>,
  features: string[],
): Permissions {
  const featureSet = new Set(features);
  const hasFeature = (slug: FeatureSlug) => featureSet.has(slug);

  // Use server permissions if available, otherwise fall back to role-based
  let perms = serverPerms;
  if (Object.keys(perms).length === 0 && role !== "custom") {
    const fallback = FALLBACK_ROLE_PERMS[role] || [];
    perms = {};
    for (const slug of fallback) {
      perms[slug] = "all";
    }
  }

  const can = (slug: string): boolean => {
    // Wildcard for owner fallback
    if ("*" in perms) return true;
    if (!(slug in perms)) return false;
    // Check feature gate
    const gate = FEATURE_GATES[slug];
    if (gate && !featureSet.has(gate)) return false;
    return true;
  };

  const scope = (slug: string): Scope | null => {
    if ("*" in perms) return "all";
    return (perms[slug] as Scope) ?? null;
  };

  return {
    role,
    features: featureSet,
    serverPerms: perms,
    can,
    scope,
    hasFeature,

    // Backward compat properties — derived from granular permissions
    canViewInvoices: can("invoices.view"),
    canViewProfitability: can("profitability.view"),
    canViewSatellite: can("satellite.view"),
    canViewSettings: can("settings.view"),
    canViewRoutes: can("routes.view"),
    canViewInspection: can("inspection.view"),
    canViewInbox: can("inbox.view"),
    canViewTeam: can("team.view"),
    canViewChemicalCosts: can("chemical_costs.view"),
    canEditCustomers: can("customers.edit"),
    canCreateCustomers: can("customers.create"),
    canDeleteCustomers: can("customers.delete"),
    canViewRates: can("customers.view_rates"),
    canViewBalance: can("customers.view_balance"),
    canEditRates: can("customers.edit_rates"),
    canViewDimensions: can("properties.view_dimensions"),
    canViewDifficulty: can("properties.view_difficulty"),
    canManageRoutes: can("routes.manage"),
    canManageTechs: can("techs.manage"),
  };
}

export function getPermissionsForRole(role: Role, features: string[] = [], serverPerms: Record<string, string> = {}): Permissions {
  return buildPermissions(role, serverPerms, features);
}

export function usePermissions(): Permissions {
  const { effectiveRole } = useDevMode();
  const { features, permissions: serverPerms } = useAuth();
  return buildPermissions(effectiveRole as Role, serverPerms, features);
}
