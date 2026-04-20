"use client";

import { useState, useEffect, useCallback, useRef, type FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { api, getBackendOrigin } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
import { toast } from "sonner";
import { Loader2, Save, Pencil, Upload, Workflow, ChevronRight } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
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
import { Textarea } from "@/components/ui/textarea";
import { AddressesSection } from "@/components/settings/addresses-section";

// --- Types ---

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

type SettingsTab = "general" | "billing" | "tiers";

interface BillingTerms {
  payment_terms_days: number;
  estimate_validity_days: number;
  late_fee_pct: number;
  warranty_days: number;
  billable_labor_rate: number;
  estimate_terms: string | null;
}

function BillingTermsSection() {
  const [terms, setTerms] = useState<BillingTerms | null>(null);
  const [form, setForm] = useState<BillingTerms>({ payment_terms_days: 30, estimate_validity_days: 30, late_fee_pct: 1.5, warranty_days: 30, billable_labor_rate: 125, estimate_terms: null });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<BillingTerms>("/v1/charge-settings/billing-terms");
      setTerms(data);
      setForm(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = terms && (
    form.payment_terms_days !== terms.payment_terms_days ||
    form.estimate_validity_days !== terms.estimate_validity_days ||
    form.late_fee_pct !== terms.late_fee_pct ||
    form.warranty_days !== terms.warranty_days ||
    form.billable_labor_rate !== terms.billable_labor_rate ||
    (form.estimate_terms || "") !== (terms.estimate_terms || "")
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/v1/charge-settings/billing-terms", form);
      toast.success("Billing terms updated");
      load();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return null;

  return (
    <div className="space-y-4">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Payment & Estimate Terms</CardTitle>
          <CardDescription>These values appear on estimates sent to customers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <Label className="text-sm font-medium">Payment Terms</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">Net</span>
                <Input
                  type="number"
                  value={form.payment_terms_days}
                  onChange={(e) => setForm({ ...form, payment_terms_days: parseInt(e.target.value) || 0 })}
                  className="w-20 h-8 text-sm"
                  min={0}
                />
                <span className="text-sm text-muted-foreground">days</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-sm font-medium">Estimate Valid</Label>
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  value={form.estimate_validity_days}
                  onChange={(e) => setForm({ ...form, estimate_validity_days: parseInt(e.target.value) || 0 })}
                  className="w-20 h-8 text-sm"
                  min={1}
                />
                <span className="text-sm text-muted-foreground">days</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-sm font-medium">Late Fee</Label>
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  step="0.1"
                  value={form.late_fee_pct}
                  onChange={(e) => setForm({ ...form, late_fee_pct: parseFloat(e.target.value) || 0 })}
                  className="w-20 h-8 text-sm"
                  min={0}
                />
                <span className="text-sm text-muted-foreground">% / month</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-sm font-medium">Labor Warranty</Label>
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  value={form.warranty_days}
                  onChange={(e) => setForm({ ...form, warranty_days: parseInt(e.target.value) || 0 })}
                  className="w-20 h-8 text-sm"
                  min={0}
                />
                <span className="text-sm text-muted-foreground">days</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-sm font-medium">Billable Labor Rate</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  value={form.billable_labor_rate}
                  onChange={(e) => setForm({ ...form, billable_labor_rate: parseFloat(e.target.value) || 0 })}
                  className="w-20 h-8 text-sm"
                  min={0}
                  step="5"
                />
                <span className="text-sm text-muted-foreground">/ hour</span>
              </div>
            </div>
          </div>

          {isDirty && (
            <Button onClick={handleSave} disabled={saving} size="sm">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
              Save
            </Button>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Custom Estimate Terms</CardTitle>
          <CardDescription>Override the default terms & conditions shown on estimates. Leave blank to use standard terms.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={form.estimate_terms || ""}
            onChange={(e) => setForm({ ...form, estimate_terms: e.target.value || null })}
            rows={8}
            placeholder="Enter custom terms & conditions..."
            className="text-sm"
          />
          <p className="text-[10px] text-muted-foreground">If blank, standard terms are displayed covering scope, pricing, payment, warranty, access, cancellation, and liability.</p>

          {isDirty && (
            <Button onClick={handleSave} disabled={saving} size="sm">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
              Save
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function BrandingSection() {
  const { refreshUser } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [branding, setBranding] = useState<{ name: string; logo_url: string | null; primary_color: string | null; tagline: string | null; email_signature: string | null } | null>(null);
  const [form, setForm] = useState({ name: "", primary_color: "", tagline: "", email_signature: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ name: string; logo_url: string | null; primary_color: string | null; tagline: string | null; email_signature: string | null }>("/v1/branding");
      setBranding(data);
      setForm({ name: data.name || "", primary_color: data.primary_color || "", tagline: data.tagline || "", email_signature: data.email_signature || "" });
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = branding && (
    form.name !== (branding.name || "") ||
    form.primary_color !== (branding.primary_color || "") ||
    form.tagline !== (branding.tagline || "") ||
    form.email_signature !== (branding.email_signature || "")
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/v1/branding", {
        organization_name: form.name,
        primary_color: form.primary_color || null,
        tagline: form.tagline || null,
        email_signature: form.email_signature || null,
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

        {/* Email Signature */}
        <div className="space-y-1">
          <Label className="text-sm font-medium">Email Signature</Label>
          <Textarea
            value={form.email_signature}
            onChange={(e) => setForm({ ...form, email_signature: e.target.value })}
            rows={4}
            placeholder={"Company Name\nemail@company.com\ncompany.com"}
            className="text-sm font-mono"
          />
          <p className="text-[10px] text-muted-foreground">Appended to all outbound emails. Plain text.</p>
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
  const { can } = usePermissions();
  const canEdit = role === "owner" || role === "admin";
  const canManageWorkflows = can("workflow.manage_config");
  const [tab, setTab] = useState<SettingsTab>("general");
  const [editMode, setEditMode] = useState(false);

  // Service tiers
  const [tiers, setTiers] = useState<ServiceTier[]>([]);
  const [tiersLoading, setTiersLoading] = useState(true);
  const [editingTier, setEditingTier] = useState<string | null>(null);
  const [tierForm, setTierForm] = useState<Partial<ServiceTier>>({});
  const [tierSaving, setTierSaving] = useState(false);

  // Load tiers
  useEffect(() => {
    api.get<ServiceTier[]>("/v1/service-tiers")
      .then(setTiers)
      .catch(() => toast.error("Failed to load service tiers"))
      .finally(() => setTiersLoading(false));
  }, []);

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

  return (
    <PageLayout
      title="Settings"
      subtitle="Organization configuration"
      action={canEdit ? (editMode ? <Button variant="ghost" size="sm" onClick={() => setEditMode(false)}>Done</Button> : <Button variant="outline" size="sm" onClick={() => setEditMode(true)}><Pencil className="h-3.5 w-3.5 mr-1.5" />Edit</Button>) : undefined}
      tabs={[
        { key: "general", label: "General" },
        { key: "billing", label: "Billing" },
        { key: "tiers", label: "Service Tiers" },
      ]}
      activeTab={tab}
      onTabChange={(key) => setTab(key as SettingsTab)}
    >
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
          {canEdit && <AddressesSection />}
          {canManageWorkflows && (
            <Link href="/settings/workflows" className="block">
              <Card className="shadow-sm hover:border-muted-foreground/40 transition-colors">
                <CardContent className="flex items-center gap-3 py-3">
                  <Workflow className="h-4 w-4 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">Workflows</div>
                    <div className="text-xs text-muted-foreground">How new jobs get handled after they&apos;re created.</div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          )}
        </div>
      )}

      {/* Billing */}
      {tab === "billing" && canEdit && <BillingTermsSection />}

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
    </PageLayout>
  );
}
