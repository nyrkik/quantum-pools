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
  X,
  Trash2,
  Loader2,
  ChevronDown,
  ChevronUp,
  Droplets,
  ClipboardList,
  Receipt,
  LayoutDashboard,
  Calendar,
  DollarSign,
  Clock,
  ClipboardCheck,
  History,
  Waves,
  Gauge,
  Wrench,
  Thermometer,
  Zap,
  FlaskConical,
  Move,
  StickyNote,
  Satellite,
} from "lucide-react";
import Link from "next/link";
import { usePermissions } from "@/lib/permissions";
import type { SatelliteImageData } from "@/types/satellite";

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

interface BodyOfWater {
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

  const handleCancel = () => {
    setForm({ ...bow });
    setDirty(false);
  };

  const typeLabel = form.name || form.water_type.replace("_", " ");

  return (
    <div className={`border rounded-lg ${dirty ? "border-l-4 border-l-amber-400" : ""}`}>
      <div className="flex items-center justify-between px-3 py-2">
        <button className="flex items-center gap-2 min-w-0 flex-1 text-left" onClick={() => setExpanded(!expanded)}>
          <Droplets className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="text-sm font-medium capitalize truncate">{typeLabel}</span>
          {expanded ? <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
        </button>
        <div className="flex gap-1.5 shrink-0 ml-2">
          {dirty && (
            <>
              <Button variant="default" size="sm" className="h-7 px-2.5 text-xs" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
              </Button>
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={handleCancel}>
                Cancel
              </Button>
            </>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive">
                <Trash2 className="h-3.5 w-3.5" />
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

  const handleCancel = () => {
    setForm({ ...property });
    setDirty(false);
    setShowOverrides(hasOverrides);
  };

  return (
    <Card className={dirty ? "border-l-4 border-l-amber-400" : ""}>
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
          <div className="flex gap-1.5 shrink-0 ml-2">
            {dirty && (
              <>
                <Button variant="default" size="sm" className="h-8 px-3 text-xs" onClick={handleSave} disabled={saving}>
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                </Button>
                <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs" onClick={handleCancel}>
                  Undo
                </Button>
              </>
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

          {/* Water Features */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Water Features</p>
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
  const perms = usePermissions();
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
        {perms.canMeasure && (
          <Link href={`/properties/${propertyId}/measure?bow=${bow.id}`} onClick={(e) => e.stopPropagation()}>
            <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 mr-1">
              <Ruler className="h-3.5 w-3.5" />
            </Button>
          </Link>
        )}
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
          {perms.canViewDimensions && showFull && (
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
                  {perms.canViewRates && <div><span className="text-muted-foreground">Monthly Rate: </span>{d.monthly_rate != null ? `$${d.monthly_rate.toFixed(2)}` : "— (uses client rate)"}</div>}
                  <div><span className="text-muted-foreground">Status: </span>{d.is_active ? "Active" : "Inactive"}</div>
                </div>
              </div>
            </div>
          )}

          {perms.canViewDimensions && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground underline"
              onClick={() => setShowFull(!showFull)}
            >
              {showFull ? "Hide details" : "Show full details"}
            </button>
          )}
        </div>
      )}
      {expanded && !detail && (
        <div className="flex justify-center py-3"><Loader2 className="h-4 w-4 animate-spin" /></div>
      )}
    </div>
  );
}

// --- Single Property BOW Section (for edit mode) ---
function SinglePropertyBowSection({ propertyId, onBowChange }: { propertyId: string; onBowChange: () => void }) {
  const [bows, setBows] = useState<BodyOfWater[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingBow, setAddingBow] = useState(false);

  const loadBows = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<BodyOfWater[]>(`/v1/bodies-of-water/property/${propertyId}`);
      setBows(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [propertyId]);

  useEffect(() => { loadBows(); }, [loadBows]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Water Features</p>
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setAddingBow(!addingBow)}>
          <Plus className="h-3 w-3 mr-1" />Add
        </Button>
      </div>
      {addingBow && (
        <form onSubmit={async (e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          try {
            await api.post(`/v1/bodies-of-water/property/${propertyId}`, {
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
      {loading ? (
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
  );
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
  const [heroImages, setHeroImages] = useState<Record<string, SatelliteImageData>>({});
  const [fullBows, setFullBows] = useState<BodyOfWater[]>([]);
  const isTech = perms.role === "technician";
  const [viewTab, setViewTab] = useState<"overview" | "service" | "details" | "bows" | "invoices">(isTech ? "service" : "overview");
  const [editingDetails, setEditingDetails] = useState(false);
  const [editingBows, setEditingBows] = useState(false);
  const [showDiscardDialog, setShowDiscardDialog] = useState(false);
  const [discardTarget, setDiscardTarget] = useState<"details" | "bows" | null>(null);

  // Customer edit form state
  const [custForm, setCustForm] = useState<Customer | null>(null);
  const [custSaving, setCustSaving] = useState(false);
  const [custDirty, setCustDirty] = useState(false);

  // Add property
  const [addingProp, setAddingProp] = useState(false);

  // Single-property inline edit state
  const singleProp = properties.length <= 1 ? properties[0] ?? null : null;
  const [propForm, setPropForm] = useState<Property | null>(null);
  const [propDirty, setPropDirty] = useState(false);

  useEffect(() => {
    if (singleProp) setPropForm(singleProp);
  }, [singleProp?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const setPropField = (field: string, value: unknown) => {
    setPropForm((f) => f ? { ...f, [field]: value } : f);
    setPropDirty(true);
  };

  const load = useCallback(async () => {
    try {
      const [c, p, inv, heroes] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
        api.get<{ items: Invoice[] }>(`/v1/invoices?customer_id=${id}`),
        api.get<Record<string, SatelliteImageData>>("/v1/satellite/images/heroes").catch(() => ({})),
      ]);
      setCustomer(c);
      setCustForm(c);
      setProperties(p.items);
      setInvoices(inv.items);
      setHeroImages(heroes);
    } catch {
      toast.error("Failed to load client");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Fetch full BOW data (with equipment, dimensions, etc.) for all properties
  useEffect(() => {
    if (properties.length === 0) return;
    Promise.all(
      properties.map((p) => api.get<BodyOfWater[]>(`/v1/bodies-of-water/property/${p.id}`).catch(() => []))
    ).then((results) => setFullBows(results.flat()));
  }, [properties]);

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
          company_name: custForm.company_name || null, customer_type: custForm.customer_type,
          email: custForm.email || null, phone: custForm.phone || null,
          billing_address: custForm.billing_address || null, billing_city: custForm.billing_city || null,
          billing_state: custForm.billing_state || null, billing_zip: custForm.billing_zip || null,
          service_frequency: custForm.service_frequency || null, preferred_day: custForm.preferred_day || null,
          billing_frequency: custForm.billing_frequency, monthly_rate: custForm.monthly_rate,
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
      toast.success("Client updated");
      setCustDirty(false);
      setPropDirty(false);
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

  const handleCancelCustomer = () => {
    setCustForm(customer);
    setCustDirty(false);
  };

  const handleCancelProperty = () => {
    if (singleProp) setPropForm(singleProp);
    setPropDirty(false);
  };

  const handleExitDetails = () => {
    if (custDirty || propDirty) {
      setDiscardTarget("details");
      setShowDiscardDialog(true);
    } else {
      setEditingDetails(false);
    }
  };

  const handleExitBows = () => {
    setEditingBows(false);
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

              {/* Address */}
              {properties.length >= 1 && (
                <div className="text-sm space-y-0.5 pt-1 border-t">
                  <div className="flex items-start gap-1.5 pt-1.5">
                    <MapPin className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground" />
                    <span>{properties[0].address}, {properties[0].city}, {properties[0].state} {properties[0].zip_code}</span>
                  </div>
                  {!isTech && <SiteDetails property={properties[0]} className="ml-5" />}
                </div>
              )}

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
                    { key: "bows" as const, icon: Droplets, label: "Water Features" },
                    { key: "details" as const, icon: History, label: "History" },
                  ]
                : [
                    { key: "overview" as const, icon: LayoutDashboard, label: "Overview" },
                    { key: "details" as const, icon: ClipboardList, label: "Details" },
                    { key: "bows" as const, icon: Droplets, label: "Water Features" },
                    ...(perms.canViewInvoices ? [{ key: "invoices" as const, icon: Receipt, label: "Invoices" }] : []),
                  ]
              ),
            ].map((nav) => (
              <button
                key={nav.key}
                onClick={() => setViewTab(nav.key)}
                className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm font-medium transition-colors shrink-0 lg:w-full ${
                  viewTab === nav.key
                    ? "bg-primary text-primary-foreground border-primary shadow-sm"
                    : "bg-background hover:bg-muted/50 border-border"
                }`}
              >
                <nav.icon className={`h-5 w-5 ${viewTab === nav.key ? "opacity-80" : "text-muted-foreground"}`} />
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
        const allBows = properties.flatMap(p => p.bodies_of_water || []);
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

            {/* Pool info for each BOW — what the tech needs to know */}
            {allBows.map((bow) => (
              <Card key={bow.id} className="shadow-sm">
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <Droplets className="h-4 w-4 text-muted-foreground" />
                    <CardTitle className="text-sm capitalize">{bow.name || bow.water_type.replace("_", " ")}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="text-sm space-y-2">
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <p className="text-xs text-muted-foreground">Gallons</p>
                      <p className="font-medium">{bow.pool_gallons ? bow.pool_gallons.toLocaleString() : "\u2014"}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Service Time</p>
                      <p className="font-medium">{bow.estimated_service_minutes} min</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Type</p>
                      <p className="font-medium capitalize">{bow.pool_type || "\u2014"}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
            {allBows.length === 0 && (
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
        const allBows = properties.flatMap(p => p.bodies_of_water || []);

        return (
          <div className="space-y-4">
            {/* Metric cards */}
            <div className={`grid grid-cols-2 ${perms.canViewRates ? "lg:grid-cols-4" : "lg:grid-cols-2"} gap-3`}>
              {perms.canViewRates && (
                <Card className="shadow-sm">
                  <CardContent className="pt-3 pb-3">
                    <div className="flex items-center gap-2 mb-1">
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Monthly Rate</p>
                    </div>
                    <p className="text-2xl font-bold">${customer.monthly_rate.toFixed(2)}</p>
                  </CardContent>
                </Card>
              )}
              {perms.canViewBalance && (
                <Card className={`shadow-sm ${outstandingTotal > 0 ? "border-red-200" : ""}`}>
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
                <Card className="shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Outstanding Invoices</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {unpaidInvoices.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-3">No outstanding invoices</p>
                    ) : (
                      <div className="space-y-2">
                        {unpaidInvoices.slice(0, 5).map((inv) => (
                          <div key={inv.id} className="flex items-center justify-between text-sm">
                            <div>
                              <Link href={`/invoices/${inv.id}`} className="font-medium hover:underline">{inv.invoice_number}</Link>
                              <span className="text-muted-foreground ml-2">{inv.issue_date}</span>
                            </div>
                            <span className="text-red-600 font-medium">${inv.balance.toFixed(2)}</span>
                          </div>
                        ))}
                        {unpaidInvoices.length > 5 && (
                          <button onClick={() => setViewTab("invoices")} className="text-xs text-muted-foreground hover:text-foreground">
                            +{unpaidInvoices.length - 5} more
                          </button>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Water Features summary */}
              <Card className="shadow-sm">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Water Features</CardTitle>
                </CardHeader>
                <CardContent>
                  {allBows.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-3">No water features</p>
                  ) : (
                    <div className="space-y-3">
                      {properties.map((prop) => {
                        const bows = prop.bodies_of_water || [];
                        if (bows.length === 0) return null;
                        const hero = heroImages[prop.id];
                        return (
                          <div key={prop.id}>
                            {properties.length > 1 && (
                              <div className="flex items-center gap-1.5 mb-2">
                                <MapPin className="h-3 w-3 text-muted-foreground" />
                                <span className="text-xs font-medium text-muted-foreground">{prop.name || prop.address}</span>
                              </div>
                            )}
                            {hero && (
                              <img
                                src={`${API_BASE}${hero.url}`}
                                alt="Satellite view"
                                className="w-full h-28 object-cover rounded-md border mb-2"
                              />
                            )}
                            <div className="space-y-2">
                              {bows.map((bow) => (
                                <div key={bow.id} className="bg-muted/50 rounded-md p-2.5">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <Droplets className="h-3.5 w-3.5 text-blue-500" />
                                    <span className="font-medium text-sm capitalize">{bow.name || bow.water_type.replace("_", " ")}</span>
                                    {bow.pool_type && (
                                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 capitalize ml-auto">{bow.pool_type}</Badge>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-3 gap-x-3 text-xs">
                                    <div>
                                      <span className="text-muted-foreground">Gallons</span>
                                      <p className="font-medium">{bow.pool_gallons ? bow.pool_gallons.toLocaleString() : "\u2014"}</p>
                                    </div>
                                    <div>
                                      <span className="text-muted-foreground">Service</span>
                                      <p className="font-medium">{bow.estimated_service_minutes} min</p>
                                    </div>
                                    {bow.monthly_rate != null ? (
                                      <div>
                                        <span className="text-muted-foreground">Rate</span>
                                        <p className="font-medium">${bow.monthly_rate.toFixed(2)}</p>
                                      </div>
                                    ) : bow.pool_sqft ? (
                                      <div>
                                        <span className="text-muted-foreground">Size</span>
                                        <p className="font-medium">{bow.pool_sqft.toLocaleString()} ft²</p>
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
                  )}
                </CardContent>
              </Card>
            </div>

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
        );
      })()}

      {/* ===== DETAILS TAB ===== */}
      {viewTab === "details" && (
        <Card className={`shadow-sm ${editingDetails ? `bg-muted/50 ${custDirty || propDirty ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-primary"}` : ""}`}>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Details</CardTitle>
              {!editingDetails && perms.canEditCustomers && (
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setEditingDetails(true)}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              )}
              {editingDetails && (
                <div className="flex gap-1.5">
                  {(custDirty || propDirty) && (
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
                {/* Top row: billing + service side by side on desktop */}
                <div className={`grid grid-cols-1 ${perms.canViewRates ? "lg:grid-cols-2" : ""} gap-4`}>
                  {/* Billing — only for roles that can see rates */}
                  {perms.canViewRates && (
                    <Card className="shadow-sm">
                      <CardHeader className="pb-2">
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

                  {/* Service */}
                  <Card className="shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Service</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm space-y-2">
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                        <div><span className="text-muted-foreground">Frequency: </span><span className="capitalize">{customer.service_frequency || "weekly"}</span></div>
                        <div>
                          <span className="text-muted-foreground">Days: </span>
                          {customer.preferred_day
                            ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ")
                            : "Any"}
                        </div>
                      </div>
                      {singleProp && (
                        <div className="pt-1.5 border-t space-y-1">
                          <p className="text-xs text-muted-foreground">Site Access</p>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                            <div><span className="text-muted-foreground">Gate: </span>{properties[0].gate_code || "\u2014"}</div>
                            <div>{properties[0].dog_on_property ? <span className="text-amber-600 font-medium">Dog on property</span> : <span className="text-muted-foreground">No dog</span>}</div>
                          </div>
                          {properties[0].access_instructions && (
                            <div><span className="text-muted-foreground">Access: </span>{properties[0].access_instructions}</div>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Notes — always present */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-2">
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
                          <Input value={custForm.company_name ?? ""} onChange={(e) => setCustField("company_name", e.target.value)} className="h-9" />
                        </div>
                      )}
                    </div>
                    {/* Service address inline */}
                    {singleProp && propForm && (
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
                    {singleProp && propForm && (
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
      )}

      {/* ===== BOWS TAB ===== */}
      {viewTab === "bows" && (
        <Card className={`shadow-sm ${editingBows ? "border-l-4 border-l-primary" : ""}`}>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Water Features</CardTitle>
              {!editingBows && perms.canEditCustomers && (
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setEditingBows(true)}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              )}
              {editingBows && (
                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={handleExitBows}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {!editingBows ? (
              /* --- BOW View --- */
              <div className="space-y-6">
                {properties.length === 0 && (
                  <p className="text-center text-muted-foreground py-6 text-sm">No service location yet</p>
                )}
                {properties.map((prop) => {
                  const propBows = fullBows.filter((b) => b.property_id === prop.id);
                  const summaryBows = prop.bodies_of_water || [];
                  const bows = propBows.length > 0 ? propBows : summaryBows;
                  const hero = heroImages[prop.id];
                  if (bows.length === 0 && properties.length === 1) {
                    return <p key={prop.id} className="text-center text-muted-foreground py-6 text-sm">No water features</p>;
                  }
                  if (bows.length === 0) return null;
                  return (
                    <div key={prop.id} className="space-y-4">
                      {/* Property header with satellite */}
                      {(properties.length > 1 || hero) && (
                        <div className="relative rounded-lg overflow-hidden border">
                          {hero ? (
                            <>
                              <img
                                src={`${API_BASE}${hero.url}`}
                                alt="Satellite view"
                                className="w-full h-40 object-cover"
                              />
                              {properties.length > 1 && (
                                <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent px-4 py-3">
                                  <div className="flex items-center gap-2 text-white">
                                    <MapPin className="h-3.5 w-3.5" />
                                    <span className="text-sm font-medium">{prop.name || prop.address}, {prop.city}</span>
                                  </div>
                                </div>
                              )}
                            </>
                          ) : properties.length > 1 ? (
                            <div className="bg-muted/30 px-4 py-3">
                              <div className="flex items-center gap-2 text-sm font-medium">
                                <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                                <span>{prop.name || prop.address}, {prop.city}</span>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      )}

                      {bows.map((bow) => {
                        const isFull = "pump_type" in bow;
                        const fb = isFull ? (bow as BodyOfWater) : null;
                        const v = (val: string | number | null | undefined, suffix = "") =>
                          val != null && val !== "" ? <span className="font-medium">{val}{suffix}</span> : <span className="text-muted-foreground/50 italic">Not set</span>;

                        return (
                          <div key={bow.id} className="space-y-3">
                            {/* BOW Header Bar */}
                            <div className="flex items-center gap-3 bg-primary text-primary-foreground px-4 py-2.5 rounded-lg">
                              <Waves className="h-4 w-4 opacity-70" />
                              <span className="text-xs font-medium uppercase tracking-wide capitalize">{bow.name || bow.water_type.replace("_", " ")}</span>
                              {bow.pool_type && <Badge className="bg-white/15 text-primary-foreground text-[10px] px-1.5 py-0 capitalize hover:bg-white/15">{bow.pool_type}</Badge>}
                              <div className="ml-auto flex items-center gap-1">
                                {bow.water_type === "pool" && (
                                <Link href={`/satellite?bow=${bow.id}`}>
                                  <Button variant="ghost" size="icon" className="h-7 w-7 text-primary-foreground/70 hover:text-primary-foreground hover:bg-white/10">
                                    <Satellite className="h-3.5 w-3.5" />
                                  </Button>
                                </Link>
                                )}
                                {perms.canMeasure && (
                                  <Link href={`/properties/${prop.id}/measure?bow=${bow.id}`}>
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-primary-foreground/70 hover:text-primary-foreground hover:bg-white/10">
                                      <Ruler className="h-3.5 w-3.5" />
                                    </Button>
                                  </Link>
                                )}
                              </div>
                            </div>

                            {/* Metric Cards Row */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                              {[
                                { icon: Droplets, label: "Volume", value: bow.pool_gallons ? `${bow.pool_gallons.toLocaleString()}` : null, unit: "gal", color: "text-blue-500" },
                                { icon: Move, label: "Surface", value: bow.pool_sqft ? `${bow.pool_sqft.toLocaleString()}` : null, unit: "ft²", color: "text-emerald-500" },
                                { icon: Clock, label: "Service", value: `${bow.estimated_service_minutes}`, unit: "min", color: "text-amber-500" },
                                { icon: DollarSign, label: "Rate", value: bow.monthly_rate != null ? `${bow.monthly_rate.toFixed(2)}` : null, unit: "/mo", color: "text-violet-500" },
                              ].map((m) => (
                                <div key={m.label} className="bg-background border rounded-lg px-3 py-2.5 shadow-sm">
                                  <div className="flex items-center gap-1.5 mb-1">
                                    <m.icon className={`h-3 w-3 ${m.color}`} />
                                    <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{m.label}</span>
                                  </div>
                                  {m.value ? (
                                    <p className="text-lg font-bold leading-tight">{m.value}<span className="text-xs font-normal text-muted-foreground ml-0.5">{m.unit}</span></p>
                                  ) : (
                                    <p className="text-sm text-muted-foreground/50 italic leading-tight mt-0.5">\u2014</p>
                                  )}
                                </div>
                              ))}
                            </div>

                            {/* Two-column grid for category tiles */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              {/* Dimensions Tile */}
                              <div className="bg-background border rounded-lg shadow-sm overflow-hidden">
                                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5">
                                  <Ruler className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Dimensions</span>
                                </div>
                                <div className="px-3 py-2.5 space-y-1.5">
                                  <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Shape</span>
                                    {fb?.pool_shape ? <span className="font-medium capitalize">{fb.pool_shape}</span> : <span className="text-muted-foreground/50 italic">Not set</span>}
                                  </div>
                                  <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">L × W</span>
                                    {fb?.pool_length_ft && fb?.pool_width_ft
                                      ? <span className="font-medium">{fb.pool_length_ft} × {fb.pool_width_ft} ft</span>
                                      : <span className="text-muted-foreground/50 italic">Not set</span>}
                                  </div>
                                  <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Depth</span>
                                    {fb?.pool_depth_shallow && fb?.pool_depth_deep
                                      ? <span className="font-medium">{fb.pool_depth_shallow}–{fb.pool_depth_deep} ft</span>
                                      : fb?.pool_depth_avg
                                      ? <span className="font-medium">{fb.pool_depth_avg} ft avg</span>
                                      : <span className="text-muted-foreground/50 italic">Not set</span>}
                                  </div>
                                  <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Surface</span>
                                    {fb?.pool_surface ? <span className="font-medium capitalize">{fb.pool_surface}</span> : <span className="text-muted-foreground/50 italic">Not set</span>}
                                  </div>
                                </div>
                              </div>

                              {/* Chemistry Tile */}
                              <div className="bg-background border rounded-lg shadow-sm overflow-hidden">
                                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5">
                                  <FlaskConical className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Chemistry</span>
                                </div>
                                <div className="px-3 py-2.5 space-y-1.5">
                                  <div className="flex justify-between items-center text-xs">
                                    <span className="text-muted-foreground">Sanitizer</span>
                                    {fb?.sanitizer_type
                                      ? <Badge variant="outline" className="text-[10px] capitalize px-1.5 py-0">{fb.sanitizer_type.replace(/_/g, " ")}</Badge>
                                      : <span className="text-muted-foreground/50 italic">Not set</span>}
                                  </div>
                                  <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Last Reading</span>
                                    <span className="text-muted-foreground/50 italic">None</span>
                                  </div>
                                </div>
                              </div>

                              {/* Equipment Tile — always show, full width */}
                              <div className="sm:col-span-2 bg-background border rounded-lg shadow-sm overflow-hidden">
                                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5">
                                  <Wrench className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Equipment</span>
                                </div>
                                <div className="px-3 py-2.5">
                                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                                    {[
                                      { icon: Gauge, label: "Pump", value: fb?.pump_type },
                                      { icon: FlaskConical, label: "Filter", value: fb?.filter_type },
                                      { icon: Thermometer, label: "Heater", value: fb?.heater_type },
                                      { icon: FlaskConical, label: "Chlorinator", value: fb?.chlorinator_type },
                                      { icon: Zap, label: "Automation", value: fb?.automation_system },
                                    ].map((e) => (
                                      <div key={e.label} className="flex items-center gap-2 text-xs">
                                        <e.icon className="h-3 w-3 text-muted-foreground shrink-0" />
                                        <span className="text-muted-foreground">{e.label}</span>
                                        <span className="truncate ml-auto">
                                          {e.value ? <span className="font-medium">{e.value}</span> : <span className="text-muted-foreground/50 italic">Not set</span>}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              {/* Notes Tile — always show */}
                              <div className="sm:col-span-2 bg-background border rounded-lg shadow-sm overflow-hidden">
                                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5">
                                  <StickyNote className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Notes</span>
                                </div>
                                <div className="px-3 py-2.5">
                                  {fb?.notes
                                    ? <p className="text-xs text-muted-foreground whitespace-pre-wrap">{fb.notes}</p>
                                    : <p className="text-xs text-muted-foreground/50 italic">No notes</p>}
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            ) : (
              /* --- BOW Edit --- */
              <div className="space-y-3">
                {singleProp && (
                  <SinglePropertyBowSection propertyId={singleProp.id} onBowChange={load} />
                )}
                {properties.length > 1 && (
                  properties.map((p) => (
                    <PropertyEditCard
                      key={p.id}
                      property={p}
                      customer={customer}
                      onSave={(data) => handleSaveProperty(p.id, data)}
                      onDelete={() => handleDeleteProperty(p.id)}
                      onBowChange={load}
                    />
                  ))
                )}
                <Button variant="outline" size="sm" className="h-8" onClick={() => setAddingProp(!addingProp)}>
                  <Plus className="h-3.5 w-3.5 mr-1" />{properties.length <= 1 ? "Add another location" : "Add location"}
                </Button>
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
                          <Button type="submit" className="flex-1 h-9">Add Location</Button>
                        </div>
                      </form>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </CardContent>
        </Card>
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
