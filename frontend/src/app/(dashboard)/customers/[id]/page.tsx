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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
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
  Droplets,
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

interface BodyOfWater {
  id: string;
  property_id: string;
  name: string | null;
  water_type: string;
  is_primary: boolean;
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
  estimated_service_minutes: number;
  is_locked_to_day: boolean;
  service_day_pattern: string | null;
  notes: string | null;
  is_active: boolean;
  bodies_of_water: BodyOfWaterSummary[];
}

interface BodyOfWaterSummary {
  id: string;
  name: string | null;
  water_type: string;
  is_primary: boolean;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
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

// --- BOW Edit Card (inline within property) ---
function BowEditCard({
  bow,
  onSave,
  onDelete,
}: {
  bow: BodyOfWater;
  onSave: (data: Record<string, unknown>) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState({ ...bow });
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
        water_type: form.water_type,
        is_primary: form.is_primary,
        pool_type: form.pool_type || null,
        pool_gallons: form.pool_gallons,
        pool_sqft: form.pool_sqft,
        pool_surface: form.pool_surface || null,
        pool_length_ft: form.pool_length_ft,
        pool_width_ft: form.pool_width_ft,
        pool_depth_shallow: form.pool_depth_shallow,
        pool_depth_deep: form.pool_depth_deep,
        pool_depth_avg: form.pool_depth_avg,
        pool_shape: form.pool_shape || null,
        sanitizer_type: form.sanitizer_type || null,
        pump_type: form.pump_type || null,
        filter_type: form.filter_type || null,
        heater_type: form.heater_type || null,
        chlorinator_type: form.chlorinator_type || null,
        automation_system: form.automation_system || null,
        estimated_service_minutes: form.estimated_service_minutes,
        monthly_rate: form.monthly_rate,
        notes: form.notes || null,
      });
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  const typeLabel = form.name || form.water_type.replace("_", " ");

