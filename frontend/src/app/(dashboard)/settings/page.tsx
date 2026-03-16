"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface RegionalDefault {
  id: string;
  region_key: string;
  sanitizer_type: string;
  sanitizer_price_per_unit: number | null;
  sanitizer_unit: string | null;
  acid_price_per_gallon: number;
  cya_price_per_lb: number;
  salt_price_per_bag: number;
}

interface OrgChemicalPrices {
  id: string;
  organization_id: string;
  liquid_chlorine_per_gal: number | null;
  tabs_per_bucket: number | null;
  cal_hypo_per_lb: number | null;
  dichlor_per_lb: number | null;
  salt_per_bag: number | null;
  acid_per_gal: number | null;
  cya_per_lb: number | null;
  bromine_per_lb: number | null;
  updated_at: string;
}

// Maps chemical row key to the OrgChemicalPrices field
interface ChemicalRow {
  key: keyof Omit<OrgChemicalPrices, "id" | "organization_id" | "updated_at">;
  label: string;
  unit: string;
  defaultKey: string; // how to find default price from regional defaults
}

const CHEMICAL_ROWS: ChemicalRow[] = [
  { key: "liquid_chlorine_per_gal", label: "Liquid Chlorine", unit: "/gal", defaultKey: "liquid" },
  { key: "acid_per_gal", label: "Muriatic Acid", unit: "/gal", defaultKey: "acid" },
  { key: "tabs_per_bucket", label: "Trichlor Tabs", unit: "/50lb bucket", defaultKey: "tabs" },
  { key: "cya_per_lb", label: "CYA (Stabilizer)", unit: "/lb", defaultKey: "cya" },
  { key: "salt_per_bag", label: "Salt", unit: "/40lb bag", defaultKey: "salt" },
  { key: "cal_hypo_per_lb", label: "Cal-Hypo", unit: "/lb", defaultKey: "cal_hypo" },
  { key: "dichlor_per_lb", label: "Dichlor", unit: "/lb", defaultKey: "dichlor" },
  { key: "bromine_per_lb", label: "Bromine", unit: "/lb", defaultKey: "bromine" },
];

function getDefaultPrice(defaults: RegionalDefault[], row: ChemicalRow): number | null {
  if (row.defaultKey === "acid") {
    // Acid price is on every default row, take from first
    return defaults[0]?.acid_price_per_gallon ?? null;
  }
  if (row.defaultKey === "cya") {
    return defaults[0]?.cya_price_per_lb ?? null;
  }
  if (row.defaultKey === "salt") {
    return defaults[0]?.salt_price_per_bag ?? null;
  }
  // Sanitizer-specific: find the matching row
  const match = defaults.find((d) => d.sanitizer_type === row.defaultKey);
  return match?.sanitizer_price_per_unit ?? null;
}

export default function SettingsPage() {
  const { user, organizationName, role } = useAuth();
  const canEdit = role === "owner" || role === "admin";

  const [defaults, setDefaults] = useState<RegionalDefault[]>([]);
  const [orgPrices, setOrgPrices] = useState<OrgChemicalPrices | null>(null);
  const [editPrices, setEditPrices] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadPricing = useCallback(async () => {
    try {
      const [defs, prices] = await Promise.all([
        api.get<RegionalDefault[]>("/v1/chemical-costs/defaults/sacramento_ca"),
        api.get<OrgChemicalPrices>("/v1/chemical-costs/org-prices"),
      ]);
      setDefaults(defs);
      setOrgPrices(prices);
      // Initialize edit fields from org prices (or defaults)
      const initial: Record<string, string> = {};
      for (const row of CHEMICAL_ROWS) {
        const orgVal = prices[row.key];
        if (orgVal != null) {
          initial[row.key] = orgVal.toString();
        } else {
          const def = getDefaultPrice(defs, row);
          initial[row.key] = def != null ? def.toString() : "";
        }
      }
      setEditPrices(initial);
    } catch {
      toast.error("Failed to load chemical pricing");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPricing();
  }, [loadPricing]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const body: Record<string, number | null> = {};
      for (const row of CHEMICAL_ROWS) {
        const val = editPrices[row.key];
        body[row.key] = val && val.trim() !== "" ? parseFloat(val) : null;
      }
      const updated = await api.put<OrgChemicalPrices>("/v1/chemical-costs/org-prices?recompute=true", body);
      setOrgPrices(updated);
      toast.success("Chemical prices updated and all pool costs recomputed");
    } catch {
      toast.error("Failed to save chemical prices");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Organization and account settings
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Account</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>
              <span className="text-muted-foreground">Name: </span>
              {user?.first_name} {user?.last_name}
            </div>
            <div>
              <span className="text-muted-foreground">Email: </span>
              {user?.email}
            </div>
            <div>
              <span className="text-muted-foreground">Role: </span>
              {role}
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Organization</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>
              <span className="text-muted-foreground">Name: </span>
              {organizationName}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Chemical Prices */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Chemical Prices</CardTitle>
          <p className="text-sm text-muted-foreground">
            Regional defaults for Sacramento, CA. Override with your actual costs.
          </p>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-4">
              {/* Header row */}
              <div className="grid grid-cols-4 gap-3 px-1">
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Chemical</div>
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Default</div>
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Your Price</div>
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Unit</div>
              </div>

              {/* Data rows */}
              {CHEMICAL_ROWS.map((row, idx) => {
                const defPrice = getDefaultPrice(defaults, row);
                return (
                  <div
                    key={row.key}
                    className={`grid grid-cols-4 gap-3 items-center px-1 py-1.5 rounded ${idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                  >
                    <div className="text-sm font-medium">{row.label}</div>
                    <div className="text-sm text-muted-foreground">
                      {defPrice != null ? `$${defPrice.toFixed(2)}` : "—"}
                    </div>
                    <div>
                      {canEdit ? (
                        <div className="relative">
                          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
                          <Input
                            type="number"
                            step="0.01"
                            min="0"
                            className="h-8 pl-5 text-sm w-full"
                            value={editPrices[row.key] ?? ""}
                            onChange={(e) => setEditPrices((prev) => ({ ...prev, [row.key]: e.target.value }))}
                          />
                        </div>
                      ) : (
                        <span className="text-sm">
                          {orgPrices?.[row.key] != null ? `$${(orgPrices[row.key] as number).toFixed(2)}` : defPrice != null ? `$${defPrice.toFixed(2)}` : "—"}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">{row.unit}</div>
                  </div>
                );
              })}

              {/* Save button */}
              {canEdit && (
                <div className="flex justify-end pt-2">
                  <Button onClick={handleSave} disabled={saving}>
                    {saving ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Updating...
                      </>
                    ) : (
                      "Save & Update All Pools"
                    )}
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
