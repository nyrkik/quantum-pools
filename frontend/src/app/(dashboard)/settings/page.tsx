"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, getBackendOrigin } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Save, Plus, Pencil, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { OrgCostSettings, OrgCostSettingsUpdate } from "@/types/profitability";
import { VendorsSection } from "@/components/settings/vendors-section";

// --- Types ---

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

interface ServiceTier {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  sort_order: number;
  base_rate: number;
  estimated_minutes: number;
  includes_chems: boolean;
  includes_skim: boolean;
  includes_baskets: boolean;
  includes_vacuum: boolean;
  includes_brush: boolean;
  includes_equipment_check: boolean;
  is_default: boolean;
  is_active: boolean;
}

interface ChemicalRow {
  key: keyof Omit<OrgChemicalPrices, "id" | "organization_id" | "updated_at">;
  label: string;
  unit: string;
  defaultKey: string;
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
  if (row.defaultKey === "acid") return defaults[0]?.acid_price_per_gallon ?? null;
  if (row.defaultKey === "cya") return defaults[0]?.cya_price_per_lb ?? null;
  if (row.defaultKey === "salt") return defaults[0]?.salt_price_per_bag ?? null;
  const match = defaults.find((d) => d.sanitizer_type === row.defaultKey);
  return match?.sanitizer_price_per_unit ?? null;
}

type SettingsTab = "general" | "costs" | "tiers" | "chemicals" | "charges" | "vendors";

