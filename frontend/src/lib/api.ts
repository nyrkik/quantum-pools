"use client";

export interface ApiError {
  error: string;
  message?: string;
}

/** Returns the backend base URL for direct API calls (bypassing Next.js proxy). */
export function getBackendOrigin(): string {
  if (typeof window === "undefined") return "http://localhost:7061";
  const host = window.location.hostname;
  // If accessed via tunnel domain, use api subdomain
  if (host.endsWith("quantumpoolspro.com")) {
    return `${window.location.protocol}//api.quantumpoolspro.com`;
  }
  // Local/Tailscale: use same host, port 7061
  return `${window.location.protocol}//${host}:7061`;
}

class ApiClient {
  private baseUrl: string;
  private refreshPromise: Promise<boolean> | null = null;
  private viewAsRole: string | null = null;
  private orgId: string | null = null;

  constructor(baseUrl = "/api") {
    this.baseUrl = baseUrl;
  }

  setViewAsRole(role: string | null) {
    this.viewAsRole = role;
  }

  setOrgId(orgId: string | null) {
    this.orgId = orgId;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };
    if (this.viewAsRole) {
      headers["X-View-As-Role"] = this.viewAsRole;
    }
    if (this.orgId) {
      headers["X-Organization-Id"] = this.orgId;
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

    if (response.status === 401) {
      // Try refresh
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        const retryResponse = await fetch(url, {
          ...options,
          headers,
          credentials: "include",
        });
        if (retryResponse.ok) {
          return retryResponse.json();
        }
      }
      throw { error: "unauthorized", message: "Session expired" } as ApiError;
    }

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw (body.detail || body) as ApiError;
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  private async tryRefresh(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise;

    this.refreshPromise = (async () => {
      try {
        const res = await fetch(`${this.baseUrl}/v1/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        return res.ok;
      } catch {
        return false;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "GET" });
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }

  async postDirect<T>(path: string, body?: unknown): Promise<T> {
    // POST directly to the backend, bypassing Next.js rewrite proxy
    const backendUrl = `${getBackendOrigin()}/api${path}`;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.viewAsRole) headers["X-View-As-Role"] = this.viewAsRole;
    const response = await fetch(backendUrl, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      headers,
      credentials: "include",
    });

    if (response.status === 401) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        const retryResponse = await fetch(backendUrl, {
          method: "POST",
          body: body ? JSON.stringify(body) : undefined,
          headers,
          credentials: "include",
        });
        if (retryResponse.ok) return retryResponse.json();
      }
      throw { error: "unauthorized", message: "Session expired" } as ApiError;
    }

    if (!response.ok) {
      const b = await response.json().catch(() => ({}));
      throw (b.detail || b) as ApiError;
    }
    return response.json();
  }

  async upload<T>(path: string, formData: FormData): Promise<T> {
    // Upload directly to the backend, bypassing Next.js rewrite proxy
    // which has body size limits that reject large photo uploads
    const backendUrl = `${getBackendOrigin()}/api${path}`;
    const uploadHeaders: Record<string, string> = {};
    if (this.viewAsRole) {
      uploadHeaders["X-View-As-Role"] = this.viewAsRole;
    }
    const response = await fetch(backendUrl, {
      method: "POST",
      body: formData,
      headers: uploadHeaders,
      credentials: "include",
    });

    if (response.status === 401) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        const retryResponse = await fetch(backendUrl, {
          method: "POST",
          body: formData,
          credentials: "include",
        });
        if (retryResponse.ok) return retryResponse.json();
      }
      throw { error: "unauthorized", message: "Session expired" } as ApiError;
    }

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw (body.detail || body) as ApiError;
    }

    return response.json();
  }
}

export const api = new ApiClient();
