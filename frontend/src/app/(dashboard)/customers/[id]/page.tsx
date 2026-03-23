"use client";

import { useState, useEffect, useCallback, useRef, use } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  ArrowLeft,
  MapPin,
  Building2,
  Home,
  Pencil,
  X,
  Loader2,
  Droplets,
  Receipt,
  LayoutDashboard,
  Calendar,
  DollarSign,
  Clock,
  ClipboardCheck,
  History,
  Satellite,
  AlertTriangle,
} from "lucide-react";
import Link from "next/link";
import { usePermissions } from "@/lib/permissions";
import type { PropertyPhoto } from "@/types/photo";
import { WfTile, type WaterFeature as WfTileWF, type TechAssignment } from "@/components/water-features/wf-tile";
import { AddWfForm } from "@/components/water-features/add-wf-form";
import { AddPropertyForm } from "@/components/properties/add-property-form";
import { PropertySiteDetails } from "@/components/properties/property-site-details";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://100.121.52.15:7061";

interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  company_name: string | null;
  customer_type: string;
  email: string | null;
  phone: string | null;
  monthly_rate: number;
  balance: number;
  billing_address: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_zip: string | null;
  service_frequency: string | null;
  preferred_day: string | null;
  billing_frequency: string;
  payment_method: string | null;
  payment_terms_days: number;
  difficulty_rating: number;
  status: string;
  notes: string | null;
  is_active: boolean;
  property_count: number;
  created_at: string;
}

interface WaterFeature {
  id: string;
  property_id: string;
  name: string | null;
  water_type: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  pool_surface: string | null;
  pool_length_ft: number | null;
  pool_width_ft: number | null;
  pool_depth_shallow: number | null;
  pool_depth_deep: number | null;
  pool_depth_avg: number | null;
  pool_shape: string | null;
  pool_volume_method: string | null;
  dimension_source: string | null;
  dimension_source_date: string | null;
  perimeter_ft: number | null;
  sanitizer_type: string | null;
  pump_type: string | null;
  filter_type: string | null;
  heater_type: string | null;
  chlorinator_type: string | null;
  automation_system: string | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
  notes: string | null;
  is_active: boolean;
}

interface Property {
  id: string;
  customer_id: string;
  name: string | null;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  pool_surface: string | null;
  pool_length_ft: number | null;
  pool_width_ft: number | null;
  pool_depth_shallow: number | null;
  pool_depth_deep: number | null;
  pool_depth_avg: number | null;
  pool_shape: string | null;
  pool_volume_method: string | null;
  has_spa: boolean;
  has_water_feature: boolean;
  pump_type: string | null;
  filter_type: string | null;
  heater_type: string | null;
  chlorinator_type: string | null;
  automation_system: string | null;
  gate_code: string | null;
  access_instructions: string | null;
  dog_on_property: boolean;
  monthly_rate: number | null;
  estimated_service_minutes: number;
  is_locked_to_day: boolean;
  service_day_pattern: string | null;
  notes: string | null;
  is_active: boolean;
  water_features: WaterFeatureSummary[];
}

interface WaterFeatureSummary {
  id: string;
  name: string | null;
  water_type: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
  dimension_source?: string | null;
}

interface Invoice {
  id: string;
  invoice_number: string;
  subject: string | null;
  status: string;
  issue_date: string;
  total: number;
  balance: number;
}



