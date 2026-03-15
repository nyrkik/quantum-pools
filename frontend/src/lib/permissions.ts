import { useDevMode } from "./dev-mode";

export type Role = "owner" | "admin" | "manager" | "technician" | "readonly";

export interface Permissions {
  role: Role;
  // Navigation
  canViewInvoices: boolean;
  canViewProfitability: boolean;
  canViewSatellite: boolean;
  canViewSettings: boolean;
  canViewRoutes: boolean;
  canViewEmd: boolean;
  canViewTeam: boolean;
  // Customer / Property
  canEditCustomers: boolean;
  canCreateCustomers: boolean;
  canDeleteCustomers: boolean;
  canViewRates: boolean;
  canViewBalance: boolean;
  canEditRates: boolean;
  // BOW / Measurement
  canMeasure: boolean;
  canViewDimensions: boolean;
  canViewDifficulty: boolean;
  // Route
  canManageRoutes: boolean;
  // Tech
  canManageTechs: boolean;
}

const ROLE_PERMISSIONS: Record<Role, Permissions> = {
  owner: {
    role: "owner",
    canViewInvoices: true,
    canViewProfitability: true,
    canViewSatellite: true,
    canViewSettings: true,
    canViewRoutes: true,
    canViewEmd: true,
    canViewTeam: true,
    canEditCustomers: true,
    canCreateCustomers: true,
    canDeleteCustomers: true,
    canViewRates: true,
    canViewBalance: true,
    canEditRates: true,
    canMeasure: true,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: true,
    canManageTechs: true,
  },
  admin: {
    role: "admin",
    canViewInvoices: true,
    canViewProfitability: true,
    canViewSatellite: true,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewTeam: true,
    canEditCustomers: true,
    canCreateCustomers: true,
    canDeleteCustomers: true,
    canViewRates: true,
    canViewBalance: true,
    canEditRates: true,
    canMeasure: true,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: true,
    canManageTechs: true,
  },
  manager: {
    role: "manager",
    canViewInvoices: false,
    canViewProfitability: false,
    canViewSatellite: true,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewTeam: false,
    canEditCustomers: true,
    canCreateCustomers: true,
    canDeleteCustomers: true,
    canViewRates: false,
    canViewBalance: false,
    canEditRates: false,
    canMeasure: true,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: true,
    canManageTechs: false,
  },
  technician: {
    role: "technician",
    canViewInvoices: false,
    canViewProfitability: false,
    canViewSatellite: false,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewTeam: false,
    canEditCustomers: false,
    canCreateCustomers: false,
    canDeleteCustomers: false,
    canViewRates: false,
    canViewBalance: false,
    canEditRates: false,
    canMeasure: false,
    canViewDimensions: false,
    canViewDifficulty: false,
    canManageRoutes: false,
    canManageTechs: false,
  },
  readonly: {
    role: "readonly",
    canViewInvoices: true,
    canViewProfitability: true,
    canViewSatellite: true,
    canViewSettings: false,
    canViewRoutes: true,
    canViewEmd: true,
    canViewTeam: false,
    canEditCustomers: false,
    canCreateCustomers: false,
    canDeleteCustomers: false,
    canViewRates: true,
    canViewBalance: true,
    canEditRates: false,
    canMeasure: false,
    canViewDimensions: true,
    canViewDifficulty: true,
    canManageRoutes: false,
    canManageTechs: false,
  },
};

export function getPermissionsForRole(role: Role): Permissions {
  return ROLE_PERMISSIONS[role] ?? ROLE_PERMISSIONS.readonly;
}

export function usePermissions(): Permissions {
  const { effectiveRole } = useDevMode();
  return getPermissionsForRole(effectiveRole);
}
