"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter } from "@/components/ui/overlay";
import { toast } from "sonner";
import { Droplets, ChevronDown, Pencil, Loader2, Plus, Trash2, ChevronRight, ExternalLink } from "lucide-react";
import { api, getBackendOrigin } from "@/lib/api";
import type { Property, WaterFeatureSummary, EquipmentItem, CatalogPart } from "../customer-types";

interface WaterFeaturesTileProps {
  properties: Property[];
}

const EQUIPMENT_TYPES = [
  { value: "pump", label: "Pump" },
  { value: "filter", label: "Filter" },
  { value: "heater", label: "Heater" },
  { value: "chlorinator", label: "Chlorinator" },
  { value: "booster_pump", label: "Booster Pump" },
  { value: "jet_pump", label: "Jet Pump" },
  { value: "chemical_feeder", label: "Chemical Feeder" },
  { value: "automation", label: "Automation" },
  { value: "flow_meter", label: "Flow Meter" },
  { value: "light", label: "Light" },
  { value: "valve", label: "Valve" },
  { value: "drain_cover", label: "Drain Cover" },
  { value: "blower", label: "Blower" },
];

function typeLabel(t: string) {
  return EQUIPMENT_TYPES.find((e) => e.value === t)?.label || t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatWaterType(t: string) {
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function displayName(item: EquipmentItem) {
  return item.catalog_canonical_name || item.normalized_name || [item.brand, item.model].filter(Boolean).join(" ") || "—";
}

type WfWithMeta = WaterFeatureSummary & { propertyId: string; propertyName?: string | null };

export function WaterFeaturesTile({ properties }: WaterFeaturesTileProps) {
  const allWfs: WfWithMeta[] = properties.flatMap((p) =>
    (p.water_features || []).map((wf) => ({ ...wf, propertyId: p.id, propertyName: p.name }))
  );

  const [expandedWfId, setExpandedWfId] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [equipmentByWf, setEquipmentByWf] = useState<Record<string, EquipmentItem[]>>({});
  const [loadedWfs, setLoadedWfs] = useState<Set<string>>(new Set());

  const loadEquipment = useCallback((wfId: string) => {
    if (loadedWfs.has(wfId)) return;
    api.get<EquipmentItem[]>(`/v1/equipment/wf/${wfId}`)
      .then((data) => {
        setEquipmentByWf((prev) => ({ ...prev, [wfId]: data || [] }));
        setLoadedWfs((prev) => new Set(prev).add(wfId));
      })
      .catch(() => {});
  }, [loadedWfs]);

  const reloadAll = useCallback(() => {
    setLoadedWfs(new Set());
    setEquipmentByWf({});
    // Reload expanded WF
    if (expandedWfId) {
      api.get<EquipmentItem[]>(`/v1/equipment/wf/${expandedWfId}`)
        .then((data) => {
          setEquipmentByWf((prev) => ({ ...prev, [expandedWfId]: data || [] }));
          setLoadedWfs(new Set([expandedWfId]));
        })
        .catch(() => {});
    }
  }, [expandedWfId]);

  const handleExpand = (wfId: string) => {
    const newId = expandedWfId === wfId ? null : wfId;
    setExpandedWfId(newId);
    if (newId) loadEquipment(newId);
  };

  const handleEdit = () => {
    // Load all WF equipment before opening edit
    for (const wf of allWfs) {
      if (!loadedWfs.has(wf.id)) {
        api.get<EquipmentItem[]>(`/v1/equipment/wf/${wf.id}`)
          .then((data) => {
            setEquipmentByWf((prev) => ({ ...prev, [wf.id]: data || [] }));
            setLoadedWfs((prev) => new Set(prev).add(wf.id));
          })
          .catch(() => {});
      }
    }
    setEditOpen(true);
  };

  const getSiblings = (wfId: string, propertyId: string) =>
    allWfs.filter((w) => w.propertyId === propertyId && w.id !== wfId);

  if (allWfs.length === 0) return null;

  return (
    <>
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm font-semibold">
            <span className="flex items-center gap-2">
              <Droplets className="h-4 w-4 text-blue-500" />
              Water Features
            </span>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleEdit}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {allWfs.map((wf) => (
            <WfSection
              key={wf.id}
              wf={wf}
              expanded={expandedWfId === wf.id}
              onToggle={() => handleExpand(wf.id)}
              showPropertyName={properties.length > 1 && !!wf.propertyName}
              equipment={equipmentByWf[wf.id] || []}
              equipLoaded={loadedWfs.has(wf.id)}
            />
          ))}
        </CardContent>
      </Card>

      <AllWfEquipmentSheet
        wfs={allWfs}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        equipmentByWf={equipmentByWf}
        initialWfId={expandedWfId || allWfs[0]?.id}
        onSaved={reloadAll}
      />
    </>
  );
}

function WfSection({
  wf,
  expanded,
  onToggle,
  showPropertyName,
  equipment,
  equipLoaded,
}: {
  wf: WfWithMeta;
  expanded: boolean;
  onToggle: () => void;
  showPropertyName: boolean;
  equipment: EquipmentItem[];
  equipLoaded: boolean;
}) {
  const [detailItem, setDetailItem] = useState<EquipmentItem | null>(null);

  // Group equipment by system_group
  const grouped = equipment.reduce<Record<string, EquipmentItem[]>>((acc, item) => {
    const key = item.system_group || "__ungrouped__";
    (acc[key] = acc[key] || []).push(item);
    return acc;
  }, {});

  const systemGroups = Object.keys(grouped).filter((k) => k !== "__ungrouped__").sort();
  const ungrouped = grouped["__ungrouped__"] || [];

  return (
    <div className="border-b last:border-b-0">
      <div
        className="flex items-center justify-between py-2.5 cursor-pointer hover:bg-muted/50 -mx-2 px-2 rounded transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium truncate">{wf.name || formatWaterType(wf.water_type)}</span>
          {wf.pool_gallons && (
            <span className="text-xs text-muted-foreground shrink-0">{wf.pool_gallons.toLocaleString()} gal</span>
          )}
          {wf.sanitizer_type && (
            <Badge variant="outline" className="text-[10px] px-1.5 shrink-0">{wf.sanitizer_type}</Badge>
          )}
        </div>
        <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform shrink-0 ${expanded ? "rotate-180" : ""}`} />
      </div>

      {showPropertyName && (
        <p className="text-[10px] text-muted-foreground -mt-1.5 mb-1 ml-0.5">{wf.propertyName}</p>
      )}

      {expanded && (
        <div className="pb-3 space-y-2.5 ml-1">
          {/* Equipment */}
          <div className="space-y-1">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Equipment</p>

            {!equipLoaded ? (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            ) : equipment.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No equipment recorded</p>
            ) : (
              <>
                {ungrouped.map((item) => (
                  <EquipmentRow key={item.id} item={item} onClick={() => setDetailItem(item)} />
                ))}
                {systemGroups.map((group) => (
                  <div key={group} className="space-y-0.5">
                    <p className="text-[10px] text-muted-foreground font-medium mt-1">{group}</p>
                    <div className="border-l-2 border-muted pl-2 space-y-0.5">
                      {grouped[group].map((item) => (
                        <EquipmentRow key={item.id} item={item} onClick={() => setDetailItem(item)} />
                      ))}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>

          {/* Specs */}
          {(wf.pool_length_ft || wf.pool_shape || wf.pool_surface || wf.pool_sqft) && (
            <div className="space-y-1">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Specs</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                {wf.pool_shape && (<><span className="text-muted-foreground">Shape</span><span className="font-medium capitalize">{wf.pool_shape}</span></>)}
                {wf.pool_length_ft && wf.pool_width_ft && (<><span className="text-muted-foreground">Size</span><span className="font-medium">{wf.pool_length_ft} x {wf.pool_width_ft} ft</span></>)}
                {wf.pool_depth_shallow && wf.pool_depth_deep && (<><span className="text-muted-foreground">Depth</span><span className="font-medium">{wf.pool_depth_shallow}–{wf.pool_depth_deep} ft</span></>)}
                {wf.pool_surface && (<><span className="text-muted-foreground">Surface</span><span className="font-medium capitalize">{wf.pool_surface}</span></>)}
                {wf.pool_sqft && (<><span className="text-muted-foreground">Area</span><span className="font-medium">{wf.pool_sqft.toLocaleString()} sqft</span></>)}
              </div>
            </div>
          )}
        </div>
      )}

      <EquipmentDetailOverlay
        item={detailItem}
        open={!!detailItem}
        onClose={() => setDetailItem(null)}
      />
    </div>
  );
}

function EquipmentRow({ item, onClick }: { item: EquipmentItem; onClick: () => void }) {
  const name = displayName(item);
  return (
    <div
      className="flex items-center justify-between text-xs py-1 -mx-1 px-1 rounded cursor-pointer hover:bg-muted/50 transition-colors"
      onClick={(e) => { e.stopPropagation(); onClick(); }}
    >
      <span className="text-muted-foreground">{typeLabel(item.equipment_type)}</span>
      <div className="flex items-center gap-1">
        <span className="font-medium">{name}</span>
        <ChevronRight className="h-3 w-3 text-muted-foreground" />
      </div>
    </div>
  );
}

// --- Equipment Detail Overlay ---

interface CatalogData {
  manufacturer?: string | null;
  model_number?: string | null;
  category?: string | null;
  image_url?: string | null;
  specs?: Record<string, unknown> | null;
}

function EquipmentDetailOverlay({ item, open, onClose }: { item: EquipmentItem | null; open: boolean; onClose: () => void }) {
  const [parts, setParts] = useState<CatalogPart[]>([]);
  const [catalogData, setCatalogData] = useState<CatalogData | null>(null);
  const [partsLoading, setPartsLoading] = useState(false);
  const backendOrigin = getBackendOrigin();

  useEffect(() => {
    if (!open || !item) return;
    setPartsLoading(true);
    setCatalogData(null);

    if (item.catalog_equipment_id) {
      // Fetch from catalog — includes linked parts
      api.get<{ parts?: CatalogPart[]; manufacturer?: string; model_number?: string; category?: string; image_url?: string; specs?: Record<string, unknown> }>(
        `/v1/equipment-catalog/${item.catalog_equipment_id}`
      )
        .then((d) => {
          setParts(d.parts || []);
          setCatalogData({ manufacturer: d.manufacturer, model_number: d.model_number, category: d.category, image_url: d.image_url, specs: d.specs });
        })
        .catch(() => setParts([]))
        .finally(() => setPartsLoading(false));
    } else {
      // Fallback: text search
      const name = displayName(item);
      if (name === "—") { setPartsLoading(false); return; }
      const searchQuery = [item.brand, item.model].filter(Boolean).join(" ").trim() || name;
      api.get<CatalogPart[]>(`/v1/parts/search?q=${encodeURIComponent(searchQuery)}&limit=10`)
        .then((d) => setParts(Array.isArray(d) ? d : []))
        .catch(() => setParts([]))
        .finally(() => setPartsLoading(false));
    }
  }, [open, item]);

  if (!item) return null;

  const name = displayName(item);
  const details = [
    { label: "Type", value: typeLabel(item.equipment_type) },
    { label: "Manufacturer", value: catalogData?.manufacturer || item.brand },
    { label: "Model #", value: catalogData?.model_number || item.model },
    { label: "Category", value: catalogData?.category },
    { label: "Part #", value: item.part_number },
    { label: "Serial #", value: item.serial_number },
    { label: "HP", value: item.horsepower?.toString() || (catalogData?.specs as Record<string, unknown>)?.hp?.toString() },
    { label: "System", value: item.system_group },
    { label: "Notes", value: item.notes },
  ].filter((d) => d.value);

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <OverlayContent className="max-w-md">
        <OverlayHeader>
          <OverlayTitle>{name}</OverlayTitle>
        </OverlayHeader>
        <OverlayBody className="space-y-4">
          {/* Equipment image + details */}
          {catalogData?.image_url && (
            <div className="flex justify-center">
              <img
                src={`${backendOrigin}${catalogData.image_url}`}
                alt={name}
                className="h-32 w-32 object-contain rounded-md bg-muted/30"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            {details.map((d) => (
              <div key={d.label} className="contents">
                <span className="text-muted-foreground text-xs">{d.label}</span>
                <span className="font-medium text-xs">{d.value}</span>
              </div>
            ))}
          </div>

          {/* Compatible parts */}
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Compatible Parts</p>
            {partsLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : parts.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No parts found in catalog</p>
            ) : (
              <div className="space-y-1.5">
                {parts.map((p) => (
                  <div key={p.id} className="flex items-start justify-between text-xs border rounded-md p-2 bg-muted/30">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{p.name}</p>
                      <div className="flex items-center gap-2 text-muted-foreground mt-0.5">
                        {p.brand && <span>{p.brand}</span>}
                        {p.sku && <span>SKU: {p.sku}</span>}
                      </div>
                      {p.category && (
                        <Badge variant="secondary" className="text-[9px] px-1 mt-1">{p.category}</Badge>
                      )}
                    </div>
                    {p.product_url && (
                      <a
                        href={p.product_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground hover:text-primary shrink-0 ml-2"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </OverlayBody>
      </OverlayContent>
    </Overlay>
  );
}

// --- Equipment Edit Sheet ---

// Types that get grouped into filter systems when multiples exist
const SYSTEM_TYPES = new Set(["pump", "filter", "chlorinator"]);

interface EditRow {
  id?: string;
  equipment_type: string;
  brand: string;
  model: string;
  system_group: string;
  notes: string;
  _deleted?: boolean;
}

function needsSystemGroups(rows: EditRow[]) {
  const active = rows.filter((r) => !r._deleted);
  // Check if any system-groupable type has more than one item
  for (const t of SYSTEM_TYPES) {
    if (active.filter((r) => r.equipment_type === t).length > 1) return true;
  }
  return false;
}

function autoAssignGroups(rows: EditRow[]): EditRow[] {
  const showGroups = needsSystemGroups(rows);
  if (!showGroups) {
    // Clear all system groups — simple setup
    return rows.map((r) => ({ ...r, system_group: "" }));
  }

  // Find how many systems we need (max count of any single system type)
  const active = rows.filter((r) => !r._deleted && SYSTEM_TYPES.has(r.equipment_type));
  const typeCounts: Record<string, number> = {};
  for (const r of active) {
    typeCounts[r.equipment_type] = (typeCounts[r.equipment_type] || 0) + 1;
  }
  const numSystems = Math.max(...Object.values(typeCounts), 1);

  // Auto-assign: items of system types without a group get assigned in order
  let systemIdx = 0;
  const typeCounters: Record<string, number> = {};
  return rows.map((r) => {
    if (r._deleted) return r;
    if (!SYSTEM_TYPES.has(r.equipment_type)) {
      // Non-system types never get grouped
      return { ...r, system_group: "" };
    }
    // If already has a valid group, keep it
    if (r.system_group && r.system_group.startsWith("System ")) return r;
    // Auto-assign
    typeCounters[r.equipment_type] = (typeCounters[r.equipment_type] || 0) + 1;
    return { ...r, system_group: `System ${typeCounters[r.equipment_type]}` };
  });
}

function AllWfEquipmentSheet({
  wfs,
  open,
  onClose,
  equipmentByWf,
  initialWfId,
  onSaved,
}: {
  wfs: WfWithMeta[];
  open: boolean;
  onClose: () => void;
  equipmentByWf: Record<string, EquipmentItem[]>;
  initialWfId: string;
  onSaved: () => void;
}) {
  const [activeWfId, setActiveWfId] = useState(initialWfId);
  const [rowsByWf, setRowsByWf] = useState<Record<string, EditRow[]>>({});
  const [originalByWf, setOriginalByWf] = useState<Record<string, EditRow[]>>({});
  const [saving, setSaving] = useState(false);
  const [copying, setCopying] = useState(false);

  useEffect(() => {
    if (open) {
      setActiveWfId(initialWfId);
      const initial: Record<string, EditRow[]> = {};
      for (const wf of wfs) {
        initial[wf.id] = (equipmentByWf[wf.id] || []).map((e) => ({
          id: e.id,
          equipment_type: e.equipment_type,
          brand: e.brand || "",
          model: e.model || "",
          system_group: e.system_group || "",
          notes: e.notes || "",
        }));
      }
      setRowsByWf(initial);
      setOriginalByWf(JSON.parse(JSON.stringify(initial)));
    }
  }, [open, equipmentByWf, wfs, initialWfId]);

  // Dirty state detection
  const isWfDirty = (wfId: string) => {
    return JSON.stringify(rowsByWf[wfId] || []) !== JSON.stringify(originalByWf[wfId] || []);
  };
  const isDirty = wfs.some((wf) => isWfDirty(wf.id));

  const rows = rowsByWf[activeWfId] || [];
  const setRows = (fn: (prev: EditRow[]) => EditRow[]) => {
    setRowsByWf((prev) => ({ ...prev, [activeWfId]: fn(prev[activeWfId] || []) }));
  };

  const showGroups = needsSystemGroups(rows);

  const addRow = () => {
    setRows((prev) => autoAssignGroups([...prev, { equipment_type: "pump", brand: "", model: "", system_group: "", notes: "" }]));
  };

  const updateRow = (idx: number, field: keyof EditRow, value: string) => {
    setRows((prev) => {
      const next = prev.map((row, i) => (i === idx ? { ...row, [field]: value } : row));
      return field === "equipment_type" ? autoAssignGroups(next) : next;
    });
  };

  const deleteRow = (idx: number) => {
    setRows((prev) => autoAssignGroups(prev.map((row, i) => (i === idx ? { ...row, _deleted: true } : row))));
  };

  const handleCopyFrom = async (sourceWfId: string) => {
    setCopying(true);
    try {
      await api.post(`/v1/equipment/wf/${activeWfId}/copy-from/${sourceWfId}`);
      toast.success("Equipment copied");
      onSaved();
      onClose();
    } catch {
      toast.error("Failed to copy");
    } finally {
      setCopying(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save all WFs that have changes
      for (const wf of wfs) {
        const wfRows = rowsByWf[wf.id] || [];
        const active = wfRows.filter((r) => !r._deleted);
        const deleted = wfRows.filter((r) => r._deleted && r.id);

        for (const r of deleted) {
          await api.delete(`/v1/equipment/${r.id}`);
        }

        for (const r of active) {
          const body = {
            equipment_type: r.equipment_type,
            brand: r.brand || null,
            model: r.model || null,
            system_group: r.system_group || null,
            notes: r.notes || null,
          };
          if (r.id) {
            await api.put(`/v1/equipment/${r.id}`, body);
          } else {
            await api.post(`/v1/equipment/wf/${wf.id}`, body);
          }
        }
      }

      toast.success("Equipment saved");
      onSaved();
      onClose();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const activeWf = wfs.find((w) => w.id === activeWfId);
  const siblings = wfs.filter((w) => w.id !== activeWfId);
  const siblingsWithEquip = siblings.filter((s) =>
    (rowsByWf[s.id] || []).filter((r) => !r._deleted).length > 0
  );
  const visibleRows = rows.filter((r) => !r._deleted);
  const systemGroups = [...new Set(visibleRows.map((r) => r.system_group).filter((g) => g.startsWith("System ")))].sort();
  const nextSystem = `System ${systemGroups.length + 1}`;

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <OverlayContent className="max-w-xl">
        <OverlayHeader>
          <OverlayTitle>Equipment</OverlayTitle>

          {/* WF tabs */}
          {wfs.length > 1 && (
            <div className="flex gap-1 mt-2">
              {wfs.map((wf) => (
                <button
                  key={wf.id}
                  onClick={() => setActiveWfId(wf.id)}
                  className={`px-3 py-1 text-xs rounded-full transition-colors relative ${
                    activeWfId === wf.id
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {wf.name || formatWaterType(wf.water_type)}
                  {isWfDirty(wf.id) && (
                    <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-amber-500" />
                  )}
                </button>
              ))}
            </div>
          )}
        </OverlayHeader>

        <OverlayBody className="space-y-3">
          {/* Copy from sibling */}
          {siblingsWithEquip.length > 0 && (
            <div className="space-y-1.5">
              {siblingsWithEquip.map((s) => (
                <Button
                  key={s.id}
                  variant="outline"
                  size="sm"
                  className="text-xs w-full justify-start gap-2"
                  onClick={() => handleCopyFrom(s.id)}
                  disabled={copying}
                >
                  Same as {s.name || formatWaterType(s.water_type)}
                </Button>
              ))}
            </div>
          )}

          {/* Equipment rows for active WF */}
          {visibleRows.map((row) => {
            const realIdx = rows.indexOf(row);
            const isSystemType = SYSTEM_TYPES.has(row.equipment_type);
            return (
              <div key={realIdx} className="border rounded-md p-3 space-y-2 relative">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 absolute top-2 right-2 text-destructive"
                  onClick={() => deleteRow(realIdx)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>

                <div className={showGroups && isSystemType ? "grid grid-cols-2 gap-2" : ""}>
                  <div className="space-y-1">
                    <Label className="text-xs">Type</Label>
                    <Select value={row.equipment_type} onValueChange={(v) => updateRow(realIdx, "equipment_type", v)}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {EQUIPMENT_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {showGroups && isSystemType && (
                    <div className="space-y-1">
                      <Label className="text-xs">System</Label>
                      <Select value={row.system_group} onValueChange={(v) => updateRow(realIdx, "system_group", v)}>
                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {systemGroups.map((g) => (
                            <SelectItem key={g} value={g}>{g}</SelectItem>
                          ))}
                          <SelectItem value={nextSystem}>{nextSystem} (new)</SelectItem>
                          <SelectItem value="">Standalone</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Brand</Label>
                    <Input
                      value={row.brand}
                      onChange={(e) => updateRow(realIdx, "brand", e.target.value)}
                      placeholder="e.g. Pentair"
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Model</Label>
                    <Input
                      value={row.model}
                      onChange={(e) => updateRow(realIdx, "model", e.target.value)}
                      placeholder="e.g. IntelliFlo VSF"
                      className="h-8 text-xs"
                    />
                  </div>
                </div>
              </div>
            );
          })}

          <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={addRow}>
            <Plus className="h-3.5 w-3.5" />
            Add Equipment
          </Button>
        </OverlayBody>
        <OverlayFooter>
          <Button onClick={handleSave} disabled={saving || !isDirty} className="flex-1">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : isDirty ? "Save Changes" : "No Changes"}
          </Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
        </OverlayFooter>
      </OverlayContent>
    </Overlay>
  );
}