// --- Site Details (gate, dog, access) ---
function SiteDetails({ property, className }: { property: Property; className?: string }) {
  const items: string[] = [];
  if (property.gate_code) items.push(`Gate: ${property.gate_code}`);
  if (property.dog_on_property) items.push("Dog on property");
  if (property.access_instructions) items.push(property.access_instructions);
  if (items.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground ${className || ""}`}>
      {items.map((item, i) => (
        <span key={i} className={item === "Dog on property" ? "text-amber-600 font-medium" : ""}>{item}</span>
      ))}
    </div>
  );
}

// --- Main Page ---
export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const perms = usePermissions();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [heroImages, setHeroImages] = useState<Record<string, PropertyPhoto>>({});
  const [fullWfs, setFullBows] = useState<WaterFeature[]>([]);
  const [techAssignments, setTechAssignments] = useState<Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>>({});
  const isTech = perms.role === "technician";
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const validTabs = ["overview", "service", "details", "wfs", "invoices"] as const;
  const resolvedTab = tabParam === "details" && !isTech ? "overview" : tabParam;
  const initialTab = validTabs.includes(resolvedTab as typeof validTabs[number]) ? (resolvedTab as typeof validTabs[number]) : isTech ? "service" : "overview";
  const [viewTab, setViewTab] = useState<typeof validTabs[number]>(initialTab);
  const [selectedWfId, setSelectedBowId] = useState<string | null>(null);
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null);
  const wfRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const propRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [scrollToPropId, setScrollToPropId] = useState<string | null>(null);
  const [editingDetails, setEditingDetails] = useState(false);
  const [showDiscardDialog, setShowDiscardDialog] = useState(false);
  const [discardTarget, setDiscardTarget] = useState<"details" | null>(null);
  const [wfProfitability, setBowProfitability] = useState<Record<string, { margin_pct: number; suggested_rate: number }>>({});
  const [showRateSplit, setShowRateSplit] = useState(false);
  const [rateSplitData, setRateSplitData] = useState<{
    total_rate: number;
    method: string | null;
    allocations: Array<{ wf_id: string; wf_name: string | null; water_type: string; gallons: number | null; proposed_rate: number; current_rate: number | null }>;
  } | null>(null);
  const [rateSplitEdits, setRateSplitEdits] = useState<Record<string, number>>({});
  const [rateSplitSaving, setRateSplitSaving] = useState(false);
  const [propRates, setPropRates] = useState<Record<string, number>>({});
  const [propRatesDirty, setPropRatesDirty] = useState(false);
  const [companies, setCompanies] = useState<string[]>([]);
  const [newCompanyCustom, setNewCompanyCustom] = useState("");

  // Customer edit form state
  const [custForm, setCustForm] = useState<Customer | null>(null);
  const [custSaving, setCustSaving] = useState(false);
  const [custDirty, setCustDirty] = useState(false);

  // Single-property inline edit state
  const singleProp = properties.length <= 1 ? properties[0] ?? null : null;
  const [propForm, setPropForm] = useState<Property | null>(null);
  const [propDirty, setPropDirty] = useState(false);

  useEffect(() => {
    if (singleProp) setPropForm(singleProp);
  }, [singleProp?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const rates: Record<string, number> = {};
    properties.forEach(p => { rates[p.id] = p.monthly_rate ?? 0; });
    setPropRates(rates);
    setPropRatesDirty(false);
  }, [properties]);

  const setPropField = (field: string, value: unknown) => {
    setPropForm((f) => f ? { ...f, [field]: value } : f);
    setPropDirty(true);
  };

  const load = useCallback(async () => {
    try {
      const [c, p, inv, heroes, companyList] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
        api.get<{ items: Invoice[] }>(`/v1/invoices?customer_id=${id}`),
        api.get<Record<string, PropertyPhoto>>("/v1/photos/heroes").catch(() => ({})),
        api.get<string[]>("/v1/customers/companies").catch(() => []),
      ]);
      setCustomer(c);
      setCustForm(c);
      setProperties(p.items);
      setInvoices(inv.items);
      setHeroImages(heroes);
      setCompanies(companyList);
    } catch {
      toast.error("Failed to load client");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Auto-select first property for multi-property clients
  useEffect(() => {
    if (properties.length > 1 && !selectedPropertyId) {
      setSelectedPropertyId(properties[0].id);
    } else if (properties.length === 1) {
      setSelectedPropertyId(null);
    }
  }, [properties, selectedPropertyId]);

  const activeProperty = properties.length > 1
    ? properties.find(p => p.id === selectedPropertyId) || properties[0]
    : null;

  // Scroll to selected WF or property when switching to wfs tab
  useEffect(() => {
    if (viewTab === "wfs") {
      if (selectedWfId) {
        const timer = setTimeout(() => {
          wfRefs.current[selectedWfId]?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 100);
        return () => clearTimeout(timer);
      }
      if (scrollToPropId) {
        const timer = setTimeout(() => {
          propRefs.current[scrollToPropId]?.scrollIntoView({ behavior: "smooth", block: "start" });
          setScrollToPropId(null);
        }, 100);
        return () => clearTimeout(timer);
      }
    }
  }, [viewTab, selectedWfId, scrollToPropId]);

  // Fetch full WF data + tech assignments for all properties
  useEffect(() => {
    if (properties.length === 0) return;
    Promise.all(
      properties.map((p) => api.get<WaterFeature[]>(`/v1/water-features/property/${p.id}`).catch(() => []))
    ).then((results) => setFullBows(results.flat()));
    api.get<Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>>("/v1/routes/tech-assignments")
      .then(setTechAssignments)
      .catch(() => setTechAssignments({}));
    // Fetch per-WF profitability
    api.get<Array<{ wf_id: string; margin_pct: number; suggested_rate: number; customer_id: string }>>("/v1/profitability/gaps")
      .then((gaps) => {
        const map: Record<string, { margin_pct: number; suggested_rate: number }> = {};
        for (const g of gaps) {
          if (g.customer_id === id) {
            map[g.wf_id] = { margin_pct: g.margin_pct, suggested_rate: g.suggested_rate };
          }
        }
        setBowProfitability(map);
      })
      .catch(() => setBowProfitability({}));
  }, [properties, id]);

  const setCustField = (field: string, value: unknown) => {
    setCustForm((f) => f ? { ...f, [field]: value } : f);
    setCustDirty(true);
  };

  const handleSaveCustomer = async () => {
    if (!custForm) return;
    setCustSaving(true);
    try {
      const promises: Promise<unknown>[] = [
        api.put(`/v1/customers/${id}`, {
          first_name: custForm.first_name, last_name: custForm.last_name,
          company_name: (custForm.company_name === "__new__" ? newCompanyCustom : custForm.company_name) || null, customer_type: custForm.customer_type,
          email: custForm.email || null, phone: custForm.phone || null,
          billing_address: custForm.billing_address || null, billing_city: custForm.billing_city || null,
          billing_state: custForm.billing_state || null, billing_zip: custForm.billing_zip || null,
          service_frequency: custForm.service_frequency || null, preferred_day: custForm.preferred_day || null,
          billing_frequency: custForm.billing_frequency,
          payment_method: custForm.payment_method || null, payment_terms_days: custForm.payment_terms_days,
          difficulty_rating: custForm.difficulty_rating, notes: custForm.notes || null,
          status: custForm.status,
          is_active: custForm.status === "active",
        }),
      ];
      if (propForm && propDirty && singleProp) {
        promises.push(api.put(`/v1/properties/${singleProp.id}`, {
          address: propForm.address, city: propForm.city, state: propForm.state, zip_code: propForm.zip_code,
          gate_code: propForm.gate_code || null, access_instructions: propForm.access_instructions || null,
          dog_on_property: propForm.dog_on_property, is_locked_to_day: propForm.is_locked_to_day,
          service_day_pattern: propForm.service_day_pattern || null, notes: propForm.notes || null,
        }));
      }
      await Promise.all(promises);
      // Save property rates sequentially so customer sync is correct
      if (propRatesDirty) {
        for (const [propId, rate] of Object.entries(propRates)) {
          const orig = properties.find(p => p.id === propId);
          if (orig && (orig.monthly_rate ?? 0) !== rate) {
            await api.put(`/v1/properties/${propId}`, { monthly_rate: rate });
          }
        }
      }
      toast.success("Client updated");
      setCustDirty(false);
      setPropDirty(false);
      setPropRatesDirty(false);
      setNewCompanyCustom("");
      setEditingDetails(false);
      load();
    } catch {
      toast.error("Failed to update client");
    } finally {
      setCustSaving(false);
    }
  };

  const openRateSplit = async () => {
    try {
      const data = await api.get<typeof rateSplitData>(`/v1/profitability/allocate-rates/${id}`);
      setRateSplitData(data);
      const edits: Record<string, number> = {};
      for (const a of data?.allocations || []) {
        edits[a.wf_id] = a.proposed_rate;
      }
      setRateSplitEdits(edits);
      setShowRateSplit(true);
    } catch {
      toast.error("Failed to load rate allocation");
    }
  };

  const applyRateSplit = async () => {
    setRateSplitSaving(true);
    try {
      await api.post(`/v1/profitability/apply-rates/${id}`, { rates: rateSplitEdits });
      toast.success("Rates applied");
      setShowRateSplit(false);
      load();
    } catch {
      toast.error("Failed to apply rates");
    } finally {
      setRateSplitSaving(false);
    }
  };

  const wfsNeedRateSplit = fullWfs.length > 1 && fullWfs.some(b => b.monthly_rate == null) && (customer?.monthly_rate ?? 0) > 0;

  if (!customer || !custForm) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const TypeIcon = customer.customer_type === "commercial" ? Building2 : Home;
  const displayName = (customer as { display_name?: string }).display_name || customer.first_name;

  const handleCancelCustomer = () => {
    setCustForm(customer);
    setCustDirty(false);
  };

  const handleCancelProperty = () => {
    if (singleProp) setPropForm(singleProp);
    setPropDirty(false);
    const rates: Record<string, number> = {};
    properties.forEach(p => { rates[p.id] = p.monthly_rate ?? 0; });
    setPropRates(rates);
    setPropRatesDirty(false);
  };

  const handleExitDetails = () => {
    if (custDirty || propDirty || propRatesDirty) {
      setDiscardTarget("details");
      setShowDiscardDialog(true);
    } else {
      setEditingDetails(false);
    }
  };

  const handleDiscardAndExit = () => {
    if (discardTarget === "details") {
      setCustDirty(false);
      setPropDirty(false);
      setCustForm(customer);
      if (singleProp) setPropForm(singleProp);
      setEditingDetails(false);
    }
    setShowDiscardDialog(false);
    setDiscardTarget(null);
    load();
  };
  // --- RENDER ---
  return (
    <div className="pb-20 sm:pb-0">
      {/* Unsaved changes guard */}
      <AlertDialog open={showDiscardDialog} onOpenChange={setShowDiscardDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unsaved changes</AlertDialogTitle>
            <AlertDialogDescription>You have unsaved changes. Discard them?</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction onClick={handleDiscardAndExit} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Discard</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Back button */}
      <div className="mb-4">
        <Button variant="ghost" size="sm" className="shrink-0" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
      </div>

      {/* Two-column layout: sidebar + main */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar */}
        <div className="lg:w-72 lg:shrink-0 space-y-4">
          {/* Client card — identity + address + contact + billing */}
          <Card className="shadow-sm">
            <CardContent className="pt-4 pb-4 space-y-3">
              {/* Name + badges */}
              <div className="flex items-center gap-3">
                <TypeIcon className="h-6 w-6 text-muted-foreground shrink-0" />
                <h1 className="text-xl font-bold tracking-tight truncate flex-1">
                  {displayName}
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {customer.company_name && (
                  <Badge variant="outline" className="text-xs">{customer.company_name}</Badge>
                )}
                <Badge
                  variant={customer.status === "active" ? "default" : customer.status === "pending" ? "outline" : "secondary"}
                  className={customer.status === "pending" ? "border-amber-400 text-amber-600" : customer.status === "one_time" ? "border-blue-400 text-blue-600" : ""}
                >
                  {customer.status === "one_time" ? "One-time" : (customer.status ?? "active").charAt(0).toUpperCase() + (customer.status ?? "active").slice(1)}
                </Badge>
              </div>

              {/* Property badges — multi-property */}
              {properties.length > 1 && (
                <div className="flex flex-wrap gap-1.5 pt-1 border-t">
                  {properties.map((prop) => (
                    <button
                      key={prop.id}
                      onClick={() => setSelectedPropertyId(prop.id)}
                      className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                        selectedPropertyId === prop.id
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-background text-muted-foreground border-border hover:bg-muted"
                      }`}
                    >
                      <MapPin className="h-3 w-3 inline mr-1" />
                      {prop.name || prop.address.split(",")[0]}
                    </button>
                  ))}
                </div>
              )}

              {/* Address */}
              {properties.length === 1 && (
                <div className="text-sm space-y-0.5 pt-1 border-t">
                  <div className="flex items-start gap-1.5 pt-1.5">
                    <Link href={`/map?wf=${(properties[0].water_features?.[0]?.id) || ""}`} title="View on map">
                      <MapPin className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground hover:text-primary transition-colors" />
                    </Link>
                    <span>{properties[0].address}, {properties[0].city}, {properties[0].state} {properties[0].zip_code}</span>
                  </div>
                  {!isTech && <SiteDetails property={properties[0]} className="ml-5" />}
                </div>
              )}
              {properties.length > 1 && activeProperty && !isTech && (() => {
                const details: string[] = [];
                if (activeProperty.gate_code) details.push(`Gate: ${activeProperty.gate_code}`);
                if (activeProperty.dog_on_property) details.push("Dog on property");
                if (activeProperty.access_instructions) details.push(activeProperty.access_instructions);
                return details.length > 0 ? <SiteDetails property={activeProperty} /> : null;
              })()}

              {/* Site access — prominent for techs */}
              {isTech && properties.length >= 1 && (
                <div className="text-sm space-y-1.5 pt-1 border-t">
                  <div className="pt-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
                    <div><span className="text-muted-foreground">Gate: </span><span className="font-medium">{properties[0].gate_code || "None"}</span></div>
                    <div>{properties[0].dog_on_property ? <span className="text-amber-600 font-medium">Dog on property</span> : <span className="text-muted-foreground">No dog</span>}</div>
                  </div>
                  {properties[0].access_instructions && (
                    <div><span className="text-muted-foreground">Access: </span>{properties[0].access_instructions}</div>
                  )}
                </div>
              )}

              {/* Contact */}
              <div className="text-sm space-y-1 pt-1 border-t">
                <div className="pt-1.5"><span className="text-muted-foreground">Email: </span>{customer.email || "\u2014"}</div>
                <div><span className="text-muted-foreground">Phone: </span>{customer.phone || "\u2014"}</div>
              </div>

              {/* Billing summary */}
              {perms.canViewRates && (
                <div className="text-sm space-y-1 pt-1 border-t">
                  <div className="pt-1.5"><span className="text-muted-foreground">Rate: </span>${customer.monthly_rate.toFixed(2)}/mo</div>
                  <div>
                    <span className="text-muted-foreground">Balance: </span>
                    <span className={customer.balance > 0 ? "text-red-600 font-medium" : ""}>${customer.balance.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Nav tiles — desktop: vertical stack, mobile: horizontal scroll */}
          <div className="flex lg:flex-col gap-2 overflow-x-auto lg:overflow-visible pb-1 lg:pb-0">
            {[
              ...(isTech
                ? [
                    { key: "service" as const, icon: ClipboardCheck, label: "Service" },
                    { key: "wfs" as const, icon: Droplets, label: "Water Features" },
                    { key: "details" as const, icon: History, label: "History" },
                  ]
                : [
                    { key: "overview" as const, icon: LayoutDashboard, label: "Overview" },
                    { key: "wfs" as const, icon: Droplets, label: "Water Features" },
                    ...(perms.canViewInvoices ? [{ key: "invoices" as const, icon: Receipt, label: "Invoices" }] : []),
                  ]
              ),
            ].map((nav) => (
              <button
                key={nav.key}
                onClick={() => setViewTab(nav.key)}
                className={`flex items-center gap-3 rounded-lg border px-4 py-2 text-sm font-medium transition-colors shrink-0 lg:w-full ${
                  viewTab === nav.key
                    ? "bg-accent border-primary/30 shadow-sm font-semibold"
                    : "bg-background hover:bg-muted/50 border-border"
                }`}
              >
                <nav.icon className={`h-5 w-5 ${viewTab === nav.key ? "text-primary" : "text-muted-foreground"}`} />
                {nav.label}
                {nav.key === "invoices" && (() => {
                  const outstanding = invoices.reduce((sum, inv) => sum + inv.balance, 0);
                  return outstanding > 0
                    ? <span className={`ml-auto text-xs ${viewTab === "invoices" ? "opacity-80" : "text-red-600"}`}>${outstanding.toFixed(2)}</span>
                    : invoices.length > 0 ? <span className={`ml-auto text-xs ${viewTab === "invoices" ? "opacity-80" : "text-muted-foreground"}`}>({invoices.length})</span> : null;
                })()}
              </button>
            ))}
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0 space-y-4">

      {/* ===== SERVICE (tech default) ===== */}
      {viewTab === "service" && (() => {
        const allWfs = properties.flatMap(p => p.water_features || []);
        const sanitizerLabels: Record<string, string> = {
          liquid: "Liquid Chlorine", tabs: "Tabs (Trichlor)", granular: "Granular (Dichlor)",
          cal_hypo: "Cal-Hypo", salt: "Salt (SWG)", bromine: "Bromine", uv_ozone: "UV / Ozone",
        };
        return (
          <div className="space-y-4">
            {/* Service schedule */}
            <Card className="shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Today&apos;s Service</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                  <div><span className="text-muted-foreground">Frequency: </span><span className="capitalize">{customer.service_frequency || "weekly"}</span></div>
                  <div>
                    <span className="text-muted-foreground">Days: </span>
                    {customer.preferred_day
                      ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ")
                      : "Any"}
                  </div>
                </div>
                {customer.notes && (
                  <div className="text-sm pt-1.5 border-t">
                    <span className="text-muted-foreground">Notes: </span>{customer.notes}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Pool info for each WF — what the tech needs to know */}
            {allWfs.map((wf) => (
              <Card key={wf.id} className="shadow-sm">
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <Droplets className="h-4 w-4 text-muted-foreground" />
                    <CardTitle className="text-sm capitalize">{wf.name || wf.water_type.replace("_", " ")}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="text-sm space-y-2">
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <p className="text-xs text-muted-foreground">Gallons</p>
                      <p className="font-medium">{wf.pool_gallons ? wf.pool_gallons.toLocaleString() : "\u2014"}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Service Time</p>
                      <p className="font-medium">{wf.estimated_service_minutes} min</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Type</p>
                      <p className="font-medium capitalize">{wf.pool_type || "\u2014"}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
            {allWfs.length === 0 && (
              <Card className="shadow-sm">
                <CardContent className="py-6 text-center text-sm text-muted-foreground">
                  No water features
                </CardContent>
              </Card>
            )}

            {/* Chemical reading entry — placeholder */}
            <Card className="shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Chemical Reading</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
                  Chemical reading entry coming soon
                </div>
              </CardContent>
            </Card>

            {/* Service checklist — placeholder */}
            <Card className="shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Service Checklist</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
                  Service checklist coming soon
                </div>
              </CardContent>
            </Card>

            {/* Complete visit — placeholder */}
            <Button className="w-full h-12 text-base" disabled>
              Complete Visit
            </Button>
          </div>
        );
      })()}

      {/* ===== OVERVIEW ===== */}
      {viewTab === "overview" && (() => {
        const unpaidInvoices = invoices.filter(inv => inv.balance > 0);
        const outstandingTotal = unpaidInvoices.reduce((sum, inv) => sum + inv.balance, 0);
        const paidInvoices = invoices.filter(inv => inv.status === "paid");
        const ytdRevenue = paidInvoices.reduce((sum, inv) => sum + inv.total, 0);
        const allWfs = properties.flatMap(p => p.water_features || []);

        return (
          <div className="space-y-4">
            {/* Metric cards */}
            <div className={`grid grid-cols-2 ${perms.canViewRates ? "lg:grid-cols-4" : "lg:grid-cols-2"} gap-3`}>
              {perms.canViewRates && (
                <Link href={`/profitability/${customer.id}`}>
                  <Card className="shadow-sm hover:bg-muted/50 transition-colors cursor-pointer">
                    <CardContent className="pt-3 pb-3">
                      <div className="flex items-center gap-2 mb-1">
                        <DollarSign className="h-4 w-4 text-muted-foreground" />
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Monthly Rate</p>
                      </div>
                      <p className="text-2xl font-bold">${customer.monthly_rate.toFixed(2)}</p>
                    </CardContent>
                  </Card>
                </Link>
              )}
              {perms.canViewBalance && (
                <Card className={`shadow-sm hover:bg-muted/50 transition-colors cursor-pointer ${outstandingTotal > 0 ? "border-red-200" : ""}`} onClick={() => setViewTab("invoices")}>
                  <CardContent className="pt-3 pb-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Receipt className="h-4 w-4 text-muted-foreground" />
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Balance</p>
                    </div>
                    <p className={`text-2xl font-bold ${outstandingTotal > 0 ? "text-red-600" : ""}`}>
                      ${customer.balance.toFixed(2)}
                    </p>
                  </CardContent>
                </Card>
              )}
              <Card className="shadow-sm">
                <CardContent className="pt-3 pb-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Last Service</p>
                  </div>
                  <p className="text-2xl font-bold text-muted-foreground">&mdash;</p>
                  <p className="text-xs text-muted-foreground">No visits recorded</p>
                </CardContent>
              </Card>
              <Card className="shadow-sm">
                <CardContent className="pt-3 pb-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Next Service</p>
                  </div>
                  <p className="text-2xl font-bold text-muted-foreground">&mdash;</p>
                  <p className="text-xs text-muted-foreground">No schedule set</p>
                </CardContent>
              </Card>
            </div>

            {/* Two-column: outstanding invoices + pools */}
            <div className={`grid grid-cols-1 ${perms.canViewInvoices ? "lg:grid-cols-2" : ""} gap-4`}>
              {/* Outstanding invoices */}
              {perms.canViewInvoices && (
                <Card className="shadow-sm py-4 gap-3 h-full max-h-64 lg:max-h-none hover:bg-muted/50 transition-colors cursor-pointer" onClick={() => setViewTab("invoices")}>
                  <CardHeader className="pb-0">
                    <CardTitle className="text-sm">Invoices</CardTitle>
                  </CardHeader>
                  <CardContent className="overflow-y-auto">
                    {invoices.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-3">No invoices</p>
                    ) : (
                      <div className="space-y-1.5">
                        {invoices.map((inv) => (
                          <div key={inv.id} className="flex items-center justify-between text-sm">
                            <div className="flex items-center gap-2 min-w-0">
                              <Link href={`/invoices/${inv.id}`} className="font-medium hover:underline shrink-0">{inv.invoice_number}</Link>
                              <span className="text-muted-foreground text-xs">{inv.issue_date}</span>
                            </div>
                            <span className={`shrink-0 ml-2 ${inv.balance > 0 ? "text-red-600 font-medium" : "text-muted-foreground"}`}>
                              ${inv.total.toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Water Features summary */}
              <Card className="shadow-sm py-4 gap-3 h-full">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Water Features</CardTitle>
                </CardHeader>
                <CardContent>
                  {(() => {
                    const visibleProps = activeProperty ? [activeProperty] : properties;
                    return (
                    <div className="space-y-3">
                      {visibleProps.map((prop) => {
                        const wfs = prop.water_features || [];
                        const hero = heroImages[prop.id];
                        return (
                          <div key={prop.id}>
                            {hero && (
                              <img
                                src={`${API_BASE}${hero.url}`}
                                alt="Property photo"
                                className="w-full h-28 object-cover rounded-md border mb-2"
                              />
                            )}
                            {/* Property-level service info */}
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground mb-2 px-1">
                              <span><span className="font-medium">Freq:</span> <span className="capitalize">{customer.service_frequency || "weekly"}</span></span>
                              <span><span className="font-medium">Days:</span> {customer.preferred_day
                                ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ")
                                : "Any"}</span>
                              {prop.gate_code && <span><span className="font-medium">Gate:</span> {prop.gate_code}</span>}
                              {prop.dog_on_property && <span className="text-amber-600 font-medium">Dog on property</span>}
                            </div>
                            <div className="space-y-2">
                              {wfs.length === 0 && (
                                <div className="bg-muted/50 rounded-md p-2.5 cursor-pointer hover:bg-muted/80 transition-colors" onClick={() => { setScrollToPropId(prop.id); setViewTab("wfs"); }}>
                                  <p className="text-xs text-muted-foreground">No water features — <span className="text-primary">add one</span></p>
                                </div>
                              )}
                              {wfs.map((wf) => (
                                <div key={wf.id} className="bg-muted/50 rounded-md p-2.5 cursor-pointer hover:bg-muted/80 transition-colors" onClick={() => { setSelectedBowId(wf.id); setViewTab("wfs"); }}>
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <Droplets className="h-3.5 w-3.5 text-blue-500" />
                                    <span className="font-medium text-sm capitalize">{wf.name || wf.water_type.replace("_", " ")}</span>
                                    {wf.pool_type && (
                                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 capitalize ml-auto">{wf.pool_type}</Badge>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-3 gap-x-3 text-xs">
                                    <div>
                                      <span className="text-muted-foreground">Gallons</span>
                                      <p className="font-medium">{wf.pool_gallons ? wf.pool_gallons.toLocaleString() : "\u2014"}</p>
                                    </div>
                                    <div>
                                      <span className="text-muted-foreground">Service</span>
                                      <p className="font-medium">{wf.estimated_service_minutes} min</p>
                                    </div>
                                    {wf.monthly_rate != null ? (
                                      <div>
                                        <span className="text-muted-foreground">Rate</span>
                                        <p className="font-medium">${wf.monthly_rate.toFixed(2)}</p>
                                      </div>
                                    ) : wf.pool_sqft ? (
                                      <div>
                                        <span className="text-muted-foreground">Size</span>
                                        <p className="font-medium">{wf.pool_sqft.toLocaleString()} ft²</p>
                                      </div>
                                    ) : (
                                      <div />
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    );
                  })()}
                </CardContent>
              </Card>
            </div>

            {/* ===== DETAILS (inline in overview) ===== */}
            <Card className={`shadow-sm py-4 gap-3 ${editingDetails ? `bg-muted/50 ${custDirty || propDirty || propRatesDirty ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-primary"}` : ""}`}>
              <CardHeader className="pb-0">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Details</CardTitle>
                  {!editingDetails && perms.canEditCustomers && (
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setEditingDetails(true)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {editingDetails && (
                    <div className="flex gap-1.5">
                      {(custDirty || propDirty || propRatesDirty) && (
                        <>
                          <Button variant="default" size="sm" className="h-8 px-3 text-xs" onClick={handleSaveCustomer} disabled={custSaving}>
                            {custSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                          </Button>
                          <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs" onClick={() => { handleCancelCustomer(); handleCancelProperty(); }}>
                            Cancel
                          </Button>
                        </>
                      )}
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={handleExitDetails}>
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {!editingDetails ? (
                  /* --- Details View --- */
                  <div className="space-y-4">
                    {/* Billing — only for roles that can see rates */}
                    {perms.canViewRates && (
                      <Card className="shadow-sm py-4 gap-3">
                        <CardHeader className="pb-0">
                          <CardTitle className="text-sm">Billing</CardTitle>
                        </CardHeader>
                        <CardContent className="text-sm space-y-2">
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                            <div><span className="text-muted-foreground">Rate: </span>${customer.monthly_rate.toFixed(2)}/mo</div>
                            <div><span className="text-muted-foreground">Terms: </span>{customer.payment_terms_days} days</div>
                            <div><span className="text-muted-foreground">Frequency: </span><span className="capitalize">{customer.billing_frequency}</span></div>
                            <div><span className="text-muted-foreground">Payment: </span>{customer.payment_method || "\u2014"}</div>
                          </div>
                          <div className="pt-1.5 border-t">
                            <p className="text-xs text-muted-foreground mb-1">Billing Address</p>
                            <p>{customer.billing_address ? `${customer.billing_address}, ${customer.billing_city}, ${customer.billing_state} ${customer.billing_zip}` : "Same as service address"}</p>
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {/* Notes — always present */}
                    <Card className="shadow-sm py-4 gap-3">
                      <CardHeader className="pb-0">
                        <CardTitle className="text-sm">Notes</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {customer.notes ? (
                          <p className="text-sm whitespace-pre-wrap">{customer.notes}</p>
                        ) : (
                          <p className="text-sm text-muted-foreground">No notes</p>
                        )}
                      </CardContent>
                    </Card>
                  </div>
                ) : (
                  /* --- Details Edit --- */
                  <div className="space-y-4">
                    {/* Client tile — identity + address */}
                    <Card className="bg-background">
                      <CardContent className="pt-3 pb-3 space-y-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Client</p>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1.5">
                            <Label className="text-xs">Type</Label>
                            <Select value={custForm.customer_type} onValueChange={(v) => setCustField("customer_type", v)}>
                              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="residential">Residential</SelectItem>
                                <SelectItem value="commercial">Commercial</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs">Status</Label>
                            <Select value={custForm.status ?? "active"} onValueChange={(v) => setCustField("status", v)}>
                              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="active">Active</SelectItem>
                                <SelectItem value="inactive">Inactive</SelectItem>
                                <SelectItem value="pending">Pending</SelectItem>
                                <SelectItem value="one_time">One-time</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1.5">
                            <Label className="text-xs">{custForm.customer_type === "commercial" ? "Name" : "First Name"}</Label>
                            <Input value={custForm.first_name} onChange={(e) => setCustField("first_name", e.target.value)} className="h-9" />
                          </div>
                          {custForm.customer_type !== "commercial" ? (
                            <div className="space-y-1.5">
                              <Label className="text-xs">Last Name</Label>
                              <Input value={custForm.last_name} onChange={(e) => setCustField("last_name", e.target.value)} className="h-9" />
                            </div>
                          ) : (
                            <div className="space-y-1.5">
                              <Label className="text-xs">Company</Label>
                              {companies.length > 0 ? (
                                <>
                                  <Select
                                    value={custForm.company_name === "__new__" ? "__new__" : (custForm.company_name || "__none__")}
                                    onValueChange={(v) => {
                                      if (v === "__none__") { setCustField("company_name", ""); setNewCompanyCustom(""); }
                                      else if (v === "__new__") { setCustField("company_name", "__new__"); }
                                      else { setCustField("company_name", v); setNewCompanyCustom(""); }
                                    }}
                                  >
                                    <SelectTrigger className="h-9"><SelectValue placeholder="Select company..." /></SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="__none__">None</SelectItem>
                                      {companies.map(name => (
                                        <SelectItem key={name} value={name}>{name}</SelectItem>
                                      ))}
                                      <SelectItem value="__new__">+ New company...</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  {custForm.company_name === "__new__" && (
                                    <Input
                                      placeholder="New company name..."
                                      value={newCompanyCustom}
                                      onChange={(e) => setNewCompanyCustom(e.target.value)}
                                      className="h-9"
                                    />
                                  )}
                                </>
                              ) : (
                                <Input value={custForm.company_name ?? ""} onChange={(e) => setCustField("company_name", e.target.value)} className="h-9" />
                              )}
                            </div>
                          )}
                        </div>
                        {/* Service address inline */}
                        {singleProp && propForm ? (
                          <>
                            <div className="space-y-1.5">
                              <Label className="text-xs">Address</Label>
                              <Input value={propForm.address} onChange={(e) => setPropField("address", e.target.value)} className="h-9" />
                            </div>
                            <div className="grid grid-cols-3 gap-2">
                              <div className="space-y-1.5">
                                <Label className="text-xs">City</Label>
                                <Input value={propForm.city} onChange={(e) => setPropField("city", e.target.value)} className="h-9" />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">State</Label>
                                <Input value={propForm.state} onChange={(e) => setPropField("state", e.target.value)} className="h-9" />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">Zip</Label>
                                <Input value={propForm.zip_code} onChange={(e) => setPropField("zip_code", e.target.value)} className="h-9" />
                              </div>
                            </div>
                          </>
                        ) : !singleProp && (
                          <p className="text-xs text-muted-foreground">
                            {properties.length} properties — <button type="button" className="text-primary hover:underline" onClick={() => setViewTab("wfs")}>edit on Water Features tab</button>
                          </p>
                        )}
                      </CardContent>
                    </Card>

                    {/* Contact tile */}
                    <Card className="bg-background">
                      <CardContent className="pt-3 pb-3 space-y-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Contact</p>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1.5">
                            <Label className="text-xs">Email</Label>
                            <Input type="email" value={custForm.email ?? ""} onChange={(e) => setCustField("email", e.target.value)} className="h-9" />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs">Phone</Label>
                            <Input value={custForm.phone ?? ""} onChange={(e) => setCustField("phone", e.target.value)} className="h-9" />
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    {/* Billing tile — only for roles that can see rates */}
                    {perms.canViewRates && <Card className="bg-background">
                      <CardContent className="pt-3 pb-3 space-y-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Billing</p>
                        {properties.length <= 1 ? (
                          <div className="grid grid-cols-2 gap-2">
                            <div className="space-y-1.5">
                              <Label className="text-xs">Monthly Rate</Label>
                              <Input type="number" step="0.01" value={propRates[properties[0]?.id] ?? ""} onChange={(e) => { setPropRates(prev => ({ ...prev, [properties[0]?.id]: parseFloat(e.target.value) || 0 })); setPropRatesDirty(true); }} className="h-9" />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs">Payment Terms (days)</Label>
                              <Input type="number" value={custForm.payment_terms_days} onChange={(e) => setCustField("payment_terms_days", parseInt(e.target.value) || 30)} className="h-9" />
                            </div>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <div className="grid grid-cols-2 gap-2">
                              <div className="space-y-1.5">
                                <Label className="text-xs">Total Rate</Label>
                                <p className="h-9 flex items-center text-sm font-medium">${Object.values(propRates).reduce((s, r) => s + r, 0).toFixed(2)}/mo</p>
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">Payment Terms (days)</Label>
                                <Input type="number" value={custForm.payment_terms_days} onChange={(e) => setCustField("payment_terms_days", parseInt(e.target.value) || 30)} className="h-9" />
                              </div>
                            </div>
                            {properties.map(prop => (
                              <div key={prop.id} className="flex items-center gap-2">
                                <Label className="text-xs flex-1 min-w-0 truncate">{prop.name || prop.address}</Label>
                                <div className="flex items-center gap-1">
                                  <span className="text-xs text-muted-foreground">$</span>
                                  <Input type="number" step="0.01" value={propRates[prop.id] ?? ""} onChange={(e) => { setPropRates(prev => ({ ...prev, [prop.id]: parseFloat(e.target.value) || 0 })); setPropRatesDirty(true); }} className="h-8 w-28 text-sm text-right" />
                                  <span className="text-xs text-muted-foreground">/mo</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1.5">
                            <Label className="text-xs">Billing Frequency</Label>
                            <Select value={custForm.billing_frequency} onValueChange={(v) => setCustField("billing_frequency", v)}>
                              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="monthly">Monthly</SelectItem>
                                <SelectItem value="quarterly">Quarterly</SelectItem>
                                <SelectItem value="annually">Annually</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs">Payment Method</Label>
                            <Input value={custForm.payment_method ?? ""} onChange={(e) => setCustField("payment_method", e.target.value)} placeholder="check, cc, ach..." className="h-9" />
                          </div>
                        </div>
                        {/* Billing address with "same as" toggle */}
                        {singleProp && propForm && (() => {
                          const sameAddr = custForm.billing_address === propForm.address
                            && custForm.billing_city === propForm.city
                            && custForm.billing_state === propForm.state
                            && custForm.billing_zip === propForm.zip_code;
                          const isSame = !custForm.billing_address || sameAddr;
                          return (
                            <>
                              <div className="flex items-center gap-2 pt-1">
                                <Switch checked={isSame} onCheckedChange={(v) => {
                                  if (v) {
                                    setCustField("billing_address", propForm.address);
                                    setCustField("billing_city", propForm.city);
                                    setCustField("billing_state", propForm.state);
                                    setCustField("billing_zip", propForm.zip_code);
                                  }
                                }} />
                                <Label className="text-xs">Same as service address</Label>
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">Billing Address</Label>
                                <Input value={isSame ? propForm.address : (custForm.billing_address ?? "")} onChange={(e) => setCustField("billing_address", e.target.value)} className="h-9" disabled={isSame} />
                              </div>
                              <div className="grid grid-cols-3 gap-2">
                                <div className="space-y-1.5">
                                  <Label className="text-xs">City</Label>
                                  <Input value={isSame ? propForm.city : (custForm.billing_city ?? "")} onChange={(e) => setCustField("billing_city", e.target.value)} className="h-9" disabled={isSame} />
                                </div>
                                <div className="space-y-1.5">
                                  <Label className="text-xs">State</Label>
                                  <Input value={isSame ? propForm.state : (custForm.billing_state ?? "")} onChange={(e) => setCustField("billing_state", e.target.value)} className="h-9" disabled={isSame} />
                                </div>
                                <div className="space-y-1.5">
                                  <Label className="text-xs">Zip</Label>
                                  <Input value={isSame ? propForm.zip_code : (custForm.billing_zip ?? "")} onChange={(e) => setCustField("billing_zip", e.target.value)} className="h-9" disabled={isSame} />
                                </div>
                              </div>
                            </>
                          );
                        })()}
                        {/* Fallback: no property, show billing address fields directly */}
                        {!singleProp && (
                          <>
                            <div className="space-y-1.5">
                              <Label className="text-xs">Billing Address</Label>
                              <Input value={custForm.billing_address ?? ""} onChange={(e) => setCustField("billing_address", e.target.value)} className="h-9" />
                            </div>
                            <div className="grid grid-cols-3 gap-2">
                              <div className="space-y-1.5">
                                <Label className="text-xs">City</Label>
                                <Input value={custForm.billing_city ?? ""} onChange={(e) => setCustField("billing_city", e.target.value)} className="h-9" />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">State</Label>
                                <Input value={custForm.billing_state ?? ""} onChange={(e) => setCustField("billing_state", e.target.value)} className="h-9" />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">Zip</Label>
                                <Input value={custForm.billing_zip ?? ""} onChange={(e) => setCustField("billing_zip", e.target.value)} className="h-9" />
                              </div>
                            </div>
                          </>
                        )}
                      </CardContent>
                    </Card>}

                    {/* Service tile — schedule + access details */}
                    <Card className="bg-background">
                      <CardContent className="pt-3 pb-3 space-y-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Service</p>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1.5">
                            <Label className="text-xs">Frequency</Label>
                            <Select value={custForm.service_frequency ?? "weekly"} onValueChange={(v) => setCustField("service_frequency", v)}>
                              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="weekly">Weekly</SelectItem>
                                <SelectItem value="biweekly">Biweekly</SelectItem>
                                <SelectItem value="monthly">Monthly</SelectItem>
                                <SelectItem value="on_call">On Call</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs">Service Days</Label>
                            <div className="flex flex-wrap gap-1">
                              {["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"].map((day) => {
                                const days = (custForm.preferred_day ?? "").split(",").filter(Boolean);
                                const active = days.includes(day);
                                return (
                                  <Button key={day} type="button" variant={active ? "default" : "outline"} size="sm" className="h-7 px-2 text-xs"
                                    onClick={() => { const next = active ? days.filter(d => d !== day) : [...days, day]; setCustField("preferred_day", next.length ? next.join(",") : null); }}>
                                    {day.slice(0, 3).charAt(0).toUpperCase() + day.slice(1, 3)}
                                  </Button>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                        {/* Access details from property */}
                        {singleProp && propForm ? (
                          <>
                            <div className="grid grid-cols-2 gap-2">
                              <div className="space-y-1.5">
                                <Label className="text-xs">Gate Code</Label>
                                <Input value={propForm.gate_code ?? ""} onChange={(e) => setPropField("gate_code", e.target.value)} className="h-9" />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">Access Instructions</Label>
                                <Input value={propForm.access_instructions ?? ""} onChange={(e) => setPropField("access_instructions", e.target.value)} className="h-9" />
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-x-6 gap-y-2">
                              <div className="flex items-center gap-2">
                                <Switch checked={propForm.dog_on_property} onCheckedChange={(v) => setPropField("dog_on_property", v)} />
                                <Label className="text-xs">Dog on Property</Label>
                              </div>
                              <div className="flex items-center gap-2">
                                <Switch checked={propForm.is_locked_to_day} onCheckedChange={(v) => setPropField("is_locked_to_day", v)} />
                                <Label className="text-xs">Locked to Day</Label>
                              </div>
                            </div>
                          </>
                        ) : !singleProp && (
                          <p className="text-xs text-muted-foreground">
                            Site access — <button type="button" className="text-primary hover:underline" onClick={() => setViewTab("wfs")}>edit per-property on Water Features tab</button>
                          </p>
                        )}
                        <div className="space-y-1.5">
                          <Label className="text-xs">Notes</Label>
                          <Textarea value={custForm.notes ?? ""} onChange={(e) => setCustField("notes", e.target.value)} rows={2} />
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        );
      })()}

      {/* ===== WFS TAB ===== */}
      {viewTab === "wfs" && (
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" className="shrink-0" onClick={() => { setSelectedBowId(null); setViewTab("overview"); }}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back to Overview
            </Button>
            {perms.canEditCustomers && (
              <AddPropertyForm customerId={id} onCreated={load} />
            )}
          </div>
          {wfsNeedRateSplit && (
            <div className="flex items-center justify-between gap-3 px-4 py-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200/50 dark:border-amber-800/50 rounded-lg">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                <span className="text-sm">
                  <span className="font-medium">Rate not split across water features.</span>
                  <span className="text-muted-foreground ml-1">Account rate is ${customer?.monthly_rate?.toFixed(0)}/mo but individual water features have no rates assigned.</span>
                </span>
              </div>
              <Button size="sm" className="shrink-0" onClick={openRateSplit}>Split Rates</Button>
            </div>
          )}

          {/* Rate Split Dialog */}
          {showRateSplit && rateSplitData && (
            <Card className="shadow-sm border-primary/30">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold">Split Rate Across Water Features</h3>
                    <p className="text-xs text-muted-foreground">
                      Total: ${rateSplitData.total_rate.toFixed(2)}/mo · Method: {rateSplitData.method || "type weight"}
                    </p>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => setShowRateSplit(false)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="space-y-2">
                  {rateSplitData.allocations.map((a) => (
                    <div key={a.wf_id} className="flex items-center gap-3 bg-muted/50 rounded-md px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{a.wf_name || a.water_type}</p>
                        <p className="text-xs text-muted-foreground capitalize">{a.water_type}{a.gallons ? ` · ${a.gallons.toLocaleString()} gal` : ""}</p>
                      </div>
                      {a.current_rate != null && (
                        <span className="text-xs text-muted-foreground">was ${a.current_rate.toFixed(0)}</span>
                      )}
                      <div className="flex items-center gap-1">
                        <span className="text-sm text-muted-foreground">$</span>
                        <Input
                          type="number"
                          value={rateSplitEdits[a.wf_id] ?? a.proposed_rate}
                          onChange={(e) => setRateSplitEdits(prev => ({ ...prev, [a.wf_id]: parseFloat(e.target.value) || 0 }))}
                          className="w-24 h-8 text-sm text-right"
                        />
                        <span className="text-xs text-muted-foreground">/mo</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between mt-3 pt-3 border-t">
                  <p className="text-xs text-muted-foreground">
                    Total: ${Object.values(rateSplitEdits).reduce((s, v) => s + v, 0).toFixed(2)}/mo
                    {Math.abs(Object.values(rateSplitEdits).reduce((s, v) => s + v, 0) - rateSplitData.total_rate) > 0.01 && (
                      <span className="text-amber-600 ml-2">
                        ({Object.values(rateSplitEdits).reduce((s, v) => s + v, 0) > rateSplitData.total_rate ? "+" : ""}
                        {(Object.values(rateSplitEdits).reduce((s, v) => s + v, 0) - rateSplitData.total_rate).toFixed(2)} from account rate)
                      </span>
                    )}
                  </p>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setShowRateSplit(false)}>Cancel</Button>
                    <Button size="sm" onClick={applyRateSplit} disabled={rateSplitSaving}>
                      {rateSplitSaving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                      Apply Rates
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {properties.length === 0 && (
            <Card className="shadow-sm">
              <CardContent className="py-6">
                <p className="text-center text-muted-foreground text-sm">No service location yet</p>
              </CardContent>
            </Card>
          )}
          {(activeProperty ? [activeProperty] : properties).map((prop) => {
            const propWfs = fullWfs.filter((b) => b.property_id === prop.id);
            const summaryWfs = prop.water_features || [];
            const wfs = propWfs.length > 0 ? propWfs : summaryWfs;
            const hero = heroImages[prop.id];
            const hasBows = wfs.length > 0;
            const firstTech = techAssignments[prop.id]?.[0];

            return (
              <div key={prop.id} ref={(el) => { propRefs.current[prop.id] = el; }} className="space-y-4">
                {/* Property header with satellite */}
                {hero && (
                  <div className="relative rounded-lg overflow-hidden border">
                    <img
                      src={`${API_BASE}${hero.url}`}
                      alt="Property photo"
                      className="w-full h-40 object-cover"
                    />
                  </div>
                )}

                {/* Property site details — address, gate, dog, access */}
                <PropertySiteDetails
                  property={prop}
                  perms={perms}
                  showAddress={properties.length > 1}
                  onUpdated={load}
                />

                {/* WF Tiles */}
                {hasBows ? (
                  wfs.map((wf) => {
                    const isFull = "pump_type" in wf;
                    const fullBow = isFull ? (wf as WaterFeature) : null;
                    if (fullBow) {
                      return (
                        <div
                          key={wf.id}
                          ref={(el) => { wfRefs.current[wf.id] = el; }}
                          className={`rounded-lg transition-all duration-500 ${selectedWfId === wf.id ? "ring-2 ring-primary ring-offset-2" : ""}`}
                        >
                          <WfTile
                            wf={fullBow as WfTileWF}
                            propertyId={prop.id}
                            perms={perms}
                            techAssignment={firstTech as TechAssignment | undefined}
                            marginPct={wfProfitability[wf.id]?.margin_pct ?? null}
                            suggestedRate={wfProfitability[wf.id]?.suggested_rate ?? null}
                            customerType={customer?.customer_type}
                            collapsed={selectedWfId !== null && selectedWfId !== wf.id}
                            onExpand={() => setSelectedBowId(wf.id)}
                            onUpdated={load}
                            onDeleted={load}
                          />
                        </div>
                      );
                    }
                    return null;
                  })
                ) : (
                  <p className="text-center text-muted-foreground py-4 text-sm">No water features yet</p>
                )}

                {/* Add Water Feature button per property */}
                {perms.canEditCustomers && (
                  <AddWfForm propertyId={prop.id} customerType={customer?.customer_type} onCreated={load} />
                )}
              </div>
            );
          })}

          {/* Visit history placeholder */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Visit History</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                Visit history will appear after 3+ service visits
              </div>
            </CardContent>
          </Card>

          {/* Chemical trends placeholder */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Chemical Trends</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                Chemical trends will appear after readings are recorded
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ===== INVOICES TAB ===== */}
      {viewTab === "invoices" && perms.canViewInvoices && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Invoices</CardTitle>
          </CardHeader>
          <CardContent>
            {invoices.length === 0 ? (
              <p className="text-center text-muted-foreground py-4 text-sm">No invoices yet</p>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-100 dark:bg-slate-800">
                      <TableHead className="text-xs font-medium uppercase tracking-wide">Invoice #</TableHead>
                      <TableHead className="hidden sm:table-cell text-xs font-medium uppercase tracking-wide">Subject</TableHead>
                      <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                      <TableHead className="hidden sm:table-cell text-xs font-medium uppercase tracking-wide">Issue Date</TableHead>
                      <TableHead className="text-right text-xs font-medium uppercase tracking-wide">Total</TableHead>
                      <TableHead className="text-right text-xs font-medium uppercase tracking-wide">Balance</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoices.map((inv, i) => (
                      <TableRow key={inv.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                        <TableCell>
                          <Link href={`/invoices/${inv.id}`} className="font-medium hover:underline">{inv.invoice_number}</Link>
                        </TableCell>
                        <TableCell className="text-muted-foreground hidden sm:table-cell">{inv.subject || "\u2014"}</TableCell>
                        <TableCell>
                          <Badge
                            variant={inv.status === "paid" ? "default" : inv.status === "overdue" ? "destructive" : "secondary"}
                            className={inv.status === "paid" ? "bg-green-600" : inv.status === "sent" ? "border-blue-400 text-blue-600" : ""}
                          >{inv.status.replace("_", " ")}</Badge>
                        </TableCell>
                        <TableCell className="hidden sm:table-cell">{inv.issue_date}</TableCell>
                        <TableCell className="text-right">${inv.total.toFixed(2)}</TableCell>
                        <TableCell className={`text-right ${inv.balance > 0 ? "text-red-600 font-medium" : ""}`}>${inv.balance.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
        </div>
      </div>
    </div>
  );
}
