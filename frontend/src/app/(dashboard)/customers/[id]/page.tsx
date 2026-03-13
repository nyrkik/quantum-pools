"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter } from "next/navigation";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Plus,
  MapPin,
  Ruler,
  Building2,
  Home,
  Pencil,
  Save,
  X,
  Trash2,
  Loader2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import Link from "next/link";

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
  notes: string | null;
  is_active: boolean;
  property_count: number;
  created_at: string;
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
  estimated_service_minutes: number;
  is_locked_to_day: boolean;
  service_day_pattern: string | null;
  notes: string | null;
  is_active: boolean;
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

// --- Helpers ---
const numOrNull = (v: string) => { const n = parseFloat(v); return isNaN(n) ? null : n; };
const intOrNull = (v: string) => { const n = parseInt(v); return isNaN(n) ? null : n; };

// --- Property Edit Card (collapsible) ---
function PropertyEditCard({
  property,
  onSave,
  onDelete,
}: {
  property: Property;
  onSave: (data: Record<string, unknown>) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState({ ...property });
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const set = (field: string, value: unknown) => {
    setForm((f) => ({ ...f, [field]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({
        name: form.name || null,
        address: form.address, city: form.city, state: form.state, zip_code: form.zip_code,
        pool_type: form.pool_type || null, pool_gallons: form.pool_gallons, pool_sqft: form.pool_sqft,
        pool_surface: form.pool_surface || null, pool_length_ft: form.pool_length_ft,
        pool_width_ft: form.pool_width_ft, pool_depth_shallow: form.pool_depth_shallow,
        pool_depth_deep: form.pool_depth_deep, pool_depth_avg: form.pool_depth_avg,
        pool_shape: form.pool_shape || null, has_spa: form.has_spa, has_water_feature: form.has_water_feature,
        pump_type: form.pump_type || null, filter_type: form.filter_type || null,
        heater_type: form.heater_type || null, chlorinator_type: form.chlorinator_type || null,
        automation_system: form.automation_system || null, gate_code: form.gate_code || null,
        access_instructions: form.access_instructions || null, dog_on_property: form.dog_on_property,
        estimated_service_minutes: form.estimated_service_minutes,
        is_locked_to_day: form.is_locked_to_day, service_day_pattern: form.service_day_pattern || null,
        notes: form.notes || null, is_active: form.is_active,
      });
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <button
            className="flex items-center gap-2 min-w-0 flex-1 text-left"
            onClick={() => setExpanded(!expanded)}
          >
            <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{form.name || form.address}</p>
              <p className="text-xs text-muted-foreground">{form.name ? form.address + ", " : ""}{form.city}, {form.state} {form.zip_code}</p>
            </div>
            {expanded ? <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />}
          </button>
          <div className="flex gap-1 shrink-0 ml-2">
            {dirty && (
              <Button variant="default" size="icon" className="h-8 w-8" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              </Button>
            )}
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete property?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete {form.address}. This cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={onDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-4 pt-2">
          {/* Name & Address */}
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Name</Label>
              <Input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Big Pool, Main Pool, Spa" className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Street Address</Label>
              <Input value={form.address} onChange={(e) => set("address", e.target.value)} className="h-9" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">City</Label>
                <Input value={form.city} onChange={(e) => set("city", e.target.value)} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">State</Label>
                <Input value={form.state} onChange={(e) => set("state", e.target.value)} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Zip</Label>
                <Input value={form.zip_code} onChange={(e) => set("zip_code", e.target.value)} className="h-9" />
              </div>
            </div>
          </div>

          {/* Pool */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Pool</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Type</Label>
                <Select value={form.pool_type ?? ""} onValueChange={(v) => set("pool_type", v || null)}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Select..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="commercial">Commercial</SelectItem>
                    <SelectItem value="residential">Residential</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Surface</Label>
                <Select value={form.pool_surface ?? ""} onValueChange={(v) => set("pool_surface", v || null)}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Select..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="gunite">Gunite</SelectItem>
                    <SelectItem value="plaster">Plaster</SelectItem>
                    <SelectItem value="pebble">Pebble</SelectItem>
                    <SelectItem value="vinyl">Vinyl</SelectItem>
                    <SelectItem value="fiberglass">Fiberglass</SelectItem>
                    <SelectItem value="tile">Tile</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Shape</Label>
                <Select value={form.pool_shape ?? ""} onValueChange={(v) => set("pool_shape", v || null)}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Select..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="rectangle">Rectangle</SelectItem>
                    <SelectItem value="oval">Oval</SelectItem>
                    <SelectItem value="round">Round</SelectItem>
                    <SelectItem value="kidney">Kidney</SelectItem>
                    <SelectItem value="L-shape">L-Shape</SelectItem>
                    <SelectItem value="freeform">Freeform</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Gallons</Label>
                <Input type="number" value={form.pool_gallons ?? ""} onChange={(e) => set("pool_gallons", intOrNull(e.target.value))} className="h-9" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Sqft</Label>
                <Input type="number" step="0.1" value={form.pool_sqft ?? ""} onChange={(e) => set("pool_sqft", numOrNull(e.target.value))} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Length (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_length_ft ?? ""} onChange={(e) => set("pool_length_ft", numOrNull(e.target.value))} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Width (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_width_ft ?? ""} onChange={(e) => set("pool_width_ft", numOrNull(e.target.value))} className="h-9" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Shallow (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_depth_shallow ?? ""} onChange={(e) => set("pool_depth_shallow", numOrNull(e.target.value))} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Deep (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_depth_deep ?? ""} onChange={(e) => set("pool_depth_deep", numOrNull(e.target.value))} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Avg (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_depth_avg ?? ""} onChange={(e) => set("pool_depth_avg", numOrNull(e.target.value))} className="h-9" />
              </div>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              <div className="flex items-center gap-2">
                <Switch checked={form.has_spa} onCheckedChange={(v) => set("has_spa", v)} />
                <Label className="text-xs">Spa</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={form.has_water_feature} onCheckedChange={(v) => set("has_water_feature", v)} />
                <Label className="text-xs">Water Feature</Label>
              </div>
            </div>
          </div>

          {/* Equipment */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Equipment</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Pump</Label>
                <Input value={form.pump_type ?? ""} onChange={(e) => set("pump_type", e.target.value)} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Filter</Label>
                <Input value={form.filter_type ?? ""} onChange={(e) => set("filter_type", e.target.value)} className="h-9" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Heater</Label>
                <Input value={form.heater_type ?? ""} onChange={(e) => set("heater_type", e.target.value)} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Chlorinator</Label>
                <Input value={form.chlorinator_type ?? ""} onChange={(e) => set("chlorinator_type", e.target.value)} className="h-9" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Automation</Label>
              <Input value={form.automation_system ?? ""} onChange={(e) => set("automation_system", e.target.value)} className="h-9" />
            </div>
          </div>

          {/* Access */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Access & Service</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Gate Code</Label>
                <Input value={form.gate_code ?? ""} onChange={(e) => set("gate_code", e.target.value)} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Service Time (min)</Label>
                <Input type="number" value={form.estimated_service_minutes} onChange={(e) => set("estimated_service_minutes", parseInt(e.target.value) || 30)} className="h-9" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Access Instructions</Label>
              <Textarea value={form.access_instructions ?? ""} onChange={(e) => set("access_instructions", e.target.value)} rows={2} />
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              <div className="flex items-center gap-2">
                <Switch checked={form.dog_on_property} onCheckedChange={(v) => set("dog_on_property", v)} />
                <Label className="text-xs">Dog</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={form.is_locked_to_day} onCheckedChange={(v) => set("is_locked_to_day", v)} />
                <Label className="text-xs">Locked to Day</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={form.is_active} onCheckedChange={(v) => set("is_active", v)} />
                <Label className="text-xs">Active</Label>
              </div>
            </div>
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <Label className="text-xs">Notes</Label>
            <Textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2} />
          </div>

          {/* Save button at bottom of expanded card */}
          {dirty && (
            <Button onClick={handleSave} disabled={saving} className="w-full h-10">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Save className="h-4 w-4 mr-1.5" />Save Property</>}
            </Button>
          )}
        </CardContent>
      )}
    </Card>
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
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [editing, setEditing] = useState(false);
  const [activeTab, setActiveTab] = useState("properties");

  // Customer edit form state
  const [custForm, setCustForm] = useState<Customer | null>(null);
  const [custSaving, setCustSaving] = useState(false);
  const [custDirty, setCustDirty] = useState(false);

  // Add property
  const [addingProp, setAddingProp] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, p, inv] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
        api.get<{ items: Invoice[] }>(`/v1/invoices?customer_id=${id}`),
      ]);
      setCustomer(c);
      setCustForm(c);
      setProperties(p.items);
      setInvoices(inv.items);
    } catch {
      toast.error("Failed to load customer");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const setCustField = (field: string, value: unknown) => {
    setCustForm((f) => f ? { ...f, [field]: value } : f);
    setCustDirty(true);
  };

  const handleSaveCustomer = async () => {
    if (!custForm) return;
    setCustSaving(true);
    try {
      await api.put(`/v1/customers/${id}`, {
        first_name: custForm.first_name, last_name: custForm.last_name,
        company_name: custForm.company_name || null, customer_type: custForm.customer_type,
        email: custForm.email || null, phone: custForm.phone || null,
        billing_address: custForm.billing_address || null, billing_city: custForm.billing_city || null,
        billing_state: custForm.billing_state || null, billing_zip: custForm.billing_zip || null,
        service_frequency: custForm.service_frequency || null, preferred_day: custForm.preferred_day || null,
        billing_frequency: custForm.billing_frequency, monthly_rate: custForm.monthly_rate,
        payment_method: custForm.payment_method || null, payment_terms_days: custForm.payment_terms_days,
        difficulty_rating: custForm.difficulty_rating, notes: custForm.notes || null,
        is_active: custForm.is_active,
      });
      toast.success("Customer updated");
      setCustDirty(false);
      load();
    } catch {
      toast.error("Failed to update customer");
    } finally {
      setCustSaving(false);
    }
  };

  const handleSaveProperty = async (propId: string, data: Record<string, unknown>) => {
    await api.put(`/v1/properties/${propId}`, data);
    toast.success("Property updated");
    load();
  };

  const handleDeleteProperty = async (propId: string) => {
    try {
      await api.delete(`/v1/properties/${propId}`);
      toast.success("Property deleted");
      load();
    } catch {
      toast.error("Failed to delete property");
    }
  };

  const handleAddProperty = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/v1/properties", {
        customer_id: id,
        name: form.get("name") || undefined,
        address: form.get("address"),
        city: form.get("city"),
        state: form.get("state"),
        zip_code: form.get("zip_code"),
        pool_type: form.get("pool_type") || undefined,
      });
      toast.success("Property added");
      setAddingProp(false);
      load();
    } catch {
      toast.error("Failed to add property");
    }
  };

  if (!customer || !custForm) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const TypeIcon = customer.customer_type === "commercial" ? Building2 : Home;
  const displayName = customer.customer_type === "commercial"
    ? customer.first_name
    : `${customer.first_name} ${customer.last_name}`.trim();

  // --- EDIT MODE ---
  if (editing) {
    return (
      <div className="space-y-4 sm:space-y-6 pb-20 sm:pb-6">
        {/* Edit header */}
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" className="shrink-0" onClick={() => { setEditing(false); setCustDirty(false); load(); }}>
            <X className="h-4 w-4" />
          </Button>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight truncate">
            Edit {displayName}
          </h1>
        </div>

        {/* Customer fields */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Customer</CardTitle>
              {custDirty && (
                <Button size="sm" onClick={handleSaveCustomer} disabled={custSaving} className="h-8">
                  {custSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <><Save className="h-3.5 w-3.5 mr-1" />Save</>}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Identity */}
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
                <Label className="text-xs">Company</Label>
                <Input value={custForm.company_name ?? ""} onChange={(e) => setCustField("company_name", e.target.value)} className="h-9" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">{custForm.customer_type === "commercial" ? "Name" : "First Name"}</Label>
                <Input value={custForm.first_name} onChange={(e) => setCustField("first_name", e.target.value)} className="h-9" />
              </div>
              {custForm.customer_type !== "commercial" && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Last Name</Label>
                  <Input value={custForm.last_name} onChange={(e) => setCustField("last_name", e.target.value)} className="h-9" />
                </div>
              )}
            </div>

            {/* Contact */}
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

            {/* Billing */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Monthly Rate ($)</Label>
                <Input type="number" step="0.01" value={custForm.monthly_rate} onChange={(e) => setCustField("monthly_rate", parseFloat(e.target.value) || 0)} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Payment Terms (days)</Label>
                <Input type="number" value={custForm.payment_terms_days} onChange={(e) => setCustField("payment_terms_days", parseInt(e.target.value) || 30)} className="h-9" />
              </div>
            </div>
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

            {/* Billing address */}
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

            {/* Service */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Service Frequency</Label>
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
                <Label className="text-xs">Preferred Day</Label>
                <Select value={custForm.preferred_day ?? ""} onValueChange={(v) => setCustField("preferred_day", v || null)}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Any" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="monday">Monday</SelectItem>
                    <SelectItem value="tuesday">Tuesday</SelectItem>
                    <SelectItem value="wednesday">Wednesday</SelectItem>
                    <SelectItem value="thursday">Thursday</SelectItem>
                    <SelectItem value="friday">Friday</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Notes + Active */}
            <div className="space-y-1.5">
              <Label className="text-xs">Notes</Label>
              <Textarea value={custForm.notes ?? ""} onChange={(e) => setCustField("notes", e.target.value)} rows={2} />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={custForm.is_active} onCheckedChange={(v) => setCustField("is_active", v)} />
              <Label className="text-xs">Active</Label>
            </div>
          </CardContent>
        </Card>

        {/* Properties */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Properties ({properties.length})</h2>
            <Button variant="outline" size="sm" className="h-8" onClick={() => setAddingProp(!addingProp)}>
              <Plus className="h-3.5 w-3.5 mr-1" />Add
            </Button>
          </div>

          {addingProp && (
            <Card>
              <CardContent className="pt-4">
                <form onSubmit={handleAddProperty} className="space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Name</Label>
                    <Input name="name" placeholder="e.g. Big Pool, Spa" className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Address</Label>
                    <Input name="address" required className="h-9" />
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs">City</Label>
                      <Input name="city" required className="h-9" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">State</Label>
                      <Input name="state" required className="h-9" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Zip</Label>
                      <Input name="zip_code" required className="h-9" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Pool Type</Label>
                    <Select name="pool_type" defaultValue="">
                      <SelectTrigger className="h-9"><SelectValue placeholder="Select..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="commercial">Commercial</SelectItem>
                        <SelectItem value="residential">Residential</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" className="flex-1 h-9" onClick={() => setAddingProp(false)}>Cancel</Button>
                    <Button type="submit" className="flex-1 h-9">Add Property</Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          {properties.map((p) => (
            <PropertyEditCard
              key={p.id}
              property={p}
              onSave={(data) => handleSaveProperty(p.id, data)}
              onDelete={() => handleDeleteProperty(p.id)}
            />
          ))}
        </div>
      </div>
    );
  }

  // --- VIEW MODE ---
  return (
    <div className="space-y-4 sm:space-y-6 pb-20 sm:pb-0">
      {/* Header */}
      <div className="flex items-start gap-2 sm:gap-4">
        <Button variant="ghost" size="sm" className="shrink-0 mt-1" onClick={() => router.back()}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <TypeIcon className="h-5 w-5 text-muted-foreground shrink-0" />
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight truncate">
              {displayName}
            </h1>
            <Badge variant={customer.is_active ? "default" : "secondary"} className="shrink-0">
              {customer.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
          {customer.company_name && (
            <p className="text-muted-foreground text-sm truncate">{customer.company_name}</p>
          )}
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="info">Info</TabsTrigger>
          <TabsTrigger value="properties">Properties ({properties.length})</TabsTrigger>
          <TabsTrigger value="invoices">Invoices ({invoices.length})</TabsTrigger>
        </TabsList>

        {/* Info Tab */}
        <TabsContent value="info" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">Contact</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div><span className="text-muted-foreground">Email: </span>{customer.email || "\u2014"}</div>
                <div><span className="text-muted-foreground">Phone: </span>{customer.phone || "\u2014"}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">Billing</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div><span className="text-muted-foreground">Monthly Rate: </span>${customer.monthly_rate.toFixed(2)}</div>
                <div>
                  <span className="text-muted-foreground">Balance: </span>
                  <span className={customer.balance > 0 ? "text-red-600 font-medium" : ""}>${customer.balance.toFixed(2)}</span>
                </div>
                {customer.billing_address && (
                  <div><span className="text-muted-foreground">Address: </span>{customer.billing_address}, {customer.billing_city}, {customer.billing_state} {customer.billing_zip}</div>
                )}
              </CardContent>
            </Card>
          </div>
          {customer.notes && (
            <Card>
              <CardHeader><CardTitle className="text-base">Notes</CardTitle></CardHeader>
              <CardContent><p className="text-sm whitespace-pre-wrap">{customer.notes}</p></CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Properties Tab */}
        <TabsContent value="properties" className="space-y-4">
          {properties.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">No properties yet</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {properties.map((p) => (
                <Card key={p.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <div className="min-w-0 flex-1">
                        <CardTitle className="text-base flex items-center gap-2">
                          <MapPin className="h-4 w-4 shrink-0" />
                          <span className="truncate">{p.name || p.address}</span>
                        </CardTitle>
                        <p className="text-sm text-muted-foreground">{p.name ? p.address + ", " : ""}{p.city}, {p.state} {p.zip_code}</p>
                      </div>
                      <Link href={`/properties/${p.id}/measure`}>
                        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                          <Ruler className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                    </div>
                  </CardHeader>
                  <CardContent className="text-sm space-y-2">
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                      {p.pool_type && <span>Pool: {p.pool_type}</span>}
                      {p.pool_gallons && <span>{p.pool_gallons.toLocaleString()} gal</span>}
                      {p.pool_sqft && <span>{p.pool_sqft.toLocaleString()} sqft</span>}
                      {p.has_spa && <Badge variant="outline">Spa</Badge>}
                    </div>
                    {p.pool_volume_method && (
                      <Badge variant="outline" className="text-xs capitalize">{p.pool_volume_method}</Badge>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Invoices Tab */}
        <TabsContent value="invoices">
          {invoices.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">No invoices yet</p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Invoice #</TableHead>
                    <TableHead className="hidden sm:table-cell">Subject</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="hidden sm:table-cell">Issue Date</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead className="text-right">Balance</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoices.map((inv) => (
                    <TableRow key={inv.id}>
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
        </TabsContent>
      </Tabs>

      {/* Single edit button at bottom */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-background border-t sm:static sm:p-0 sm:border-0 sm:bg-transparent z-30">
        <Button
          variant="outline"
          className="w-full h-12 sm:h-10"
          onClick={() => setEditing(true)}
        >
          <Pencil className="h-4 w-4 mr-2" />
          Edit Customer & Properties
        </Button>
      </div>
    </div>
  );
}
