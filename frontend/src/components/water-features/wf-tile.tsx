"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EquipmentInput } from "@/components/equipment/equipment-input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  Pencil,
  X,
  Trash2,
  Loader2,
  Droplets,
  Clock,
  DollarSign,
  Ruler,
  Waves,
  Gauge,
  Thermometer,
  Zap,
  FlaskConical,
  Move,
  StickyNote,
  Wrench,
  Satellite,
  Shield,
  Pipette,
  CircleDot,
  MapPin,
  WavesLadder,
} from "lucide-react";
import { WfQuickView, type WfQuickViewReading } from "./wf-quick-view";

function waterTypeIcon(type: string, className: string) {
  switch (type) {
    case "spa": case "hot_tub": return <Droplets className={className} />;
    case "fountain": case "water_feature": case "wading_pool": return <Waves className={className} />;
    default: return <WavesLadder className={className} />;
  }
}
import Link from "next/link";
import type { Permissions } from "@/lib/permissions";

export interface WaterFeature {
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
  fill_method: string | null;
  drain_type: string | null;
  drain_method: string | null;
  drain_count: number | null;
  drain_cover_compliant: boolean | null;
  drain_cover_install_date: string | null;
  drain_cover_expiry_date: string | null;
  equalizer_cover_compliant: boolean | null;
  equalizer_cover_install_date: string | null;
  equalizer_cover_expiry_date: string | null;
  plumbing_size_inches: number | null;
  pool_cover_type: string | null;
  turnover_hours: number | null;
  skimmer_count: number | null;
  equipment_year: number | null;
  equipment_pad_location: string | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
  notes: string | null;
  is_active: boolean;
}

export interface TechAssignment {
  tech_id: string;
  tech_name: string;
  color: string;
  service_days: string[];
}

const DIM_SOURCE_LABELS: Record<string, string> = {
  inspection: "Inspection",
  perimeter: "Perimeter",
  measurement: "Measured",
  satellite: "Satellite",
  manual: "Manual",
};

const DIM_SOURCE_COLORS: Record<string, string> = {
  inspection: "bg-green-100 text-green-800",
  perimeter: "bg-green-100 text-green-800",
  measurement: "bg-blue-100 text-blue-800",
  satellite: "bg-yellow-100 text-yellow-800",
  manual: "bg-gray-100 text-gray-600",
};

const numOrNull = (v: string) => { const n = parseFloat(v); return isNaN(n) ? null : n; };
const intOrNull = (v: string) => { const n = parseInt(v); return isNaN(n) ? null : n; };

interface DifficultyAdjustments {
  res_tree_debris: number;
  res_dog: number;
  res_customer_demands: number;
  res_system_effectiveness: number;
}

interface PropertyContext {
  gate_code: string | null;
  access_instructions: string | null;
  dog_on_property: boolean;
  service_day_pattern: string | null;
}

interface CustomerContext {
  preferred_day: string | null;
}

interface WfTileProps {
  wf: WaterFeature;
  propertyId: string;
  perms: Permissions;
  techAssignment?: TechAssignment;
  suggestedRate?: number | null;
  marginPct?: number | null;
  customerType?: string;
  collapsed?: boolean;
  propertyContext?: PropertyContext;
  customerContext?: CustomerContext;
  lastReading?: WfQuickViewReading | null;
  onExpand?: () => void;
  onUpdated: () => void;
  onDeleted: () => void;
}

