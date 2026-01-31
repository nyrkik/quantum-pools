"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { api } from "./api";

interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  created_at: string;
}

interface AuthState {
  user: User | null;
  organizationId: string;
  organizationName: string;
  role: string;
  isLoading: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

interface RegisterData {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  organization_name: string;
}

interface OrgUserResponse {
  user: User;
  organization_id: string;
  organization_name: string;
  role: string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    organizationId: "",
    organizationName: "",
    role: "",
    isLoading: true,
  });

  const setFromResponse = useCallback((data: OrgUserResponse) => {
    setState({
      user: data.user,
      organizationId: data.organization_id,
      organizationName: data.organization_name,
      role: data.role,
      isLoading: false,
    });
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const data = await api.get<OrgUserResponse>("/v1/auth/me");
      setFromResponse(data);
    } catch {
      setState((prev) => ({ ...prev, user: null, isLoading: false }));
    }
  }, [setFromResponse]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    const data = await api.post<OrgUserResponse>("/v1/auth/login", {
      email,
      password,
    });
    setFromResponse(data);
  };

  const register = async (data: RegisterData) => {
    const resp = await api.post<OrgUserResponse>("/v1/auth/register", data);
    setFromResponse(resp);
  };

  const logout = async () => {
    await api.post("/v1/auth/logout").catch(() => {});
    setState({
      user: null,
      organizationId: "",
      organizationName: "",
      role: "",
      isLoading: false,
    });
  };

  return (
    <AuthContext.Provider
      value={{ ...state, login, register, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
