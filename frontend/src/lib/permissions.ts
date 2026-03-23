import { useDevMode } from "./dev-mode";
import { useAuth } from "./auth-context";

export type Role = "owner" | "admin" | "manager" | "technician" | "readonly";

export type FeatureSlug =
  | "core_operations"
  | "route_optimization"
  | "invoicing"
  | "profitability"
  | "satellite_analysis"
  | "emd_intelligence"
  | "chemical_costs"
  | "customer_portal";

export interface Permissions {
  role: Role;
  features: Set<string>;
  // Navigation
  canViewInvoices: boolean;
  canViewProfitability: boolean;
  canViewSatellite: boolean;
  canViewSettings: boolean;
  canViewRoutes: boolean;
  canViewEmd: boolean;
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

interface RolePermissions {
  canViewInvoices: boolean;
  canViewProfitability: boolean;
  canViewSatellite: boolean;
  canViewSettings: boolean;
  canViewRoutes: boolean;
  canViewEmd: boolean;
  canViewInbox: boolean;
  canViewTeam: boolean;
  canEditCustomers: boolean;
  canCreateCustomers: boolean;
  canDeleteCustomers: boolean;
  canViewRates: boolean;
  canViewBalance: boolean;
  canEditRates: boolean;
  canViewDimensions: boolean;
  canViewDifficulty: boolean;
  canManageRoutes: boolean;
  canManageTechs: boolean;
}

const ROLE_PERMISSIONS: Record<Role, RolePermissions> = {
  owner: {
    canViewInvoices: true,
    canViewProfitability: true,
    canViewSatellite: true,
    canViewSettings: true,
    canViewRoutes: true,
    canViewEmd: true,
    canViewInbox: true,
    canViewTeam: true,
    canEditCustomers: true,
    canCreateCustomers: true,
    canDeleteCustomers: true,
    canViewRates: true,
    canViewBalance: true,
    canEditRates: true,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: true,
    canManageTechs: true,
  },
  admin: {
    canViewInvoices: true,
    canViewProfitability: true,
    canViewSatellite: true,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewInbox: true,
    canViewTeam: true,
    canEditCustomers: true,
    canCreateCustomers: true,
    canDeleteCustomers: true,
    canViewRates: true,
    canViewBalance: true,
    canEditRates: true,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: true,
    canManageTechs: true,
  },
  manager: {
    canViewInvoices: false,
    canViewProfitability: false,
    canViewSatellite: true,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewInbox: false,
    canViewTeam: false,
    canEditCustomers: true,
    canCreateCustomers: true,
    canDeleteCustomers: true,
    canViewRates: false,
    canViewBalance: false,
    canEditRates: false,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: true,
    canManageTechs: false,
  },
  technician: {
    canViewInvoices: false,
    canViewProfitability: false,
    canViewSatellite: false,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewInbox: false,
    canViewTeam: false,
    canEditCustomers: false,
    canCreateCustomers: false,
    canDeleteCustomers: false,
    canViewRates: false,
    canViewBalance: false,
    canEditRates: false,
    canViewDimensions: false,
    canViewDifficulty: false,
    canManageRoutes: false,
    canManageTechs: false,
  },
  readonly: {
    canViewInvoices: true,
    canViewProfitability: true,
    canViewSatellite: true,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewInbox: false,
    canViewTeam: false,
    canEditCustomers: false,
    canCreateCustomers: false,
    canDeleteCustomers: false,
    canViewRates: true,
    canViewBalance: true,
    canEditRates: false,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: false,
    canManageTechs: false,
  },
};

/** Map from permission key to the feature slug that gates it */
const FEATURE_GATES: Partial<Record<keyof RolePermissions, FeatureSlug>> = {
  canViewInvoices: "invoicing",
  canViewProfitability: "profitability",
  canViewSatellite: "satellite_analysis",
  canViewRoutes: "route_optimization",
  canViewEmd: "emd_intelligence",
  canManageRoutes: "route_optimization",
};

export function getPermissionsForRole(role: Role, features: string[] = []): Permissions {
  const rolePerms = ROLE_PERMISSIONS[role] ?? ROLE_PERMISSIONS.readonly;
  const featureSet = new Set(features);
  const hasFeature = (slug: FeatureSlug) => featureSet.has(slug);

  // Merge: role AND feature must both allow it
  const merged: Record<string, boolean> = {};
  for (const [key, roleAllows] of Object.entries(rolePerms)) {
    const featureSlug = FEATURE_GATES[key as keyof RolePermissions];
    if (featureSlug) {
      merged[key] = roleAllows && featureSet.has(featureSlug);
    } else {
      merged[key] = roleAllows;
    }
  }

  return {
    role,
    features: featureSet,
    hasFeature,
    canViewChemicalCosts: (merged.canViewProfitability ?? false) && featureSet.has("chemical_costs"),
    ...merged,
  } as Permissions;
}

export function usePermissions(): Permissions {
  const { effectiveRole } = useDevMode();
  const { features } = useAuth();
  return getPermissionsForRole(effectiveRole, features);
}
