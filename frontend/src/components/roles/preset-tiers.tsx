"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Loader2, ChevronDown, ChevronUp, ShieldCheck } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PermissionEditor, type PermissionCatalog } from "./permission-editor";

interface PresetPermission {
  slug: string;
  scope: string;
}

interface Preset {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  is_system: boolean;
  sort_order: number;
  permissions: PresetPermission[];
}

const TIER_COLORS: Record<string, string> = {
  owner: "bg-violet-100 border-violet-300 dark:bg-violet-950/40 dark:border-violet-700",
  admin: "bg-blue-100 border-blue-300 dark:bg-blue-950/40 dark:border-blue-700",
  manager: "bg-emerald-100 border-emerald-300 dark:bg-emerald-950/40 dark:border-emerald-700",
  technician: "bg-amber-100 border-amber-300 dark:bg-amber-950/40 dark:border-amber-700",
  readonly: "bg-slate-100 border-slate-300 dark:bg-slate-800 dark:border-slate-600",
};

const TIER_TEXT: Record<string, string> = {
  owner: "text-violet-700 dark:text-violet-300",
  admin: "text-blue-700 dark:text-blue-300",
  manager: "text-emerald-700 dark:text-emerald-300",
  technician: "text-amber-700 dark:text-amber-300",
  readonly: "text-slate-700 dark:text-slate-300",
};

const TIER_LABELS: Record<string, string> = {
  owner: "Full Access",
  admin: "Admin",
  manager: "Standard",
  technician: "Limited",
  readonly: "View Only",
};

interface PresetTiersProps {
  catalog: PermissionCatalog | null;
}

export function PresetTiers({ catalog }: PresetTiersProps) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchPresets = useCallback(async () => {
    try {
      const data = await api.get<Preset[]>("/v1/permissions/presets");
      setPresets(data);
    } catch {
      toast.error("Failed to load permission presets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold">Permission Levels</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Built-in tiers define the base permissions for each role. Click a tier to see what it includes.
      </p>

      {/* Tier cards grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {presets.map((preset) => {
          const isExpanded = expanded === preset.slug;
          const colorClass = TIER_COLORS[preset.slug] || TIER_COLORS.readonly;
          const textClass = TIER_TEXT[preset.slug] || TIER_TEXT.readonly;
          const label = TIER_LABELS[preset.slug] || preset.name;

          return (
            <button
              key={preset.id}
              onClick={() => setExpanded(isExpanded ? null : preset.slug)}
              className={cn(
                "rounded-lg border-2 p-4 text-center transition-all",
                colorClass,
                isExpanded && "ring-2 ring-primary ring-offset-2",
                "hover:shadow-md cursor-pointer"
              )}
            >
              <div className={cn("text-sm font-semibold", textClass)}>{label}</div>
              <div className={cn("text-2xl font-bold mt-1", textClass)}>
                {preset.permissions.length}
              </div>
              <div className="text-xs text-muted-foreground mt-1">permissions</div>
              {isExpanded ? (
                <ChevronUp className="h-3.5 w-3.5 mx-auto mt-2 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 mx-auto mt-2 text-muted-foreground" />
              )}
            </button>
          );
        })}
      </div>

      {/* Expanded permission list */}
      {expanded && catalog && (
        <Card className="shadow-sm">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-4">
              <Badge variant="secondary">
                {TIER_LABELS[expanded] || expanded}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {presets.find((p) => p.slug === expanded)?.permissions.length} permissions
              </span>
            </div>
            <PermissionEditor
              catalog={catalog}
              selected={new Set(
                presets.find((p) => p.slug === expanded)?.permissions.map((p) => p.slug) || []
              )}
              onChange={() => {}}
              readOnly
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
