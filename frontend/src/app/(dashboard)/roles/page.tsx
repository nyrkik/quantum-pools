"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Shield, Loader2 } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { PresetTiers } from "@/components/roles/preset-tiers";
import { CustomRoles } from "@/components/roles/custom-roles";
import { TeamMatrix } from "@/components/roles/team-matrix";
import type { PermissionCatalog } from "@/components/roles/permission-editor";

export default function RolesPage() {
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCatalog = useCallback(async () => {
    try {
      const data = await api.get<PermissionCatalog>("/v1/permissions/catalog");
      setCatalog(data);
    } catch {
      toast.error("Failed to load permission catalog");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto space-y-8">
      <div className="flex items-center gap-3">
        <Shield className="h-6 w-6 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold">Roles & Permissions</h1>
          <p className="text-sm text-muted-foreground">
            Manage access levels, custom roles, and per-user permission overrides.
          </p>
        </div>
      </div>

      <PresetTiers catalog={catalog} />

      <Separator />

      <CustomRoles catalog={catalog} />

      <Separator />

      <TeamMatrix catalog={catalog} />
    </div>
  );
}
