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
}

const DevModeContext = createContext<DevModeState | undefined>(undefined);

export function DevModeProvider({ children }: { children: ReactNode }) {
  const { role, isDeveloper } = useAuth();
  const [isActive, setIsActive] = useState(false);
  const [viewAsRole, setViewAsRole] = useState<Role | null>(null);

  const realRole = (role || "readonly") as Role;

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
