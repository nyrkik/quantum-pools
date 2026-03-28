"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  ChevronDown,
  ChevronUp,
  DollarSign,
  Pencil,
  Check,
  X,
  Loader2,
  Ruler,
  Search,
  Shield,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { EquipmentInput } from "@/components/equipment/equipment-input";
import type { Permissions } from "@/lib/permissions";

interface WfFields {
  id: string;
  pump_type: string | null;
  filter_type: string | null;
  heater_type: string | null;
  chlorinator_type: string | null;
  automation_system: string | null;
  equipment_year: number | null;
  equipment_pad_location: string | null;
  pool_shape: string | null;
  pool_length_ft: number | null;
  pool_width_ft: number | null;
  pool_depth_shallow: number | null;
  pool_depth_deep: number | null;
  pool_depth_avg: number | null;
  pool_surface: string | null;
  pool_sqft: number | null;
  perimeter_ft: number | null;
  monthly_rate: number | null;
  pool_type: string | null;
  drain_cover_compliant: boolean | null;
  drain_cover_install_date: string | null;
  drain_cover_expiry_date: string | null;
  equalizer_cover_compliant: boolean | null;
  plumbing_size_inches: number | null;
  turnover_hours: number | null;
  skimmer_count: number | null;
  pool_cover_type: string | null;
  fill_method: string | null;
}

interface WfDetailSectionsProps {
  wf: WfFields;
  perms: Permissions;
  canEdit?: boolean;
  onUpdate?: () => void;
}

// --- Shared components ---