function BrandingSection() {
  const { refreshUser } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [branding, setBranding] = useState<{ name: string; logo_url: string | null; primary_color: string | null; tagline: string | null } | null>(null);
  const [form, setForm] = useState({ name: "", primary_color: "", tagline: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ name: string; logo_url: string | null; primary_color: string | null; tagline: string | null }>("/v1/branding");
      setBranding(data);
      setForm({ name: data.name || "", primary_color: data.primary_color || "", tagline: data.tagline || "" });
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = branding && (
    form.name !== (branding.name || "") ||
    form.primary_color !== (branding.primary_color || "") ||
    form.tagline !== (branding.tagline || "")
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/v1/branding", {
        organization_name: form.name,
        primary_color: form.primary_color || null,
        tagline: form.tagline || null,
      });
      toast.success("Branding updated");
      load();
      refreshUser();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const backendUrl = `${getBackendOrigin()}/api/v1/branding/logo`;
      const res = await fetch(backendUrl, { method: "POST", body: formData, credentials: "include" });
      if (!res.ok) throw new Error("Upload failed");
      toast.success("Logo uploaded");
      load();
      refreshUser();
    } catch {
      toast.error("Failed to upload logo");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const logoSrc = branding?.logo_url
    ? `${getBackendOrigin()}${branding.logo_url}`
    : null;

  if (loading) return null;

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">Branding</CardTitle>
        <CardDescription>Customize how your company appears in the app.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Logo */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Logo</Label>
          <div className="flex items-center gap-4">
            {logoSrc ? (
              <img src={logoSrc} alt="Logo" className="h-16 w-auto object-contain rounded border p-1 bg-white" />
            ) : (
              <div className="h-16 w-16 rounded border bg-muted flex items-center justify-center text-xs text-muted-foreground">No logo</div>
            )}
            <div>
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" className="hidden" onChange={handleLogoUpload} />
              <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
                {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Upload className="h-3.5 w-3.5 mr-1.5" />}
                {logoSrc ? "Change Logo" : "Upload Logo"}
              </Button>
              <p className="text-[10px] text-muted-foreground mt-1">PNG, JPEG, SVG, or WebP. Max 2MB.</p>
            </div>
          </div>
        </div>

        {/* Company Name */}
        <div className="space-y-1">
          <Label className="text-sm font-medium">Company Name</Label>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="max-w-sm" />
        </div>

        {/* Primary Color */}
        <div className="space-y-1">
          <Label className="text-sm font-medium">Brand Color</Label>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={form.primary_color || "#1a1a2e"}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              className="h-9 w-12 rounded border cursor-pointer"
            />
            <Input
              value={form.primary_color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              placeholder="#1e40af"
              className="w-28 font-mono text-sm"
            />
            {form.primary_color && (
              <div className="flex items-center gap-2">
                <div className="h-6 w-6 rounded" style={{ backgroundColor: form.primary_color }} />
                <span className="text-sm font-medium" style={{ color: form.primary_color }}>Preview</span>
              </div>
            )}
          </div>
        </div>

        {/* Tagline */}
        <div className="space-y-1">
          <Label className="text-sm font-medium">Tagline</Label>
          <Input
            value={form.tagline}
            onChange={(e) => setForm({ ...form, tagline: e.target.value })}
            placeholder="Your company slogan or tagline"
            className="max-w-sm"
          />
          <p className="text-[10px] text-muted-foreground">Displayed under your logo in the sidebar.</p>
        </div>

        {/* Save */}
        {isDirty && (
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
            Save Branding
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { user, organizationName, role } = useAuth();
  const canEdit = role === "owner" || role === "admin";
  const [tab, setTab] = useState<SettingsTab>("general");
  const [editMode, setEditMode] = useState(false);

  // Cost settings
  const [costSettings, setCostSettings] = useState<OrgCostSettings | null>(null);
  const [costForm, setCostForm] = useState<OrgCostSettingsUpdate>({});
  const [costLoading, setCostLoading] = useState(true);
  const [costSaving, setCostSaving] = useState(false);

  // Chemical prices
  const [defaults, setDefaults] = useState<RegionalDefault[]>([]);
  const [orgPrices, setOrgPrices] = useState<OrgChemicalPrices | null>(null);
  const [editPrices, setEditPrices] = useState<Record<string, string>>({});
  const [chemSaving, setChemSaving] = useState(false);
  const [chemLoading, setChemLoading] = useState(true);

  // Service tiers
  const [tiers, setTiers] = useState<ServiceTier[]>([]);
  const [tiersLoading, setTiersLoading] = useState(true);
  const [editingTier, setEditingTier] = useState<string | null>(null);
  const [tierForm, setTierForm] = useState<Partial<ServiceTier>>({});
  const [tierSaving, setTierSaving] = useState(false);

  // Load cost settings
  useEffect(() => {
    api.get<OrgCostSettings>("/v1/profitability/settings")
      .then((data) => {
        setCostSettings(data);
        setCostForm({
          burdened_labor_rate: data.burdened_labor_rate,
          vehicle_cost_per_mile: data.vehicle_cost_per_mile,
          chemical_cost_per_gallon: data.chemical_cost_per_gallon,
          monthly_overhead: data.monthly_overhead,
          target_margin_pct: data.target_margin_pct,
          residential_overhead_per_account: data.residential_overhead_per_account,
          commercial_overhead_per_account: data.commercial_overhead_per_account,
          avg_drive_minutes: data.avg_drive_minutes,
          avg_drive_miles: data.avg_drive_miles,
          visits_per_month: data.visits_per_month,
          semi_annual_discount_value: data.semi_annual_discount_value,
          annual_discount_value: data.annual_discount_value,
          default_parts_markup_pct: data.default_parts_markup_pct,
        });
      })
      .catch(() => toast.error("Failed to load cost settings"))
      .finally(() => setCostLoading(false));
  }, []);

  // Load chemical prices
  const loadChemicals = useCallback(async () => {
    try {
      const [defs, prices] = await Promise.all([
        api.get<RegionalDefault[]>("/v1/chemical-costs/defaults/sacramento_ca"),
        api.get<OrgChemicalPrices>("/v1/chemical-costs/org-prices"),
      ]);
      setDefaults(defs);
      setOrgPrices(prices);
      const initial: Record<string, string> = {};
      for (const row of CHEMICAL_ROWS) {
        const orgVal = prices[row.key];
        initial[row.key] = orgVal != null ? orgVal.toString() : (getDefaultPrice(defs, row)?.toString() ?? "");
      }
      setEditPrices(initial);
    } catch {
      toast.error("Failed to load chemical pricing");
    } finally {
      setChemLoading(false);
    }
  }, []);

  useEffect(() => { loadChemicals(); }, [loadChemicals]);

  // Load tiers
  useEffect(() => {
    api.get<ServiceTier[]>("/v1/service-tiers")
      .then(setTiers)
      .catch(() => toast.error("Failed to load service tiers"))
      .finally(() => setTiersLoading(false));
  }, []);

  const saveCosts = async () => {
    setCostSaving(true);
    try {
      const data = await api.put<OrgCostSettings>("/v1/profitability/settings", costForm);
      setCostSettings(data);
      toast.success("Cost settings saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setCostSaving(false);
    }
  };

  const saveChemicals = async () => {
    setChemSaving(true);
    try {
      const body: Record<string, number | null> = {};
      for (const row of CHEMICAL_ROWS) {
        const val = editPrices[row.key];
        body[row.key] = val && val.trim() !== "" ? parseFloat(val) : null;
      }
      const updated = await api.put<OrgChemicalPrices>("/v1/chemical-costs/org-prices?recompute=true", body);
      setOrgPrices(updated);
      toast.success("Chemical prices saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setChemSaving(false);
    }
  };

  const saveTier = async (tierId: string) => {
    setTierSaving(true);
    try {
      await api.put(`/v1/service-tiers/${tierId}`, tierForm);
      const updated = await api.get<ServiceTier[]>("/v1/service-tiers");
      setTiers(updated);
      setEditingTier(null);
      toast.success("Tier saved");
    } catch {
      toast.error("Failed to save tier");
    } finally {
      setTierSaving(false);
    }
  };

  const TABS: { key: SettingsTab; label: string }[] = [
    { key: "general", label: "General" },
    { key: "costs", label: "Costs & Margins" },
    { key: "tiers", label: "Service Tiers" },
    { key: "chemicals", label: "Chemical Prices" },
    { key: "charges", label: "Charges" },
    { key: "vendors", label: "Vendors" },
  ];

  const costFields: { key: keyof OrgCostSettingsUpdate; label: string; prefix: string; suffix: string; description: string; step?: string }[] = [
    { key: "burdened_labor_rate", label: "Burdened Labor Rate", prefix: "$", suffix: "/hour", description: "Fully loaded cost per hour (wages + taxes + benefits)" },
    { key: "vehicle_cost_per_mile", label: "Vehicle Cost per Mile", prefix: "$", suffix: "/mile", description: "IRS standard rate or your actual cost" },
    { key: "chemical_cost_per_gallon", label: "Chemical Cost per 10k Gallons", prefix: "$", suffix: "/visit", description: "Fallback when no per-pool chemical profile exists" },
    { key: "monthly_overhead", label: "Total Monthly Overhead", prefix: "$", suffix: "/month", description: "Office, insurance, software — for reference only" },
    { key: "target_margin_pct", label: "Target Profit Margin", prefix: "", suffix: "%", description: "Accounts below this are flagged for adjustment" },
    { key: "residential_overhead_per_account", label: "Residential Overhead", prefix: "$", suffix: "/account", description: "Per-account overhead for residential (typical $8-15)" },
    { key: "commercial_overhead_per_account", label: "Commercial Overhead", prefix: "$", suffix: "/account", description: "Per-account overhead for commercial (typical $35-60)" },
    { key: "avg_drive_minutes", label: "Avg Drive Between Stops", prefix: "", suffix: "min", description: "Average drive time between service stops" },
    { key: "avg_drive_miles", label: "Avg Distance Between Stops", prefix: "", suffix: "miles", description: "Average miles between stops" },
    { key: "visits_per_month", label: "Visits per Month", prefix: "", suffix: "visits", description: "Standard weekly = 4" },
    { key: "semi_annual_discount_value", label: "Semi-Annual Discount", prefix: "", suffix: "%", description: "Discount for semi-annual billing" },
    { key: "annual_discount_value", label: "Annual Discount", prefix: "", suffix: "%", description: "Discount for annual billing" },
    { key: "default_parts_markup_pct", label: "Default Parts Markup", prefix: "", suffix: "%", description: "Default markup on parts for customer pricing (typical 25-50%)" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-muted-foreground text-sm">Organization and service configuration</p>
        </div>
        {canEdit && !editMode && (
          <Button variant="outline" size="sm" onClick={() => setEditMode(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1.5" />
            Edit
          </Button>
        )}
        {editMode && (
          <Button variant="ghost" size="sm" onClick={() => setEditMode(false)}>
            Done
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* General */}
      {tab === "general" && (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="shadow-sm">
              <CardHeader><CardTitle className="text-base">Account</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div><span className="text-muted-foreground">Name: </span>{user?.first_name} {user?.last_name}</div>
                <div><span className="text-muted-foreground">Email: </span>{user?.email}</div>
                <div><span className="text-muted-foreground">Role: </span>{role}</div>
              </CardContent>
            </Card>
            <Card className="shadow-sm">
              <CardHeader><CardTitle className="text-base">Organization</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div><span className="text-muted-foreground">Name: </span>{organizationName}</div>
              </CardContent>
            </Card>
          </div>
          {canEdit && <BrandingSection />}
        </div>
      )}

      {/* Costs & Margins */}
      {tab === "costs" && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Cost Configuration</CardTitle>
            <CardDescription>These values drive all profitability calculations.</CardDescription>
          </CardHeader>
          <CardContent>
            {costLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin" /></div>
            ) : (
              <div className="space-y-5">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {costFields.map((f) => (
                    <div key={f.key} className="space-y-1">
                      <Label className="text-xs">{f.label}</Label>
                      <div className="flex items-center gap-1.5">
                        {f.prefix && <span className="text-sm text-muted-foreground">{f.prefix}</span>}
                        <Input
                          type="number"
                          step={f.step || "0.01"}
                          className="h-8 text-sm max-w-[140px]"
                          value={String((costForm as Record<string, unknown>)[f.key] ?? "")}
                          onChange={(e) => setCostForm({ ...costForm, [f.key]: parseFloat(e.target.value) || 0 })}
                          disabled={!editMode}
                        />
                        <span className="text-xs text-muted-foreground">{f.suffix}</span>
                      </div>
                      <p className="text-[10px] text-muted-foreground">{f.description}</p>
                    </div>
                  ))}
                </div>
                {editMode && (
                  <Button onClick={saveCosts} disabled={costSaving} size="sm">
                    {costSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
                    Save
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Service Tiers */}
      {tab === "tiers" && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Residential Service Tiers</CardTitle>
            <CardDescription>Define service packages and base rates for residential clients.</CardDescription>
          </CardHeader>
          <CardContent>
            {tiersLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin" /></div>
            ) : (
              <div className="space-y-3">
                {tiers.map((tier) => (
                  <div key={tier.id} className={`border rounded-lg p-4 ${tier.is_default ? "border-primary/30 bg-primary/5" : ""}`}>
                    {editingTier === tier.id ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-3 gap-3">
                          <div className="space-y-1">
                            <Label className="text-xs">Name</Label>
                            <Input className="h-8 text-sm" value={tierForm.name || ""} onChange={(e) => setTierForm({ ...tierForm, name: e.target.value })} />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs">Base Rate</Label>
                            <div className="flex items-center gap-1">
                              <span className="text-sm text-muted-foreground">$</span>
                              <Input type="number" className="h-8 text-sm" value={tierForm.base_rate || ""} onChange={(e) => setTierForm({ ...tierForm, base_rate: parseFloat(e.target.value) || 0 })} />
                              <span className="text-xs text-muted-foreground">/mo</span>
                            </div>
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs">Est. Minutes</Label>
                            <Input type="number" className="h-8 text-sm" value={tierForm.estimated_minutes || ""} onChange={(e) => setTierForm({ ...tierForm, estimated_minutes: parseInt(e.target.value) || 0 })} />
                          </div>
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs">Description</Label>
                          <Input className="h-8 text-sm" value={tierForm.description || ""} onChange={(e) => setTierForm({ ...tierForm, description: e.target.value })} />
                        </div>
                        <div className="flex flex-wrap gap-4 text-xs">
                          {(["includes_chems", "includes_skim", "includes_baskets", "includes_vacuum", "includes_brush", "includes_equipment_check"] as const).map((k) => (
                            <label key={k} className="flex items-center gap-1.5 cursor-pointer">
                              <Switch
                                checked={!!tierForm[k]}
                                onCheckedChange={(v) => setTierForm({ ...tierForm, [k]: v })}
                                className="h-4 w-7"
                              />
                              <span className="capitalize">{k.replace("includes_", "")}</span>
                            </label>
                          ))}
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => saveTier(tier.id)} disabled={tierSaving}>
                            {tierSaving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingTier(null)}>Cancel</Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold">{tier.name}</h3>
                            {tier.is_default && <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-medium">Default</span>}
                          </div>
                          <p className="text-sm text-muted-foreground mt-0.5">{tier.description}</p>
                          <div className="flex gap-4 mt-2 text-sm">
                            <span className="font-semibold">${tier.base_rate.toFixed(0)}/mo</span>
                            <span className="text-muted-foreground">{tier.estimated_minutes} min</span>
                            <span className="text-muted-foreground">
                              {[
                                tier.includes_chems && "Chems",
                                tier.includes_skim && "Skim",
                                tier.includes_baskets && "Baskets",
                                tier.includes_vacuum && "Vacuum",
                                tier.includes_brush && "Brush",
                                tier.includes_equipment_check && "Equip Check",
                              ].filter(Boolean).join(" · ")}
                            </span>
                          </div>
                        </div>
                        {editMode && (
                          <Button variant="ghost" size="icon" onClick={() => { setEditingTier(tier.id); setTierForm({ ...tier }); }}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Chemical Prices */}
      {tab === "chemicals" && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Chemical Prices</CardTitle>
            <CardDescription>Regional defaults for Sacramento, CA. Override with your actual costs.</CardDescription>
          </CardHeader>
          <CardContent>
            {chemLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin" /></div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-4 gap-3 px-1">
                  <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Chemical</div>
                  <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Default</div>
                  <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Your Price</div>
                  <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Unit</div>
                </div>
                {CHEMICAL_ROWS.map((row, idx) => {
                  const defPrice = getDefaultPrice(defaults, row);
                  return (
                    <div key={row.key} className={`grid grid-cols-4 gap-3 items-center px-1 py-1.5 rounded ${idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                      <div className="text-sm font-medium">{row.label}</div>
                      <div className="text-sm text-muted-foreground">{defPrice != null ? `$${defPrice.toFixed(2)}` : "—"}</div>
                      <div>
                        {editMode ? (
                          <div className="relative">
                            <span className="absolute left-2 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
                            <Input type="number" step="0.01" min="0" className="h-8 pl-5 text-sm" value={editPrices[row.key] ?? ""} onChange={(e) => setEditPrices((prev) => ({ ...prev, [row.key]: e.target.value }))} />
                          </div>
                        ) : (
                          <span className="text-sm">{orgPrices?.[row.key] != null ? `$${(orgPrices[row.key] as number).toFixed(2)}` : defPrice != null ? `$${defPrice.toFixed(2)}` : "—"}</span>
                        )}
                      </div>
                      <div className="text-sm text-muted-foreground">{row.unit}</div>
                    </div>
                  );
                })}
                {editMode && (
                  <div className="flex justify-end pt-2">
                    <Button onClick={saveChemicals} disabled={chemSaving} size="sm">
                      {chemSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
                      Save & Recompute
                    </Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Charges */}
      {tab === "charges" && <ChargeSettingsTab editMode={editMode} />}

      {/* Vendors */}
      {tab === "vendors" && <VendorsSection editMode={editMode} />}
    </div>
  );
}

// ── Charge Settings Tab ───────────────────────────────────────

interface ChargeTemplate {
  id: string;
  name: string;
  default_amount: number;
  category: string;
  is_taxable: boolean;
  requires_approval: boolean;
  sort_order: number;
}

interface Thresholds {
  auto_approve_threshold: number;
  separate_invoice_threshold: number;
  require_photo_threshold: number;
}

function ChargeSettingsTab({ editMode }: { editMode: boolean }) {
  const [templates, setTemplates] = useState<ChargeTemplate[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<ChargeTemplate>>({});
  const [addMode, setAddMode] = useState(false);
  const [addForm, setAddForm] = useState({ name: "", default_amount: "", category: "other", requires_approval: false });
  const [thresholdForm, setThresholdForm] = useState<Thresholds>({ auto_approve_threshold: 75, separate_invoice_threshold: 200, require_photo_threshold: 50 });
  const [thresholdSaving, setThresholdSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [tmpls, thresh] = await Promise.all([
        api.get<ChargeTemplate[]>("/v1/charge-templates"),
        api.get<Thresholds>("/v1/charge-settings"),
      ]);
      setTemplates(tmpls);
      setThresholds(thresh);
      setThresholdForm(thresh);
    } catch {
      toast.error("Failed to load charge settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveTemplate = async (id: string) => {
    setSaving(true);
    try {
      await api.put(`/v1/charge-templates/${id}`, editForm);
      toast.success("Template updated");
      setEditingId(null);
      load();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const addTemplate = async () => {
    if (!addForm.name || !addForm.default_amount) return;
    setSaving(true);
    try {
      await api.post("/v1/charge-templates", {
        name: addForm.name,
        default_amount: parseFloat(addForm.default_amount),
        category: addForm.category,
        requires_approval: addForm.requires_approval,
      });
      toast.success("Template created");
      setAddMode(false);
      setAddForm({ name: "", default_amount: "", category: "other", requires_approval: false });
      load();
    } catch {
      toast.error("Failed to create");
    } finally {
      setSaving(false);
    }
  };

  const deleteTemplate = async (id: string) => {
    try {
      await api.delete(`/v1/charge-templates/${id}`);
      toast.success("Template removed");
      load();
    } catch {
      toast.error("Failed to delete");
    }
  };

  const saveThresholds = async () => {
    setThresholdSaving(true);
    try {
      const updated = await api.put<Thresholds>("/v1/charge-settings", thresholdForm);
      setThresholds(updated);
      toast.success("Thresholds saved");
    } catch {
      toast.error("Failed to save thresholds");
    } finally {
      setThresholdSaving(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  }

  return (
    <div className="space-y-6">
      {/* Thresholds */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Charge Thresholds</CardTitle>
          <CardDescription>Control auto-approval, photo requirements, and separate invoicing.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label className="text-xs">Auto-Approve Below</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="5"
                  className="h-8 text-sm max-w-[120px]"
                  value={thresholdForm.auto_approve_threshold}
                  onChange={(e) => setThresholdForm({ ...thresholdForm, auto_approve_threshold: parseFloat(e.target.value) || 0 })}
                  disabled={!editMode}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Charges below this amount skip approval</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Require Photo Above</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="5"
                  className="h-8 text-sm max-w-[120px]"
                  value={thresholdForm.require_photo_threshold}
                  onChange={(e) => setThresholdForm({ ...thresholdForm, require_photo_threshold: parseFloat(e.target.value) || 0 })}
                  disabled={!editMode}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Photo evidence recommended above this</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Separate Invoice Above</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="10"
                  className="h-8 text-sm max-w-[120px]"
                  value={thresholdForm.separate_invoice_threshold}
                  onChange={(e) => setThresholdForm({ ...thresholdForm, separate_invoice_threshold: parseFloat(e.target.value) || 0 })}
                  disabled={!editMode}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Large charges become separate estimates</p>
            </div>
          </div>
          {editMode && (
            <Button onClick={saveThresholds} disabled={thresholdSaving} size="sm" className="mt-4">
              {thresholdSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
              Save Thresholds
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Templates */}
      <Card className="shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Charge Templates</CardTitle>
              <CardDescription>Predefined charge types techs can select in the field.</CardDescription>
            </div>
            {editMode && (
              <Button variant="outline" size="sm" onClick={() => setAddMode(true)}>
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                Add
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {addMode && (
              <div className="border rounded-lg p-3 space-y-3 bg-muted/30">
                <div className="grid grid-cols-3 gap-3">
                  <Input placeholder="Name" className="h-8 text-sm" value={addForm.name} onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} />
                  <div className="flex items-center gap-1">
                    <span className="text-sm text-muted-foreground">$</span>
                    <Input type="number" placeholder="Amount" className="h-8 text-sm" value={addForm.default_amount} onChange={(e) => setAddForm({ ...addForm, default_amount: e.target.value })} />
                  </div>
                  <Select value={addForm.category} onValueChange={(v) => setAddForm({ ...addForm, category: v })}>
                    <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="time">Time</SelectItem>
                      <SelectItem value="chemical">Chemical</SelectItem>
                      <SelectItem value="material">Material</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs">
                    <Switch
                      checked={addForm.requires_approval}
                      onCheckedChange={(v) => setAddForm({ ...addForm, requires_approval: v })}
                      className="h-4 w-7"
                    />
                    Always requires approval
                  </label>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={addTemplate} disabled={saving || !addForm.name || !addForm.default_amount}>
                      {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setAddMode(false)}>Cancel</Button>
                  </div>
                </div>
              </div>
            )}

            {templates.map((tmpl) => (
              <div key={tmpl.id} className="border rounded-lg p-3">
                {editingId === tmpl.id ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 gap-3">
                      <Input className="h-8 text-sm" value={editForm.name || ""} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
                      <div className="flex items-center gap-1">
                        <span className="text-sm text-muted-foreground">$</span>
                        <Input type="number" className="h-8 text-sm" value={editForm.default_amount || ""} onChange={(e) => setEditForm({ ...editForm, default_amount: parseFloat(e.target.value) || 0 })} />
                      </div>
                      <Select value={editForm.category || "other"} onValueChange={(v) => setEditForm({ ...editForm, category: v })}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="time">Time</SelectItem>
                          <SelectItem value="chemical">Chemical</SelectItem>
                          <SelectItem value="material">Material</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-xs">
                        <Switch
                          checked={!!editForm.requires_approval}
                          onCheckedChange={(v) => setEditForm({ ...editForm, requires_approval: v })}
                          className="h-4 w-7"
                        />
                        Always requires approval
                      </label>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => saveTemplate(tmpl.id)} disabled={saving}>
                          {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{tmpl.name}</span>
                        <span className="text-sm font-semibold">${tmpl.default_amount.toFixed(0)}</span>
                        <Badge variant="secondary" className="text-[10px]">{tmpl.category}</Badge>
                        {tmpl.requires_approval && (
                          <Badge variant="outline" className="text-[10px] border-amber-400 text-amber-600">Approval</Badge>
                        )}
                      </div>
                    </div>
                    {editMode && (
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" onClick={() => { setEditingId(tmpl.id); setEditForm({ ...tmpl }); }}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => deleteTemplate(tmpl.id)} className="text-destructive">
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
