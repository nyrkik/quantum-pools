"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ChevronUp, Loader2, Check, Camera, Sparkles } from "lucide-react";
import type { VisitWaterFeature, VisitReading, LastReadings } from "@/types/visit";
import { LSIGauge } from "@/components/chemistry/LSIGauge";
import { DosingCards, type DosingRecord } from "@/components/chemistry/DosingCards";

interface VisitReadingsProps {
  visitId: string;
  waterFeatures: VisitWaterFeature[];
  readings: VisitReading[];
  lastReadings: LastReadings;
  onUpdate: (readings: VisitReading[]) => void;
}

interface FieldConfig {
  key: string;
  label: string;
  step: number;
  required: boolean;
  ranges: { ideal: [number, number]; attention: [number, number]; };
}

const FIELDS: FieldConfig[] = [
  { key: "ph", label: "pH", step: 0.1, required: true, ranges: { ideal: [7.2, 7.6], attention: [7.0, 7.8] } },
  { key: "free_chlorine", label: "Free Chlorine", step: 0.5, required: true, ranges: { ideal: [1, 5], attention: [0.5, 7] } },
  { key: "total_chlorine", label: "Total Chlorine", step: 0.5, required: true, ranges: { ideal: [1, 5], attention: [0.5, 7] } },
  { key: "alkalinity", label: "Alkalinity", step: 1, required: true, ranges: { ideal: [80, 120], attention: [60, 150] } },
  { key: "calcium_hardness", label: "Calcium Hardness", step: 1, required: true, ranges: { ideal: [200, 400], attention: [150, 500] } },
  { key: "cya", label: "CYA", step: 1, required: true, ranges: { ideal: [30, 50], attention: [20, 80] } },
  { key: "phosphates", label: "Phosphates", step: 1, required: false, ranges: { ideal: [0, 100], attention: [0, 300] } },
  { key: "salt", label: "Salt", step: 100, required: false, ranges: { ideal: [2700, 3400], attention: [2500, 3600] } },
  { key: "water_temp", label: "Water Temp", step: 1, required: false, ranges: { ideal: [76, 82], attention: [70, 90] } },
];

function getRangeColor(value: number | undefined, config: FieldConfig): string {
  if (value === undefined || value === null) return "";
  const { ideal, attention } = config.ranges;
  if (value >= ideal[0] && value <= ideal[1]) return "bg-green-500";
  if (value >= attention[0] && value <= attention[1]) return "bg-yellow-500";
  return "bg-red-500";
}

type ReadingValues = Record<string, string>;