export function WfTile({ wf, propertyId, perms, techAssignment, suggestedRate, marginPct, customerType, collapsed, propertyContext, customerContext, lastReading, onExpand, onUpdated, onDeleted }: WfTileProps) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ ...wf });
  const [diffAdj, setDiffAdj] = useState<DifficultyAdjustments | null>(null);
  const [diffSaving, setDiffSaving] = useState(false);

  // Load difficulty adjustments
  const isResidential = customerType !== "commercial";
  useEffect(() => {
    if (!isResidential) return;
    api.get<{ res_tree_debris: number; res_dog: number; res_customer_demands: number; res_system_effectiveness: number }>(`/v1/profitability/properties/${propertyId}/difficulty`)
      .then((d) => setDiffAdj({ res_tree_debris: d.res_tree_debris || 0, res_dog: d.res_dog || 0, res_customer_demands: d.res_customer_demands || 0, res_system_effectiveness: d.res_system_effectiveness || 0 }))
      .catch(() => setDiffAdj({ res_tree_debris: 0, res_dog: 0, res_customer_demands: 0, res_system_effectiveness: 0 }));
  }, [propertyId, isResidential]);

  const saveDiffAdj = async (field: string, value: number) => {
    setDiffSaving(true);
    try {
      await api.put(`/v1/profitability/properties/${propertyId}/difficulty`, { [field]: value });
      setDiffAdj(prev => prev ? { ...prev, [field]: value } : null);
      onUpdated();
    } catch (e) {
      toast.error("Failed to save adjustment");
      console.error("saveDiffAdj error:", e);
    } finally {
      setDiffSaving(false);
    }
  };
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const set = (field: string, value: unknown) => {
    setForm((f) => ({ ...f, [field]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/v1/water-features/${wf.id}`, {
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
        fill_method: form.fill_method || null,
        drain_type: form.drain_type || null,
        drain_method: form.drain_method || null,
        drain_count: form.drain_count,
        drain_cover_compliant: form.drain_cover_compliant,
        drain_cover_install_date: form.drain_cover_install_date || null,
        drain_cover_expiry_date: form.drain_cover_expiry_date || null,
        equalizer_cover_compliant: form.equalizer_cover_compliant,
        equalizer_cover_install_date: form.equalizer_cover_install_date || null,
        equalizer_cover_expiry_date: form.equalizer_cover_expiry_date || null,
        plumbing_size_inches: form.plumbing_size_inches,
        pool_cover_type: form.pool_cover_type || null,
        turnover_hours: form.turnover_hours,
        skimmer_count: form.skimmer_count,
        equipment_year: form.equipment_year,
        equipment_pad_location: form.equipment_pad_location || null,
        estimated_service_minutes: form.estimated_service_minutes,
        monthly_rate: form.monthly_rate,
        notes: form.notes || null,
      });
      toast.success("Saved");
      setDirty(false);
      setEditing(false);
      onUpdated();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setForm({ ...wf });
    setDirty(false);
    setEditing(false);
  };

  const handleDelete = async () => {
    try {
      await api.delete(`/v1/water-features/${wf.id}`);
      toast.success("Deleted");
      onDeleted();
    } catch {
      toast.error("Failed to delete");
    }
  };

  const fb = wf;

  if (editing) {
    return (
      <div className="rounded-lg border shadow-sm bg-card p-4 space-y-3 border-l-4 border-l-primary">
        {/* WF Header Bar — edit mode */}
        <div className="flex items-center gap-3">
          {waterTypeIcon(wf.water_type, "h-4 w-4 text-primary/60")}
          <span className="text-xs font-semibold uppercase tracking-widest text-foreground/70 capitalize">
            {form.name || form.water_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            {dirty && (
              <Button variant="default" size="sm" className="h-7 px-2.5 text-xs" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
              </Button>
            )}
            {dirty && (
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => { setForm({ ...wf }); setDirty(false); }}>
                Cancel
              </Button>
            )}
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={handleCancel}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Edit form */}
        <div className="border border-l-4 border-l-primary rounded-lg p-4 space-y-4 bg-muted/50">
          {/* Identity */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Identity</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Name</Label>
                <Input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Lap Pool" className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Type</Label>
                <Select value={form.water_type} onValueChange={(v) => set("water_type", v)}>
                  <SelectTrigger className="h-8 text-sm bg-background"><SelectValue /></SelectTrigger>
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
                  <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="commercial">Commercial</SelectItem>
                    <SelectItem value="residential">Residential</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Volume & Service */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Volume & Service</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Gallons</Label>
                <Input type="number" value={form.pool_gallons ?? ""} onChange={(e) => set("pool_gallons", intOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Sqft</Label>
                <Input type="number" step="0.1" value={form.pool_sqft ?? ""} onChange={(e) => set("pool_sqft", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Service (min)</Label>
                <Input type="number" value={form.estimated_service_minutes} onChange={(e) => set("estimated_service_minutes", parseInt(e.target.value) || 30)} className="h-8 text-sm bg-background" />
              </div>
              {perms.canEditRates && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Monthly Rate ($)</Label>
                  <Input type="number" step="0.01" value={form.monthly_rate ?? ""} onChange={(e) => set("monthly_rate", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
                </div>
              )}
            </div>
          </div>

          {/* Dimensions */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Dimensions</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Length (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_length_ft ?? ""} onChange={(e) => set("pool_length_ft", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Width (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_width_ft ?? ""} onChange={(e) => set("pool_width_ft", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Shape</Label>
                <Select value={form.pool_shape ?? ""} onValueChange={(v) => set("pool_shape", v || null)}>
                  <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="..." /></SelectTrigger>
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
            <div className="grid grid-cols-3 gap-2 mt-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Shallow (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_depth_shallow ?? ""} onChange={(e) => set("pool_depth_shallow", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Deep (ft)</Label>
                <Input type="number" step="0.1" value={form.pool_depth_deep ?? ""} onChange={(e) => set("pool_depth_deep", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Surface</Label>
                <Select value={form.pool_surface ?? ""} onValueChange={(v) => set("pool_surface", v || null)}>
                  <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="..." /></SelectTrigger>
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
          </div>

          {/* Chemistry & Equipment */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Chemistry & Equipment</p>
            <div className="space-y-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Sanitizer</Label>
                <Select value={form.sanitizer_type ?? ""} onValueChange={(v) => set("sanitizer_type", v || null)}>
                  <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="Select..." /></SelectTrigger>
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
                  <EquipmentInput value={form.pump_type ?? ""} onChange={(v) => set("pump_type", v)} equipmentType="pump" className="h-8 text-sm bg-background" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Filter</Label>
                  <EquipmentInput value={form.filter_type ?? ""} onChange={(v) => set("filter_type", v)} equipmentType="filter" className="h-8 text-sm bg-background" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Heater</Label>
                  <EquipmentInput value={form.heater_type ?? ""} onChange={(v) => set("heater_type", v)} equipmentType="heater" className="h-8 text-sm bg-background" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Chlorinator</Label>
                  <EquipmentInput value={form.chlorinator_type ?? ""} onChange={(v) => set("chlorinator_type", v)} equipmentType="chlorinator" className="h-8 text-sm bg-background" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Automation</Label>
                  <EquipmentInput value={form.automation_system ?? ""} onChange={(v) => set("automation_system", v)} equipmentType="automation" className="h-8 text-sm bg-background" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Equipment Year</Label>
                  <Input type="number" value={form.equipment_year ?? ""} onChange={(e) => set("equipment_year", intOrNull(e.target.value))} className="h-8 text-sm bg-background" placeholder="e.g. 2020" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Equipment Pad Location</Label>
                <Input value={form.equipment_pad_location ?? ""} onChange={(e) => set("equipment_pad_location", e.target.value)} className="h-8 text-sm bg-background" placeholder="e.g. East side of pool" />
              </div>
            </div>
          </div>

          {/* Infrastructure */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Infrastructure</p>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Pool Cover</Label>
                  <Select value={form.pool_cover_type ?? ""} onValueChange={(v) => set("pool_cover_type", v || null)}>
                    <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="Select..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="automatic">Automatic</SelectItem>
                      <SelectItem value="manual">Manual</SelectItem>
                      <SelectItem value="safety_net">Safety Net</SelectItem>
                      <SelectItem value="none">None</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Skimmers</Label>
                  <Input type="number" value={form.skimmer_count ?? ""} onChange={(e) => set("skimmer_count", intOrNull(e.target.value))} className="h-8 text-sm bg-background" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Fill Method</Label>
                  <Select value={form.fill_method ?? ""} onValueChange={(v) => set("fill_method", v || null)}>
                    <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="Select..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="tap">Tap</SelectItem>
                      <SelectItem value="ro_system">RO System</SelectItem>
                      <SelectItem value="truck">Truck</SelectItem>
                      <SelectItem value="recycled">Recycled</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Plumbing Size (in)</Label>
                  <Input type="number" step="0.25" value={form.plumbing_size_inches ?? ""} onChange={(e) => set("plumbing_size_inches", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Drain Type</Label>
                  <Select value={form.drain_type ?? ""} onValueChange={(v) => set("drain_type", v || null)}>
                    <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="Select..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="main_drain">Main Drain</SelectItem>
                      <SelectItem value="surge">Surge</SelectItem>
                      <SelectItem value="circulation">Circulation</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Drain Method</Label>
                  <Select value={form.drain_method ?? ""} onValueChange={(v) => set("drain_method", v || null)}>
                    <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="Select..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sewer">Sewer</SelectItem>
                      <SelectItem value="catch_basin">Catch Basin</SelectItem>
                      <SelectItem value="storm_drain">Storm Drain</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Drain Count</Label>
                  <Input type="number" value={form.drain_count ?? ""} onChange={(e) => set("drain_count", intOrNull(e.target.value))} className="h-8 text-sm bg-background" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Turnover (hours)</Label>
                <Input type="number" step="0.5" value={form.turnover_hours ?? ""} onChange={(e) => set("turnover_hours", numOrNull(e.target.value))} className="h-8 text-sm bg-background" />
              </div>
            </div>
          </div>

          {/* Drain Covers (Compliance) */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Drain Cover Compliance</p>
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Drain Cover Compliant</Label>
                  <Select value={form.drain_cover_compliant == null ? "" : form.drain_cover_compliant ? "yes" : "no"} onValueChange={(v) => set("drain_cover_compliant", v === "" ? null : v === "yes")}>
                    <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="yes">Yes</SelectItem>
                      <SelectItem value="no">No</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Install Date</Label>
                  <Input type="date" value={form.drain_cover_install_date ? form.drain_cover_install_date.slice(0, 10) : ""} onChange={(e) => set("drain_cover_install_date", e.target.value ? new Date(e.target.value).toISOString() : null)} className="h-8 text-sm bg-background" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Expiry Date</Label>
                  <Input type="date" value={form.drain_cover_expiry_date ? form.drain_cover_expiry_date.slice(0, 10) : ""} onChange={(e) => set("drain_cover_expiry_date", e.target.value ? new Date(e.target.value).toISOString() : null)} className="h-8 text-sm bg-background" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Equalizer Compliant</Label>
                  <Select value={form.equalizer_cover_compliant == null ? "" : form.equalizer_cover_compliant ? "yes" : "no"} onValueChange={(v) => set("equalizer_cover_compliant", v === "" ? null : v === "yes")}>
                    <SelectTrigger className="h-8 text-sm bg-background"><SelectValue placeholder="..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="yes">Yes</SelectItem>
                      <SelectItem value="no">No</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Install Date</Label>
                  <Input type="date" value={form.equalizer_cover_install_date ? form.equalizer_cover_install_date.slice(0, 10) : ""} onChange={(e) => set("equalizer_cover_install_date", e.target.value ? new Date(e.target.value).toISOString() : null)} className="h-8 text-sm bg-background" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Expiry Date</Label>
                  <Input type="date" value={form.equalizer_cover_expiry_date ? form.equalizer_cover_expiry_date.slice(0, 10) : ""} onChange={(e) => set("equalizer_cover_expiry_date", e.target.value ? new Date(e.target.value).toISOString() : null)} className="h-8 text-sm bg-background" />
                </div>
              </div>
            </div>
          </div>

          {/* Notes */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Notes</p>
            <Textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2} className="bg-background" />
          </div>

          {/* Delete button at bottom */}
          <div className="flex justify-end pt-2 border-t">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 text-xs text-destructive hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5 mr-1" />
                  Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete {form.name || form.water_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}?</AlertDialogTitle>
                  <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>
    );
  }

  // --- View mode --- uses WfQuickView
  return (
    <WfQuickView
      wf={wf}
      property={propertyContext || { gate_code: null, access_instructions: null, dog_on_property: false, service_day_pattern: null }}
      customer={customerContext || { preferred_day: null }}
      lastReading={lastReading}
      perms={perms}
      onEdit={perms.canEditCustomers ? () => setEditing(true) : undefined}
    />
  );
}
