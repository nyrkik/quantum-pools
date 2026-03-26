"use client";

import { useState, useMemo } from "react";
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
import { ChevronDown, ChevronUp, Loader2, Check } from "lucide-react";
import type { VisitWaterFeature, VisitReading, LastReadings } from "@/types/visit";

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
    setSaved(false);
  };

  const lastForWf = lastReadings[activeWfId] || {};

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const payload: Record<string, unknown> = { water_feature_id: activeWfId };
      for (const f of FIELDS) {
        const v = values[f.key];
        payload[f.key] = v ? parseFloat(v) : null;
      }
      const result = await api.post<VisitReading>(`/v1/visits/${visitId}/readings`, payload);
      const newReadings = readings.filter((r) => r.water_feature_id !== activeWfId);
      newReadings.push(result);
      onUpdate(newReadings);
      setSaved(true);
      toast.success("Readings saved");
    } catch {
      toast.error("Failed to save readings");
    } finally {
      setSaving(false);
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

          {/* Input grid */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-3">
            {FIELDS.map((field) => {
              const lastVal = (lastForWf as Record<string, unknown>)[field.key];
              const placeholder = lastVal != null ? `Last: ${lastVal}` : "";
              const numVal = values[field.key] ? parseFloat(values[field.key]) : undefined;
              const dot = getRangeColor(numVal, field);

              return (
                <div key={field.key} className="space-y-1">
                  <div className="flex items-center gap-1.5">
                    {dot && <span className={`h-2 w-2 rounded-full ${dot}`} />}
                    <Label className="text-xs text-muted-foreground">{field.label}</Label>
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