  return (
    <div className="border rounded-lg">
      <div className="flex items-center justify-between px-3 py-2">
        <button className="flex items-center gap-2 min-w-0 flex-1 text-left" onClick={() => setExpanded(!expanded)}>
          <Droplets className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="text-sm font-medium capitalize truncate">{typeLabel}</span>
          {form.is_primary && <Badge variant="outline" className="text-[10px] px-1 py-0">Primary</Badge>}
          {expanded ? <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
        </button>
        <div className="flex gap-1 shrink-0 ml-2">
          {dirty && (
            <Button variant="default" size="icon" className="h-7 w-7" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            </Button>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive">
                <Trash2 className="h-3 w-3" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete {typeLabel}?</AlertDialogTitle>
                <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={onDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t pt-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Name</Label>
              <Input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Lap Pool" className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Type</Label>
              <Select value={form.water_type} onValueChange={(v) => set("water_type", v)}>
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="pool">Pool</SelectItem>
                  <SelectItem value="spa">Spa</SelectItem>
                  <SelectItem value="hot_tub">Hot Tub</SelectItem>
                  <SelectItem value="wading_pool">Wading Pool</SelectItem>
                  <SelectItem value="fountain">Fountain</SelectItem>
                  <SelectItem value="water_feature">Water Feature</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Pool Type</Label>
              <Select value={form.pool_type ?? ""} onValueChange={(v) => set("pool_type", v || null)}>
                <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="commercial">Commercial</SelectItem>
                  <SelectItem value="residential">Residential</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Gallons</Label>
              <Input type="number" value={form.pool_gallons ?? ""} onChange={(e) => set("pool_gallons", intOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Sqft</Label>
              <Input type="number" step="0.1" value={form.pool_sqft ?? ""} onChange={(e) => set("pool_sqft", numOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Service (min)</Label>
              <Input type="number" value={form.estimated_service_minutes} onChange={(e) => set("estimated_service_minutes", parseInt(e.target.value) || 30)} className="h-8 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Length (ft)</Label>
              <Input type="number" step="0.1" value={form.pool_length_ft ?? ""} onChange={(e) => set("pool_length_ft", numOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Width (ft)</Label>
              <Input type="number" step="0.1" value={form.pool_width_ft ?? ""} onChange={(e) => set("pool_width_ft", numOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Shape</Label>
              <Select value={form.pool_shape ?? ""} onValueChange={(v) => set("pool_shape", v || null)}>
                <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="..." /></SelectTrigger>
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
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Shallow (ft)</Label>
              <Input type="number" step="0.1" value={form.pool_depth_shallow ?? ""} onChange={(e) => set("pool_depth_shallow", numOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Deep (ft)</Label>
              <Input type="number" step="0.1" value={form.pool_depth_deep ?? ""} onChange={(e) => set("pool_depth_deep", numOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Surface</Label>
              <Select value={form.pool_surface ?? ""} onValueChange={(v) => set("pool_surface", v || null)}>
                <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="..." /></SelectTrigger>
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
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide pt-1">Chemical & Equipment</p>
          <div className="space-y-1.5">
            <Label className="text-xs">Sanitizer</Label>
            <Select value={form.sanitizer_type ?? ""} onValueChange={(v) => set("sanitizer_type", v || null)}>
              <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Select..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="liquid">Liquid Chlorine</SelectItem>
                <SelectItem value="tabs">Tabs (Trichlor)</SelectItem>
                <SelectItem value="granular">Granular (Dichlor)</SelectItem>
                <SelectItem value="cal_hypo">Cal-Hypo</SelectItem>
                <SelectItem value="salt">Salt (SWG)</SelectItem>
                <SelectItem value="bromine">Bromine</SelectItem>
                <SelectItem value="uv_ozone">UV / Ozone</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Pump</Label>
              <Input value={form.pump_type ?? ""} onChange={(e) => set("pump_type", e.target.value)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Filter</Label>
              <Input value={form.filter_type ?? ""} onChange={(e) => set("filter_type", e.target.value)} className="h-8 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Heater</Label>
              <Input value={form.heater_type ?? ""} onChange={(e) => set("heater_type", e.target.value)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Chlorinator</Label>
              <Input value={form.chlorinator_type ?? ""} onChange={(e) => set("chlorinator_type", e.target.value)} className="h-8 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Automation</Label>
              <Input value={form.automation_system ?? ""} onChange={(e) => set("automation_system", e.target.value)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Monthly Rate ($)</Label>
              <Input type="number" step="0.01" value={form.monthly_rate ?? ""} onChange={(e) => set("monthly_rate", numOrNull(e.target.value))} className="h-8 text-sm" />
            </div>
          </div>
          {dirty && (
            <Button onClick={handleSave} disabled={saving} size="sm" className="w-full h-8">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <><Save className="h-3.5 w-3.5 mr-1" />Save</>}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// --- Property Edit Card (collapsible) ---
function PropertyEditCard({
  property,
  customer,
  onSave,
  onDelete,
  onBowChange,
}: {
  property: Property;
  customer: Customer;
  onSave: (data: Record<string, unknown>) => Promise<void>;
  onDelete: () => Promise<void>;
  onBowChange: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState({ ...property });
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [bows, setBows] = useState<BodyOfWater[]>([]);
  const [bowsLoading, setBowsLoading] = useState(false);
  const [addingBow, setAddingBow] = useState(false);
  const hasOverrides = Boolean(property.gate_code || property.access_instructions || property.dog_on_property || property.notes ||
    (customer.billing_address && property.address !== customer.billing_address) ||
    property.is_locked_to_day ||
    property.service_day_pattern);
  const [showOverrides, setShowOverrides] = useState<boolean>(hasOverrides);
  const set = (field: string, value: unknown) => {
    setForm((f) => ({ ...f, [field]: value }));
    setDirty(true);
  };

  const loadBows = useCallback(async () => {
    setBowsLoading(true);
    try {
      const data = await api.get<BodyOfWater[]>(`/v1/bodies-of-water/property/${property.id}`);
      setBows(data);
    } catch {
      /* ignore */
    } finally {
      setBowsLoading(false);
    }
  }, [property.id]);

  useEffect(() => {
    if (expanded && bows.length === 0) loadBows();
  }, [expanded, loadBows, bows.length]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const addr = showOverrides
        ? { address: form.address, city: form.city, state: form.state, zip_code: form.zip_code }
        : { address: customer.billing_address || form.address, city: customer.billing_city || form.city, state: customer.billing_state || form.state, zip_code: customer.billing_zip || form.zip_code };
      await onSave({
        ...addr,
        gate_code: showOverrides ? (form.gate_code || null) : null,
        access_instructions: showOverrides ? (form.access_instructions || null) : null,
        dog_on_property: showOverrides ? form.dog_on_property : false,
        is_locked_to_day: showOverrides ? form.is_locked_to_day : false,
        service_day_pattern: showOverrides ? (form.service_day_pattern || null) : null,
        notes: showOverrides ? (form.notes || null) : null, is_active: form.is_active,
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
              <p className="text-sm font-medium truncate">{form.address}</p>
              <p className="text-xs text-muted-foreground">{form.city}, {form.state} {form.zip_code}</p>
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
          {/* Override toggle */}
          <div className="space-y-3">
            <button
              type="button"
              className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => { setShowOverrides(!showOverrides); setDirty(true); }}
            >
              <Switch checked={showOverrides} className="scale-75" />
              <span className="font-medium uppercase tracking-wide">Different info for this property</span>
            </button>
            {showOverrides && (
              <div className="space-y-3 pl-1 border-l-2 border-muted ml-2">
                <div className="pl-3 space-y-3">
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
                  <div className="space-y-1.5">
                    <Label className="text-xs">Gate Code</Label>
                    <Input value={form.gate_code ?? ""} onChange={(e) => set("gate_code", e.target.value)} className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Access Instructions</Label>
                    <Textarea value={form.access_instructions ?? ""} onChange={(e) => set("access_instructions", e.target.value)} rows={2} />
                  </div>
                  <div className="flex flex-wrap gap-x-6 gap-y-2">
                    <div className="flex items-center gap-2">
                      <Switch checked={form.dog_on_property} onCheckedChange={(v) => set("dog_on_property", v)} />
                      <Label className="text-xs">Dog on Property</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch checked={form.is_locked_to_day} onCheckedChange={(v) => set("is_locked_to_day", v)} />
                      <Label className="text-xs">Locked to Day</Label>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Notes</Label>
                    <Textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2} />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Active toggle */}
          <div className="flex items-center gap-2">
            <Switch checked={form.is_active} onCheckedChange={(v) => set("is_active", v)} />
            <Label className="text-xs">Active</Label>
          </div>

          {/* Bodies of Water */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Bodies of Water</p>
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setAddingBow(!addingBow)}>
                <Plus className="h-3 w-3 mr-1" />Add
              </Button>
            </div>
            {addingBow && (
              <form onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                try {
                  await api.post(`/v1/bodies-of-water/property/${property.id}`, {
                    name: fd.get("bow_name") || undefined,
                    water_type: fd.get("bow_water_type") || "pool",
                    estimated_service_minutes: parseInt(fd.get("bow_minutes") as string) || 30,
                  });
                  toast.success("Added");
                  setAddingBow(false);
                  loadBows();
                  onBowChange();
                } catch { toast.error("Failed to add"); }
              }} className="border rounded-lg p-3 space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Name</Label>
                    <Input name="bow_name" placeholder="e.g. Spa" className="h-8 text-sm" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Type</Label>
                    <select name="bow_water_type" defaultValue="pool" className="h-8 w-full rounded-md border px-2 text-sm">
                      <option value="pool">Pool</option>
                      <option value="spa">Spa</option>
                      <option value="hot_tub">Hot Tub</option>
                      <option value="fountain">Fountain</option>
                      <option value="water_feature">Water Feature</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Minutes</Label>
                    <Input name="bow_minutes" type="number" defaultValue="30" className="h-8 text-sm" />
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" size="sm" className="flex-1 h-7" onClick={() => setAddingBow(false)}>Cancel</Button>
                  <Button type="submit" size="sm" className="flex-1 h-7">Add</Button>
                </div>
              </form>
            )}
            {bowsLoading ? (
              <div className="flex justify-center py-2"><Loader2 className="h-4 w-4 animate-spin" /></div>
            ) : (
              bows.map((bow) => (
                <BowEditCard
                  key={bow.id}
                  bow={bow}
                  onSave={async (data) => {
                    await api.put(`/v1/bodies-of-water/${bow.id}`, data);
                    toast.success("Saved");
                    loadBows();
                    onBowChange();
                  }}
                  onDelete={async () => {
                    try {
                      await api.delete(`/v1/bodies-of-water/${bow.id}`);
                      toast.success("Deleted");
                      loadBows();
                      onBowChange();
                    } catch { toast.error("Failed to delete"); }
                  }}
                />
              ))
            )}
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

// --- BOW View Row (expandable, progressive disclosure) ---
function BowViewRow({ bow, propertyId, property, customer }: {
  bow: BodyOfWaterSummary;
  propertyId: string;
  property: Property;
  customer: Customer;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showFull, setShowFull] = useState(false);
  const [detail, setDetail] = useState<BodyOfWater | null>(null);

  const loadDetail = async () => {
    if (detail) return;
    try {
      const data = await api.get<BodyOfWater>(`/v1/bodies-of-water/${bow.id}`);
      setDetail(data);
    } catch { /* ignore */ }
  };

  const toggle = () => {
    if (!expanded) loadDetail();
    setExpanded(!expanded);
  };

  const d = detail;

  const sanitizerLabels: Record<string, string> = {
    liquid: "Liquid Chlorine", tabs: "Tabs (Trichlor)", granular: "Granular (Dichlor)",
    cal_hypo: "Cal-Hypo", salt: "Salt (SWG)", bromine: "Bromine", uv_ozone: "UV / Ozone",
  };

  const equipmentItems = d ? [
    d.pump_type && `Pump: ${d.pump_type}`,
    d.filter_type && `Filter: ${d.filter_type}`,
    d.heater_type && `Heater: ${d.heater_type}`,
    d.chlorinator_type && `Chlorinator: ${d.chlorinator_type}`,
    d.automation_system && `Automation: ${d.automation_system}`,
  ].filter(Boolean) : [];

  return (
    <div className="rounded-lg border overflow-hidden">
      <div className="flex items-center bg-muted/50">
        <button
          className="flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/70 flex-1 min-w-0"
          onClick={toggle}
        >
          <Droplets className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="font-medium capitalize flex-1 truncate">
            {bow.name || bow.water_type.replace("_", " ")}
          </span>
          <span className="text-xs text-muted-foreground shrink-0">
            {bow.pool_gallons ? `${bow.pool_gallons.toLocaleString()} gal` : ""}
            {bow.pool_gallons && bow.estimated_service_minutes ? " · " : ""}
            {bow.estimated_service_minutes} min
            {customer.preferred_day ? ` · ${customer.preferred_day.split(",").map(d => d.trim().slice(0, 3).charAt(0).toUpperCase() + d.trim().slice(1, 3)).join("/")}` : ""}
          </span>
          {expanded ? <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground ml-1" /> : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground ml-1" />}
        </button>
        <Link href={`/properties/${propertyId}/measure?bow=${bow.id}`} onClick={(e) => e.stopPropagation()}>
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 mr-1">
            <Ruler className="h-3.5 w-3.5" />
          </Button>
        </Link>
      </div>
      {expanded && d && (
        <div className="px-3 pb-3 pt-2 border-t space-y-2.5 text-sm">
          {/* Tech quick view */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5">
            <div><span className="text-muted-foreground">Gallons: </span>{d.pool_gallons ? d.pool_gallons.toLocaleString() : "—"}</div>
            <div><span className="text-muted-foreground">Sanitizer: </span>{d.sanitizer_type ? sanitizerLabels[d.sanitizer_type] || d.sanitizer_type : "—"}</div>
          </div>

          {equipmentItems.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1 text-xs">
              {equipmentItems.map((item, i) => <div key={i} className="text-muted-foreground">{item}</div>)}
            </div>
          )}

          {/* Access & schedule from property/customer */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5 text-xs pt-1 border-t">
            <div><span className="text-muted-foreground">Frequency: </span><span className="capitalize">{customer.service_frequency || "weekly"}</span></div>
            <div><span className="text-muted-foreground">Days: </span>{customer.preferred_day ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ") : "any"}</div>
            {property.gate_code && <div><span className="text-muted-foreground">Gate: </span>{property.gate_code}</div>}
            {property.dog_on_property && <div className="text-amber-600 font-medium">Dog on property</div>}
            {property.access_instructions && <div className="col-span-2 sm:col-span-3"><span className="text-muted-foreground">Access: </span>{property.access_instructions}</div>}
          </div>

          {d.notes && (
            <p className="text-xs italic border-t pt-1.5">{d.notes}</p>
          )}

          {/* Full details — manager/owner view */}
          {showFull && (
            <div className="space-y-3 pt-2 border-t">
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Pool Info</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5">
                  <div><span className="text-muted-foreground">Type: </span><span className="capitalize">{d.pool_type || "—"}</span></div>
                  <div><span className="text-muted-foreground">Water Type: </span><span className="capitalize">{d.water_type.replace("_", " ")}</span></div>
                  <div><span className="text-muted-foreground">Surface: </span><span className="capitalize">{d.pool_surface || "—"}</span></div>
                  <div><span className="text-muted-foreground">Shape: </span><span className="capitalize">{d.pool_shape || "—"}</span></div>
                  <div><span className="text-muted-foreground">Volume Method: </span>{d.pool_volume_method || "—"}</div>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Dimensions</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5">
                  <div><span className="text-muted-foreground">Sqft: </span>{d.pool_sqft ? d.pool_sqft.toLocaleString() : "—"}</div>
                  <div><span className="text-muted-foreground">Length: </span>{d.pool_length_ft ? `${d.pool_length_ft} ft` : "—"}</div>
                  <div><span className="text-muted-foreground">Width: </span>{d.pool_width_ft ? `${d.pool_width_ft} ft` : "—"}</div>
                  <div><span className="text-muted-foreground">Shallow: </span>{d.pool_depth_shallow != null ? `${d.pool_depth_shallow} ft` : "—"}</div>
                  <div><span className="text-muted-foreground">Deep: </span>{d.pool_depth_deep != null ? `${d.pool_depth_deep} ft` : "—"}</div>
                  <div><span className="text-muted-foreground">Avg Depth: </span>{d.pool_depth_avg != null ? `${d.pool_depth_avg} ft` : "—"}</div>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Service & Billing</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5">
                  <div><span className="text-muted-foreground">Service Time: </span>{d.estimated_service_minutes} min</div>
                  <div><span className="text-muted-foreground">Monthly Rate: </span>{d.monthly_rate != null ? `$${d.monthly_rate.toFixed(2)}` : "— (uses client rate)"}</div>
                  <div><span className="text-muted-foreground">Status: </span>{d.is_active ? "Active" : "Inactive"}</div>
                </div>
              </div>
            </div>
          )}

          <button
            type="button"
            className="text-xs text-muted-foreground hover:text-foreground underline"
            onClick={() => setShowFull(!showFull)}
          >
            {showFull ? "Hide details" : "Show full details"}
          </button>
        </div>
      )}
      {expanded && !detail && (
        <div className="flex justify-center py-3"><Loader2 className="h-4 w-4 animate-spin" /></div>
      )}
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
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [editing, setEditing] = useState(false);
  const [invoicesOpen, setInvoicesOpen] = useState(false);

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
      toast.error("Failed to load client");
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
      toast.success("Client updated");
      setCustDirty(false);
      load();
    } catch {
      toast.error("Failed to update client");
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
        address: form.get("address"),
        city: form.get("city"),
        state: form.get("state"),
        zip_code: form.get("zip_code"),
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
              <CardTitle className="text-base">Client</CardTitle>
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
                <Label className="text-xs">Service Days</Label>
                <div className="flex flex-wrap gap-1">
                  {["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"].map((day) => {
                    const days = (custForm.preferred_day ?? "").split(",").filter(Boolean);
                    const active = days.includes(day);
                    return (
                      <Button
                        key={day}
                        type="button"
                        variant={active ? "default" : "outline"}
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => {
                          const next = active ? days.filter(d => d !== day) : [...days, day];
                          setCustField("preferred_day", next.length ? next.join(",") : null);
                        }}
                      >
                        {day.slice(0, 3).charAt(0).toUpperCase() + day.slice(1, 3)}
                      </Button>
                    );
                  })}
                </div>
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
              customer={customer}
              onSave={(data) => handleSaveProperty(p.id, data)}
              onDelete={() => handleDeleteProperty(p.id)}
              onBowChange={load}
            />
          ))}
        </div>
      </div>
    );
  }

  // --- VIEW MODE ---
  return (
    <div className="space-y-4 sm:space-y-6 pb-20 sm:pb-0 max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" className="shrink-0" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1" />
        <Button
          variant="outline"
          size="sm"
          onClick={() => setEditing(true)}
        >
          <Pencil className="h-3.5 w-3.5 mr-1.5" />
          Edit
        </Button>
      </div>

      {/* Client card */}
      <Card>
        <CardContent className="pt-5 pb-4 space-y-4">
          <div className="flex items-start gap-3">
            <TypeIcon className="h-6 w-6 text-muted-foreground shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight truncate flex-1">
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

          <div className="grid gap-3 sm:grid-cols-2">
            <Card className="bg-muted/50">
              <CardContent className="pt-3 pb-3 space-y-1.5 text-sm">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Contact</p>
                <div><span className="text-muted-foreground">Email: </span>{customer.email || "\u2014"}</div>
                <div><span className="text-muted-foreground">Phone: </span>{customer.phone || "\u2014"}</div>
              </CardContent>
            </Card>
            <Card className="bg-muted/50">
              <CardContent className="pt-3 pb-3 space-y-1.5 text-sm">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Billing</p>
                <div><span className="text-muted-foreground">Rate: </span>${customer.monthly_rate.toFixed(2)}/mo</div>
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
            <Card className="bg-muted/50">
              <CardContent className="pt-3 pb-3 text-sm">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Notes</p>
                <p className="whitespace-pre-wrap">{customer.notes}</p>
              </CardContent>
            </Card>
          )}

          {/* Properties */}
          {properties.length === 0 ? (
            <p className="text-center text-muted-foreground py-2 text-sm">No properties yet</p>
          ) : (
            properties.map((p) => (
              <Card key={p.id} className="bg-background">
                <CardContent className="pt-3 pb-3 space-y-2">
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        <span className="truncate">{p.address}</span>
                      </div>
                      <p className="text-xs text-muted-foreground ml-5.5 pl-0.5">{p.city}, {p.state} {p.zip_code}</p>
                    </div>
                  </div>
                  {(p.bodies_of_water?.length > 0) ? (
                    <div className="space-y-1">
                      {p.bodies_of_water.map((bow) => (
                        <BowViewRow key={bow.id} bow={bow} propertyId={p.id} property={p} customer={customer} />
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground ml-5.5 pl-0.5">
                      {p.pool_type && <span>Pool: {p.pool_type}</span>}
                      {p.pool_gallons && <span>{p.pool_gallons.toLocaleString()} gal</span>}
                      {p.pool_sqft && <span>{p.pool_sqft.toLocaleString()} sqft</span>}
                      {p.has_spa && <Badge variant="outline">Spa</Badge>}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </CardContent>
      </Card>

      {/* Invoices — collapsible accordion */}
      <Collapsible open={invoicesOpen} onOpenChange={setInvoicesOpen}>
        <CollapsibleTrigger asChild>
          <button className="w-full flex items-center justify-between rounded-lg border px-4 py-3 hover:bg-muted/50 transition-colors">
            <div className="flex items-center gap-2 text-sm font-semibold">
              Invoices ({invoices.length})
              {(() => {
                const outstanding = invoices.reduce((sum, inv) => sum + inv.balance, 0);
                return outstanding > 0
                  ? <span className="text-xs font-normal text-red-600">${outstanding.toFixed(2)} outstanding</span>
                  : null;
              })()}
            </div>
            {invoicesOpen ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          {invoices.length === 0 ? (
            <p className="text-center text-muted-foreground py-4 text-sm">No invoices yet</p>
          ) : (
            <div className="rounded-md border mt-2">
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
        </CollapsibleContent>
      </Collapsible>

    </div>
  );
}
