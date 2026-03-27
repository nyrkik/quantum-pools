"use client";

import { useMemo } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface PermissionCatalogItem {
  slug: string;
  action: string;
  description: string | null;
}

export interface PermissionCatalog {
  resources: Record<string, PermissionCatalogItem[]>;
}

interface PermissionEditorProps {
  catalog: PermissionCatalog;
  /** Currently selected permission slugs */
  selected: Set<string>;
  /** Callback when selections change */
  onChange: (slugs: Set<string>) => void;
  /** Base permissions (from preset) shown as grayed out when in override mode */
  basePermissions?: Set<string>;
  /** Override mode: shows added (green) and revoked (red) indicators */
  overrideMode?: boolean;
  /** Read-only mode */
  readOnly?: boolean;
}

const RESOURCE_LABELS: Record<string, string> = {
  customers: "Customers",
  properties: "Properties",
  water_features: "Water Features",
  routes: "Routes",
  visits: "Visits",
  chemicals: "Chemical Readings",
  invoices: "Invoices",
  payments: "Payments",
  techs: "Technicians",
  profitability: "Profitability",
  satellite: "Satellite Analysis",
  emd: "EMD Intelligence",
  chemical_costs: "Chemical Costs",
  inbox: "Inbox",
  jobs: "Jobs",
  team: "Team",
  settings: "Settings",
  branding: "Branding",
  billing: "Billing",
  notifications: "Notifications",
};

const ACTION_LABELS: Record<string, string> = {
  view: "View",
  create: "Create",
  edit: "Edit",
  delete: "Delete",
  manage: "Manage",
  view_rates: "View Rates",
  edit_rates: "Edit Rates",
  view_balance: "View Balance",
  view_dimensions: "View Dimensions",
  view_difficulty: "View Difficulty",
  measure: "Measure",
  edit_settings: "Edit Settings",
  analyze: "Analyze",
};

export function PermissionEditor({
  catalog,
  selected,
  onChange,
  basePermissions,
  overrideMode = false,
  readOnly = false,
}: PermissionEditorProps) {
  const resourceOrder = useMemo(() => Object.keys(catalog.resources), [catalog]);

  const togglePermission = (slug: string) => {
    if (readOnly) return;
    const next = new Set(selected);
    if (next.has(slug)) {
      next.delete(slug);
    } else {
      next.add(slug);
    }
    onChange(next);
  };

  const toggleResource = (resource: string) => {
    if (readOnly) return;
    const perms = catalog.resources[resource];
    const slugs = perms.map((p) => p.slug);
    const allSelected = slugs.every((s) => selected.has(s));
    const next = new Set(selected);
    if (allSelected) {
      slugs.forEach((s) => next.delete(s));
    } else {
      slugs.forEach((s) => next.add(s));
    }
    onChange(next);
  };

  return (
    <div className="space-y-4">
      {resourceOrder.map((resource) => {
        const perms = catalog.resources[resource];
        const slugs = perms.map((p) => p.slug);
        const selectedCount = slugs.filter((s) => selected.has(s)).length;
        const allSelected = selectedCount === slugs.length;
        const someSelected = selectedCount > 0 && !allSelected;

        return (
          <div key={resource} className="rounded-lg border">
            <div className="flex items-center gap-3 px-4 py-2.5 bg-slate-100 dark:bg-slate-800 rounded-t-lg">
              {!readOnly && (
                <Checkbox
                  checked={allSelected ? true : someSelected ? "indeterminate" : false}
                  onCheckedChange={() => toggleResource(resource)}
                />
              )}
              <span className="text-xs font-medium uppercase tracking-wide">
                {RESOURCE_LABELS[resource] || resource}
              </span>
              <Badge variant="secondary" className="ml-auto text-[10px]">
                {selectedCount}/{slugs.length}
              </Badge>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-0.5 p-2">
              {perms.map((perm) => {
                const isSelected = selected.has(perm.slug);
                const isBase = basePermissions?.has(perm.slug) ?? false;
                const isAdded = overrideMode && isSelected && !isBase;
                const isRevoked = overrideMode && !isSelected && isBase;

                return (
                  <label
                    key={perm.slug}
                    className={cn(
                      "flex items-center gap-2 rounded px-2.5 py-1.5 text-sm transition-colors cursor-pointer",
                      readOnly && "cursor-default",
                      isAdded && "bg-green-50 dark:bg-green-950/30",
                      isRevoked && "bg-red-50 dark:bg-red-950/30",
                      !isAdded && !isRevoked && "hover:bg-muted/50"
                    )}
                  >
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => togglePermission(perm.slug)}
                      disabled={readOnly}
                    />
                    <span
                      className={cn(
                        "text-sm",
                        isAdded && "text-green-700 dark:text-green-400 font-medium",
                        isRevoked && "text-red-500 dark:text-red-400 line-through",
                        !isAdded && !isRevoked && "text-foreground"
                      )}
                    >
                      {ACTION_LABELS[perm.action] || perm.action}
                    </span>
                    {isAdded && (
                      <Badge variant="outline" className="ml-auto text-[9px] border-green-400 text-green-600 px-1 py-0">
                        added
                      </Badge>
                    )}
                    {isRevoked && (
                      <Badge variant="outline" className="ml-auto text-[9px] border-red-400 text-red-500 px-1 py-0">
                        revoked
                      </Badge>
                    )}
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
