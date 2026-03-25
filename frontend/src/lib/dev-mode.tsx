"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { useAuth } from "./auth-context";
import { api } from "./api";
import type { Role } from "./permissions";

interface OrgOption {
  id: string;
  name: string;
}

interface DevModeState {
  /** User has is_developer flag in DB */
  isDeveloper: boolean;
  /** Dev mode activated this session */
  isActive: boolean;
  /** Currently simulated role (null = use real role) */
  viewAsRole: Role | null;
  /** The user's actual role */
  realRole: Role;
  /** Toggle dev mode on/off */
  toggle: () => void;
  /** Set the view-as role */
  setViewAs: (role: Role | null) => void;
  /** Effective role (viewAs if active, otherwise real) */
  effectiveRole: Role;
  /** Available orgs for switching */
  orgs: OrgOption[];
  /** Currently active org ID (null = default) */
  activeOrgId: string | null;
  /** Switch org */
  switchOrg: (orgId: string | null) => void;
}

const DevModeContext = createContext<DevModeState | undefined>(undefined);

export function DevModeProvider({ children }: { children: ReactNode }) {
  const { role, isDeveloper, refreshUser } = useAuth();
  const [isActive, setIsActive] = useState(false);
  const [viewAsRole, setViewAsRole] = useState<Role | null>(null);
  const [orgs, setOrgs] = useState<OrgOption[]>([]);
  const [activeOrgId, setActiveOrgId] = useState<string | null>(null);

  const realRole = (role || "readonly") as Role;

  // Load available orgs for dev users
  useEffect(() => {
    if (isDeveloper) {
      api.get<{ id: string; name: string }[]>("/v1/auth/my-orgs")
        .then(setOrgs)
        .catch(() => {});
    }
  }, [isDeveloper]);

  const toggle = useCallback(() => {
    setIsActive((prev) => {
      if (prev) {
        // Turning off — reset view-as
        setViewAsRole(null);
      }
      return !prev;
    });
  }, []);

  const setViewAs = useCallback((r: Role | null) => {
    setViewAsRole(r);
  }, []);

  const effectiveRole = isActive && viewAsRole ? viewAsRole : realRole;

  const switchOrg = useCallback((orgId: string | null) => {
    setActiveOrgId(orgId);
    api.setOrgId(orgId);
    // Refresh user to get new org context
    refreshUser();
  }, [refreshUser]);

  // Sync view-as role to API client
  useEffect(() => {
    if (isActive && viewAsRole && viewAsRole !== realRole) {
      api.setViewAsRole(viewAsRole);
    } else {
      api.setViewAsRole(null);
    }
  }, [isActive, viewAsRole, realRole]);

  return (
    <DevModeContext.Provider
      value={{
        isDeveloper,
        isActive,
        viewAsRole,
        realRole,
        toggle,
        setViewAs,
        effectiveRole,
        orgs,
        activeOrgId,
        switchOrg,
      }}
    >
      {children}
    </DevModeContext.Provider>
  );
}

export function useDevMode() {
  const ctx = useContext(DevModeContext);
  if (!ctx) throw new Error("useDevMode must be used within DevModeProvider");
  return ctx;
}