export function VisitReadings({ visitId, waterFeatures, readings, lastReadings, onUpdate }: VisitReadingsProps) {
  const [open, setOpen] = useState(true);
  const [activeWfId, setActiveWfId] = useState(waterFeatures[0]?.id || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const existingReading = useMemo(
    () => readings.find((r) => r.water_feature_id === activeWfId),
    [readings, activeWfId]
  );

  const [values, setValues] = useState<ReadingValues>(() => buildValues(existingReading));
  const [scanning, setScanning] = useState(false);
  const [aiSuggestion, setAiSuggestion] = useState<Record<string, number> | null>(null);
  const [aiBrand, setAiBrand] = useState<string | null>(null);
  const [aiConfidence, setAiConfidence] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Backend chemistry-field name ↔ FIELDS.key mapping. The frontend collapsed
  // `cyanuric_acid` to `cya`; everything else is identical.
  const BACKEND_TO_UI: Record<string, string> = { cyanuric_acid: "cya" };
  const UI_TO_BACKEND: Record<string, string> = { cya: "cyanuric_acid" };

  function buildValues(reading?: VisitReading): ReadingValues {
    const v: ReadingValues = {};
    for (const f of FIELDS) {
      const val = reading ? (reading as unknown as Record<string, unknown>)[f.key] : undefined;
      v[f.key] = val != null ? String(val) : "";
    }
    return v;
  }

  const switchWf = (wfId: string) => {
    setActiveWfId(wfId);
    const r = readings.find((r) => r.water_feature_id === wfId);
    setValues(buildValues(r));
    setAiSuggestion(null);
    setAiBrand(null);
    setAiConfidence(null);
    setSaved(false);
  };

  const lastForWf = lastReadings[activeWfId] || {};

  // ---- Phase 3d.2: live LSI + dosing recommendations ---------------------
  // As the tech enters/edits readings, hit the chemistry endpoint with a
  // 300ms debounce and show the gauge + cards below. No DB write — the
  // visit save flow remains the canonical store. Dosing engine is pure
  // determinism; this is just live preview.
  type DosingResponse = {
    dosing: DosingRecord[];
    lsi: { value: number; classification: "corrosive" | "balanced" | "scaling"; based_on: { temp_f: number } } | null;
  };
  const [chemistry, setChemistry] = useState<DosingResponse | null>(null);
  const activeWf = waterFeatures.find((wf) => wf.id === activeWfId);
  const poolGallons = activeWf?.pool_gallons ?? null;

  useEffect(() => {
    if (!activeWfId || !poolGallons || poolGallons <= 0) {
      setChemistry(null);
      return;
    }
    const numFor = (k: string) => {
      const raw = values[k];
      if (raw === undefined || raw === null || raw === "") return null;
      const n = parseFloat(raw);
      return Number.isFinite(n) ? n : null;
    };
    const body: Record<string, number | null> = {
      pool_gallons: poolGallons,
      ph: numFor("ph"),
      free_chlorine: numFor("free_chlorine"),
      combined_chlorine: numFor("combined_chlorine"),
      alkalinity: numFor("alkalinity"),
      calcium_hardness: numFor("calcium_hardness"),
      cyanuric_acid: numFor("cya"),
      phosphates: numFor("phosphates"),
    };
    // Skip the call if every reading field is empty — nothing to compute.
    const hasAny = Object.entries(body).some(
      ([k, v]) => k !== "pool_gallons" && v !== null,
    );
    if (!hasAny) {
      setChemistry(null);
      return;
    }
    const handle = setTimeout(async () => {
      try {
        const res = await api.post<DosingResponse>(
          `/v1/chemistry/water-features/${activeWfId}/dosing`,
          body,
        );
        setChemistry(res);
      } catch {
        // Non-fatal — preview just disappears, form still works.
        setChemistry(null);
      }
    }, 300);
    return () => clearTimeout(handle);
  }, [activeWfId, poolGallons, values]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const payload: Record<string, unknown> = { water_feature_id: activeWfId };
      for (const f of FIELDS) {
        const v = values[f.key];
        const backendKey = UI_TO_BACKEND[f.key] || f.key;
        payload[backendKey] = v ? parseFloat(v) : null;
      }
      const result = await api.post<VisitReading>(`/v1/visits/${visitId}/readings`, payload);
      const newReadings = readings.filter((r) => r.water_feature_id !== activeWfId);
      newReadings.push(result);
      onUpdate(newReadings);
      setSaved(true);
      toast.success("Readings saved");

      // If AI pre-populated, fire-and-forget the correction-logging endpoint
      // so the next scan in this org gets better.
      if (aiSuggestion) {
        const saved: Record<string, number> = {};
        for (const f of FIELDS) {
          const v = values[f.key];
          if (!v) continue;
          const backendKey = UI_TO_BACKEND[f.key] || f.key;
          saved[backendKey] = parseFloat(v);
        }
        api.post(`/v1/visits/${visitId}/scan-test-strip/correction`, {
          ai_suggested: aiSuggestion,
          saved,
          brand_detected: aiBrand,
          confidence: aiConfidence,
        }).catch(() => { /* fire-and-forget */ });
        setAiSuggestion(null);
        setAiBrand(null);
        setAiConfidence(null);
      }
    } catch {
      toast.error("Failed to save readings");
    } finally {
      setSaving(false);
    }
  };

  const handleScanFile = async (file: File) => {
    setScanning(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const result = await api.upload<{
        values: Record<string, number>;
        confidence: number;
        brand_detected: string | null;
        notes: string | null;
      }>(`/v1/visits/${visitId}/scan-test-strip`, fd);

      // Apply scanned values to the form, mapping backend → UI keys
      setValues((prev) => {
        const next = { ...prev };
        for (const [backendKey, val] of Object.entries(result.values)) {
          const uiKey = BACKEND_TO_UI[backendKey] || backendKey;
          if (FIELDS.some((f) => f.key === uiKey)) {
            next[uiKey] = String(val);
          }
        }
        return next;
      });
      setAiSuggestion(result.values);
      setAiBrand(result.brand_detected);
      setAiConfidence(result.confidence);
      const filledCount = Object.keys(result.values).length;
      const brandLabel = result.brand_detected ? ` (${result.brand_detected})` : "";
      toast.success(`Strip scanned${brandLabel}: ${filledCount} values filled · review and save`);
      if (result.notes) {
        toast.message(result.notes);
      }
    } catch (e) {
      toast.error("Strip scan failed — enter values manually");
      console.error("scan-test-strip error", e);
    } finally {
      setScanning(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const hasSavedReading = useMemo(
    () => waterFeatures.map((wf) => ({
      id: wf.id,
      saved: readings.some((r) => r.water_feature_id === wf.id),
    })),
    [waterFeatures, readings]
  );

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center justify-between rounded-lg bg-muted/60 px-4 py-3 text-left">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Chemical Readings</span>
            {readings.length > 0 && (
              <span className="text-xs text-muted-foreground">
                {readings.length} saved
              </span>
            )}
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="space-y-4 pt-3">
          {/* Water feature tabs */}
          {waterFeatures.length > 1 && (
            <div className="flex gap-1.5">
              {waterFeatures.map((wf) => {
                const info = hasSavedReading.find((h) => h.id === wf.id);
                return (
                  <Button
                    key={wf.id}
                    variant={activeWfId === wf.id ? "default" : "outline"}
                    size="sm"
                    onClick={() => switchWf(wf.id)}
                    className="text-xs"
                  >
                    {wf.name}
                    {info?.saved && <Check className="h-3 w-3 ml-1" />}
                  </Button>
                );
              })}
            </div>
          )}

          {/* LSI gauge + dosing cards (live, debounced; renders only
              when there's enough input to compute). */}
          {chemistry && chemistry.lsi ? (
            <div className="flex justify-center pt-1">
              <LSIGauge
                value={chemistry.lsi.value}
                classification={chemistry.lsi.classification}
                caption={`temp: ${chemistry.lsi.based_on.temp_f}°F (assumed)`}
              />
            </div>
          ) : null}
          {chemistry && chemistry.dosing.length > 0 ? (
            <DosingCards recommendations={chemistry.dosing} />
          ) : null}

          {/* Scan strip control */}
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleScanFile(f);
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={scanning}
              className="flex-1 h-10"
            >
              {scanning ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Camera className="h-4 w-4 mr-2" />
              )}
              {scanning ? "Reading strip…" : "Scan test strip"}
            </Button>
            {aiBrand && (
              <span className="text-[10px] text-muted-foreground inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3" />
                {aiBrand}
                {aiConfidence != null && ` · ${Math.round(aiConfidence * 100)}%`}
              </span>
            )}
          </div>

          {/* Input grid */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-3">
            {FIELDS.map((field) => {
              const lastVal = (lastForWf as Record<string, unknown>)[field.key];
              const placeholder = lastVal != null ? `Last: ${lastVal}` : "";
              const numVal = values[field.key] ? parseFloat(values[field.key]) : undefined;
              const dot = getRangeColor(numVal, field);

              // Trend: compare last reading to ideal range midpoint
              const lastNum = lastVal != null ? Number(lastVal) : null;
              const trendArrow = (() => {
                if (numVal == null || lastNum == null) return null;
                const diff = numVal - lastNum;
                if (Math.abs(diff) < field.step * 0.5) return "→";
                const mid = (field.ranges.ideal[0] + field.ranges.ideal[1]) / 2;
                // Is the change moving toward ideal or away?
                const wasCloser = Math.abs(lastNum - mid) > Math.abs(numVal - mid);
                if (wasCloser) return "↗";  // improving
                return "↘";  // worsening
              })();
              const trendColor = trendArrow === "↗" ? "text-green-600" : trendArrow === "↘" ? "text-red-500" : "text-muted-foreground";

              return (
                <div key={field.key} className="space-y-1">
                  <div className="flex items-center gap-1.5">
                    {dot && <span className={`h-2 w-2 rounded-full ${dot}`} />}
                    <Label className="text-xs text-muted-foreground">{field.label}</Label>
                    {trendArrow && <span className={`text-xs font-bold ${trendColor}`}>{trendArrow}</span>}
                  </div>
                  <Input
                    type="number"
                    step={field.step}
                    inputMode="decimal"
                    value={values[field.key]}
                    onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                    placeholder={placeholder}
                    className="h-10 text-sm"
                  />
                </div>
              );
            })}
          </div>

          <Button onClick={handleSave} disabled={saving} className="w-full">
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : saved ? (
              <Check className="h-4 w-4 mr-2" />
            ) : null}
            {saved ? "Saved" : "Save Readings"}
          </Button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