function CollapsibleSection({ icon: Icon, title, children, editing, onEdit, onSave, onCancel, saving, canEdit, open, onToggle }: {
  icon: React.ElementType; title: string; children: React.ReactNode;
  editing?: boolean; onEdit?: () => void; onSave?: () => void; onCancel?: () => void;
  saving?: boolean; canEdit?: boolean;
  open: boolean; onToggle: () => void;
}) {
  return (
    <Collapsible open={open} onOpenChange={onToggle}>
      <CollapsibleTrigger asChild>
        <button type="button" className="flex items-center gap-2 w-full px-3 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors cursor-pointer min-h-[44px]">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</span>
          {open && canEdit && !editing && onEdit && (
            <button type="button" className="ml-2 p-1 rounded hover:bg-muted" onClick={(e) => { e.stopPropagation(); onEdit(); }}>
              <Pencil className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
          {open && editing && (
            <div className="ml-2 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              <button type="button" className="p-1 rounded hover:bg-green-100 text-green-600" onClick={onSave} disabled={saving}>
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              </button>
              <button type="button" className="p-1 rounded hover:bg-red-100 text-red-500" onClick={onCancel}>
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
          <span className="ml-auto">
            {open ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex justify-between text-xs py-0.5">
      <span className="text-muted-foreground">{label}</span>
      {value ? <span className="font-medium capitalize">{value.replace(/_/g, " ")}</span> : <span className="text-muted-foreground/50 italic">--</span>}
    </div>
  );
}

function EditRow({ label, value, onChange, type = "text", placeholder }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs py-0.5">
      <span className="text-muted-foreground w-20 flex-shrink-0">{label}</span>
      <Input value={value} onChange={(e) => onChange(e.target.value)} type={type} placeholder={placeholder} className="h-7 text-xs flex-1" />
    </div>
  );
}

// --- Main component ---

export function WfDetailSections({ wf, perms, canEdit = false, onUpdate }: WfDetailSectionsProps) {
  const [openSection, setOpenSection] = useState<string | null>(null);
  const toggle = (section: string) => setOpenSection(openSection === section ? null : section);

  // Equipment edit state
  const [editingEquip, setEditingEquip] = useState(false);
  const [savingEquip, setSavingEquip] = useState(false);
  const [equipForm, setEquipForm] = useState({
    pump_type: wf.pump_type || "",
    filter_type: wf.filter_type || "",
    heater_type: wf.heater_type || "",
    chlorinator_type: wf.chlorinator_type || "",
    automation_system: wf.automation_system || "",
  });

  const handleSaveEquip = async () => {
    setSavingEquip(true);
    try {
      await api.put(`/v1/bodies-of-water/${wf.id}`, equipForm);
      toast.success("Equipment updated");
      setEditingEquip(false);
      onUpdate?.();
    } catch { toast.error("Failed to save"); }
    finally { setSavingEquip(false); }
  };

  // Dimensions edit state
  const [editingDims, setEditingDims] = useState(false);
  const [savingDims, setSavingDims] = useState(false);
  const [dimsForm, setDimsForm] = useState({
    pool_length_ft: String(wf.pool_length_ft || ""),
    pool_width_ft: String(wf.pool_width_ft || ""),
    pool_depth_shallow: String(wf.pool_depth_shallow || ""),
    pool_depth_deep: String(wf.pool_depth_deep || ""),
    pool_shape: wf.pool_shape || "",
    pool_surface: wf.pool_surface || "",
  });

  const handleSaveDims = async () => {
    setSavingDims(true);
    try {
      await api.put(`/v1/bodies-of-water/${wf.id}`, {
        pool_length_ft: dimsForm.pool_length_ft ? parseFloat(dimsForm.pool_length_ft) : null,
        pool_width_ft: dimsForm.pool_width_ft ? parseFloat(dimsForm.pool_width_ft) : null,
        pool_depth_shallow: dimsForm.pool_depth_shallow ? parseFloat(dimsForm.pool_depth_shallow) : null,
        pool_depth_deep: dimsForm.pool_depth_deep ? parseFloat(dimsForm.pool_depth_deep) : null,
        pool_shape: dimsForm.pool_shape || null,
        pool_surface: dimsForm.pool_surface || null,
      });
      toast.success("Dimensions updated");
      setEditingDims(false);
      onUpdate?.();
    } catch { toast.error("Failed to save"); }
    finally { setSavingDims(false); }
  };

  return (
    <div className="border-t">
      {/* Equipment */}
      <CollapsibleSection
        icon={Wrench} title="Equipment" canEdit={canEdit}
        open={openSection === "equipment"} onToggle={() => toggle("equipment")}
        editing={editingEquip}
        onEdit={() => setEditingEquip(true)}
        onSave={handleSaveEquip}
        onCancel={() => { setEditingEquip(false); setEquipForm({ pump_type: wf.pump_type || "", filter_type: wf.filter_type || "", heater_type: wf.heater_type || "", chlorinator_type: wf.chlorinator_type || "", automation_system: wf.automation_system || "" }); }}
        saving={savingEquip}
      >
        <div className="px-3 py-2.5 space-y-2 border-b">
          {editingEquip ? (
            <>
              {(["pump", "filter", "heater", "chlorinator", "automation"] as const).map((type) => {
                const key = type === "automation" ? "automation_system" : `${type}_type` as keyof typeof equipForm;
                return (
                  <div key={type} className="space-y-0.5">
                    <label className="text-[10px] text-muted-foreground uppercase">{type}</label>
                    <EquipmentInput
                      value={equipForm[key]}
                      onChange={(v) => setEquipForm({ ...equipForm, [key]: v })}
                      equipmentType={type}
                      className="h-8 text-sm"
                      placeholder={`Enter ${type}...`}
                    />
                  </div>
                );
              })}
            </>
          ) : (
            <>
              {[
                { label: "Pump", value: wf.pump_type },
                { label: "Filter", value: wf.filter_type },
                { label: "Heater", value: wf.heater_type },
                { label: "Chlorinator", value: wf.chlorinator_type },
                { label: "Automation", value: wf.automation_system },
              ].map((eq) => (
                <div key={eq.label} className="flex items-center justify-between text-xs py-0.5">
                  <span className="text-muted-foreground">{eq.label}</span>
                  {eq.value ? (
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-right">{eq.value}</span>
                      <a href={`https://www.google.com/search?q=${encodeURIComponent(eq.value + " parts")}`} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground" onClick={(e) => e.stopPropagation()}>
                        <Search className="h-3 w-3" />
                      </a>
                    </div>
                  ) : (
                    <span className="text-muted-foreground/50 italic">--</span>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </CollapsibleSection>

      {/* Dimensions */}
      {perms.canViewDimensions && (
        <CollapsibleSection
          icon={Ruler} title="Dimensions" canEdit={canEdit && perms.canViewDimensions}
          open={openSection === "dimensions"} onToggle={() => toggle("dimensions")}
          editing={editingDims}
          onEdit={() => setEditingDims(true)}
          onSave={handleSaveDims}
          onCancel={() => { setEditingDims(false); setDimsForm({ pool_length_ft: String(wf.pool_length_ft || ""), pool_width_ft: String(wf.pool_width_ft || ""), pool_depth_shallow: String(wf.pool_depth_shallow || ""), pool_depth_deep: String(wf.pool_depth_deep || ""), pool_shape: wf.pool_shape || "", pool_surface: wf.pool_surface || "" }); }}
          saving={savingDims}
        >
          <div className="px-3 py-2.5 space-y-1.5 border-b">
            {editingDims ? (
              <>
                <EditRow label="Shape" value={dimsForm.pool_shape} onChange={(v) => setDimsForm({ ...dimsForm, pool_shape: v })} placeholder="Rectangle, Freeform..." />
                <EditRow label="Length (ft)" value={dimsForm.pool_length_ft} onChange={(v) => setDimsForm({ ...dimsForm, pool_length_ft: v })} type="number" />
                <EditRow label="Width (ft)" value={dimsForm.pool_width_ft} onChange={(v) => setDimsForm({ ...dimsForm, pool_width_ft: v })} type="number" />
                <EditRow label="Shallow (ft)" value={dimsForm.pool_depth_shallow} onChange={(v) => setDimsForm({ ...dimsForm, pool_depth_shallow: v })} type="number" />
                <EditRow label="Deep (ft)" value={dimsForm.pool_depth_deep} onChange={(v) => setDimsForm({ ...dimsForm, pool_depth_deep: v })} type="number" />
                <EditRow label="Surface" value={dimsForm.pool_surface} onChange={(v) => setDimsForm({ ...dimsForm, pool_surface: v })} placeholder="Plaster, Pebble..." />
              </>
            ) : (
              <>
                <DetailRow label="Shape" value={wf.pool_shape} />
                <div className="flex justify-between text-xs py-0.5">
                  <span className="text-muted-foreground">L x W</span>
                  {wf.pool_length_ft && wf.pool_width_ft ? <span className="font-medium">{wf.pool_length_ft} x {wf.pool_width_ft} ft</span> : <span className="text-muted-foreground/50 italic">--</span>}
                </div>
                <div className="flex justify-between text-xs py-0.5">
                  <span className="text-muted-foreground">Depth</span>
                  {wf.pool_depth_shallow && wf.pool_depth_deep ? <span className="font-medium">{wf.pool_depth_shallow}&ndash;{wf.pool_depth_deep} ft</span>
                    : wf.pool_depth_avg ? <span className="font-medium">{wf.pool_depth_avg} ft avg</span>
                    : <span className="text-muted-foreground/50 italic">--</span>}
                </div>
                <DetailRow label="Surface" value={wf.pool_surface} />
                {wf.pool_sqft && <DetailRow label="Area" value={`${wf.pool_sqft.toLocaleString()} sqft`} />}
                {wf.perimeter_ft && <DetailRow label="Perimeter" value={`${wf.perimeter_ft} ft`} />}
              </>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Compliance */}
      <CollapsibleSection icon={Shield} title="Compliance" open={openSection === "compliance"} onToggle={() => toggle("compliance")}>
        <div className="px-3 py-2.5 space-y-1.5 border-b">
          <div className="flex justify-between text-xs py-0.5">
            <span className="text-muted-foreground">Drain Covers</span>
            {wf.drain_cover_compliant != null ? (
              <Badge variant={wf.drain_cover_compliant ? "default" : "destructive"} className="text-[10px] h-4 px-1.5">
                {wf.drain_cover_compliant ? "Compliant" : "Non-Compliant"}
              </Badge>
            ) : <span className="text-muted-foreground/50 italic">--</span>}
          </div>
          {wf.drain_cover_expiry_date && <DetailRow label="Expires" value={new Date(wf.drain_cover_expiry_date).toLocaleDateString("en-US", { month: "short", year: "numeric" })} />}
          {wf.plumbing_size_inches && <DetailRow label="Plumbing" value={`${wf.plumbing_size_inches}"`} />}
          {wf.turnover_hours && <DetailRow label="Turnover" value={`${wf.turnover_hours} hrs`} />}
          {wf.skimmer_count && <DetailRow label="Skimmers" value={String(wf.skimmer_count)} />}
          {wf.pool_cover_type && <DetailRow label="Cover" value={wf.pool_cover_type} />}
          {wf.fill_method && <DetailRow label="Fill" value={wf.fill_method} />}
        </div>
      </CollapsibleSection>

      {/* Rate & Billing removed — belongs on customer billing context, not WF tile */}
    </div>
  );
}
