"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";

// --- Types ---

interface DifficultyModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  propertyId: string;
  bowDetail: Record<string, unknown> | null;
  onSaved: () => void;
}

interface DifficultyData {
  equipment_age_years: number | null;
  shade_exposure: string | null;
  tree_debris_level: string | null;
  enclosure_type: string | null;
  chemical_demand_score: number;
  access_difficulty_score: number;
  customer_demands_score: number;
  callback_frequency_score: number;
  override_composite: number | null;
  notes: string;
}

// --- Scoring logic (mirrors backend exactly) ---

const WEIGHTS: Record<string, number> = {
  pool_gallons: 0.10,
  pool_sqft: 0.05,
  water_features: 0.08,
  equipment_age: 0.07,
  shade_debris: 0.05,
  enclosure: 0.05,
  chemical_demand: 0.12,
  service_time: 0.18,
  distance: 0.10,
  access: 0.08,
  customer_demands: 0.07,
  callback: 0.05,
};

const GALLON_RANGES: [number, number][] = [[10000, 1], [20000, 2], [30000, 3], [40000, 4]];
const SQFT_RANGES: [number, number][] = [[400, 1], [700, 2], [1000, 3], [1500, 4]];
const SERVICE_TIME_RANGES: [number, number][] = [[20, 1], [30, 2], [45, 3], [60, 4]];
const EQUIPMENT_AGE_RANGES: [number, number][] = [[3, 1], [6, 2], [10, 3], [15, 4]];

function rangeScore(value: number | null | undefined, ranges: [number, number][]): number {
  if (value == null) return 1.0;
  for (const [threshold, score] of ranges) {
    if (value <= threshold) return score;
  }
  return 5.0;
}

function shadeScore(shade: string | null): number {
  return { full_sun: 1.0, partial_shade: 3.0, full_shade: 5.0 }[shade || ""] ?? 1.0;
}

function debrisScore(debris: string | null): number {
  return { none: 1.0, low: 2.0, moderate: 3.5, heavy: 5.0 }[debris || ""] ?? 1.0;
}

function enclosureScore(enclosure: string | null): number {
  return { indoor: 1.0, screened: 2.0, open: 3.5 }[enclosure || ""] ?? 3.5;
}

// --- Score color helpers ---

function scoreColor(score: number): string {
  if (score <= 2) return "text-emerald-600";
  if (score <= 3) return "text-amber-600";
  return "text-red-600";
}

function scoreBgColor(score: number): string {
  if (score <= 2) return "bg-emerald-500";
  if (score <= 3) return "bg-amber-500";
  return "bg-red-500";
}

function dotColor(dotIndex: number, activeScore: number): string {
  if (dotIndex > activeScore) return "bg-muted-foreground/20";
  if (activeScore <= 2) return "bg-emerald-500";
  if (activeScore <= 3) return "bg-amber-500";
  return "bg-red-500";
}

// --- Score dot selector ---

function ScoreDots({
  value,
  onChange,
  readonly = false,
}: {
  value: number;
  onChange?: (v: number) => void;
  readonly?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {[1, 2, 3, 4, 5].map((dot) => (
        <button
          key={dot}
          type="button"
          disabled={readonly}
          onClick={() => onChange?.(dot)}
          className={`h-3.5 w-3.5 rounded-full transition-colors ${
            dotColor(dot, Math.round(value))
          } ${readonly ? "cursor-default" : "cursor-pointer hover:ring-2 hover:ring-primary/30"}`}
          title={`${dot}`}
        />
      ))}
      <span className="text-xs text-muted-foreground ml-1 tabular-nums w-6">{value.toFixed(1)}</span>
    </div>
  );
}

// --- Score bar (read-only, for auto-calculated factors) ---

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-1.5">
      {[1, 2, 3, 4, 5].map((dot) => (
        <div
          key={dot}
          className={`h-3 w-3 rounded-full ${dotColor(dot, Math.round(score))}`}
        />
      ))}
      <span className="text-xs text-muted-foreground ml-1 tabular-nums w-6">{score.toFixed(1)}</span>
    </div>
  );
}

// --- Factor row ---

function FactorRow({
  label,
  weight,
  children,
}: {
  label: string;
  weight: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm truncate">{label}</span>
        <span className="text-[10px] text-muted-foreground/60 tabular-nums shrink-0">
          {(weight * 100).toFixed(0)}%
        </span>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

// --- Main component ---

export default function DifficultyModal({
  open,
  onOpenChange,
  propertyId,
  bowDetail,
  onSaved,
}: DifficultyModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<DifficultyData>({
    equipment_age_years: null,
    shade_exposure: null,
    tree_debris_level: null,
    enclosure_type: null,
    chemical_demand_score: 1,
    access_difficulty_score: 1,
    customer_demands_score: 1,
    callback_frequency_score: 1,
    override_composite: null,
    notes: "",
  });
  const [overrideEnabled, setOverrideEnabled] = useState(false);

  // Load existing difficulty data on open
  useEffect(() => {
    if (!open || !propertyId) return;
    setLoading(true);
    api
      .get<Record<string, unknown>>(`/v1/profitability/properties/${propertyId}/difficulty`)
      .then((data) => {
        setForm({
          equipment_age_years: (data.equipment_age_years as number) ?? null,
          shade_exposure: (data.shade_exposure as string) ?? null,
          tree_debris_level: (data.tree_debris_level as string) ?? null,
          enclosure_type: (data.enclosure_type as string) ?? null,
          chemical_demand_score: (data.chemical_demand_score as number) ?? 1,
          access_difficulty_score: (data.access_difficulty_score as number) ?? 1,
          customer_demands_score: (data.customer_demands_score as number) ?? 1,
          callback_frequency_score: (data.callback_frequency_score as number) ?? 1,
          override_composite: (data.override_composite as number) ?? null,
          notes: (data.notes as string) ?? "",
        });
        setOverrideEnabled(data.override_composite != null);
      })
      .catch(() => {
        // 404 = no difficulty record yet, use defaults
        setForm({
          equipment_age_years: null,
          shade_exposure: null,
          tree_debris_level: null,
          enclosure_type: null,
          chemical_demand_score: 1,
          access_difficulty_score: 1,
          customer_demands_score: 1,
          callback_frequency_score: 1,
          override_composite: null,
          notes: "",
        });
        setOverrideEnabled(false);
      })
      .finally(() => setLoading(false));
  }, [open, propertyId]);

  // Auto-calculated scores from bowDetail
  const autoScores = useMemo(() => {
    const gallons = (bowDetail as { pool_gallons?: number })?.pool_gallons ?? null;
    const sqft = (bowDetail as { pool_sqft?: number })?.pool_sqft ?? null;
    const minutes = (bowDetail as { estimated_service_minutes?: number })?.estimated_service_minutes ?? null;
    const waterType = (bowDetail as { water_type?: string })?.water_type;

    let waterFeatureScore = 1.0;
    if (waterType === "spa") waterFeatureScore += 1.5;
    if (waterType === "water_feature" || waterType === "fountain") waterFeatureScore += 1.0;

    return {
      pool_gallons: rangeScore(gallons, GALLON_RANGES),
      pool_sqft: rangeScore(sqft, SQFT_RANGES),
      service_time: rangeScore(minutes, SERVICE_TIME_RANGES),
      water_features: Math.min(waterFeatureScore, 5.0),
      distance: 1.0,
    };
  }, [bowDetail]);

  // Derived manager scores
  const managerScores = useMemo(() => {
    const equipAge = rangeScore(form.equipment_age_years, EQUIPMENT_AGE_RANGES);
    const shade = shadeScore(form.shade_exposure);
    const debris = debrisScore(form.tree_debris_level);
    const shadeDebris = (shade + debris) / 2.0;
    const enclosure = enclosureScore(form.enclosure_type);

    return {
      equipment_age: equipAge,
      shade_debris: shadeDebris,
      enclosure,
      chemical_demand: form.chemical_demand_score,
      access: form.access_difficulty_score,
      customer_demands: form.customer_demands_score,
      callback: form.callback_frequency_score,
    };
  }, [form]);

  // Composite score (live preview)
  const composite = useMemo(() => {
    if (overrideEnabled && form.override_composite != null) {
      return form.override_composite;
    }
    const allScores: Record<string, number> = { ...autoScores, ...managerScores };
    let total = 0;
    for (const key of Object.keys(WEIGHTS)) {
      total += (allScores[key] ?? 1.0) * WEIGHTS[key];
    }
    return Math.min(Math.max(total, 1.0), 5.0);
  }, [autoScores, managerScores, overrideEnabled, form.override_composite]);

  const updateForm = useCallback(<K extends keyof DifficultyData>(key: K, value: DifficultyData[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        equipment_age_years: form.equipment_age_years,
        shade_exposure: form.shade_exposure,
        tree_debris_level: form.tree_debris_level,
        enclosure_type: form.enclosure_type,
        chemical_demand_score: form.chemical_demand_score,
        access_difficulty_score: form.access_difficulty_score,
        customer_demands_score: form.customer_demands_score,
        callback_frequency_score: form.callback_frequency_score,
        override_composite: overrideEnabled ? form.override_composite : null,
        notes: form.notes || null,
      };
      await api.put(`/v1/profitability/properties/${propertyId}/difficulty`, body);
      toast.success("Difficulty score saved");
      onSaved();
      onOpenChange(false);
    } catch {
      toast.error("Failed to save difficulty score");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Difficulty Score</span>
            <div className="flex items-center gap-2">
              <span className={`text-3xl font-bold tabular-nums ${scoreColor(composite)}`}>
                {composite.toFixed(2)}
              </span>
              <div className={`h-3 w-3 rounded-full ${scoreBgColor(composite)}`} />
            </div>
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-5">
            {/* Auto-calculated factors */}
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">
                Auto-calculated
              </p>
              <div className="bg-muted/50 rounded-md px-3 py-1 divide-y divide-border/50">
                <FactorRow label="Pool Volume" weight={WEIGHTS.pool_gallons}>
                  <ScoreBar score={autoScores.pool_gallons} />
                </FactorRow>
                <FactorRow label="Surface Area" weight={WEIGHTS.pool_sqft}>
                  <ScoreBar score={autoScores.pool_sqft} />
                </FactorRow>
                <FactorRow label="Service Time" weight={WEIGHTS.service_time}>
                  <ScoreBar score={autoScores.service_time} />
                </FactorRow>
                <FactorRow label="Water Features" weight={WEIGHTS.water_features}>
                  <ScoreBar score={autoScores.water_features} />
                </FactorRow>
                <FactorRow label="Distance" weight={WEIGHTS.distance}>
                  <ScoreBar score={autoScores.distance} />
                </FactorRow>
              </div>
            </div>

            {/* Manager-rated factors */}
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mb-1">
                Manager-rated
              </p>
              <div className="space-y-3">
                {/* Equipment Age */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Label className="text-sm">Equipment Age</Label>
                    <span className="text-[10px] text-muted-foreground/60 tabular-nums">
                      {(WEIGHTS.equipment_age * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Input
                      type="number"
                      min={0}
                      max={50}
                      placeholder="yrs"
                      className="w-16 h-7 text-xs"
                      value={form.equipment_age_years ?? ""}
                      onChange={(e) => {
                        const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                        updateForm("equipment_age_years", v);
                      }}
                    />
                    <ScoreBar score={managerScores.equipment_age} />
                  </div>
                </div>

                {/* Shade */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Label className="text-sm">Shade</Label>
                    <span className="text-[10px] text-muted-foreground/60 tabular-nums">
                      {(WEIGHTS.shade_debris * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Select
                    value={form.shade_exposure ?? ""}
                    onValueChange={(v) => updateForm("shade_exposure", v || null)}
                  >
                    <SelectTrigger className="w-36 h-7 text-xs">
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="full_sun">Full Sun</SelectItem>
                      <SelectItem value="partial_shade">Partial Shade</SelectItem>
                      <SelectItem value="full_shade">Full Shade</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Debris */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Label className="text-sm">Debris</Label>
                  </div>
                  <Select
                    value={form.tree_debris_level ?? ""}
                    onValueChange={(v) => updateForm("tree_debris_level", v || null)}
                  >
                    <SelectTrigger className="w-36 h-7 text-xs">
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="moderate">Moderate</SelectItem>
                      <SelectItem value="heavy">Heavy</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Enclosure */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Label className="text-sm">Enclosure</Label>
                    <span className="text-[10px] text-muted-foreground/60 tabular-nums">
                      {(WEIGHTS.enclosure * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Select
                    value={form.enclosure_type ?? ""}
                    onValueChange={(v) => updateForm("enclosure_type", v || null)}
                  >
                    <SelectTrigger className="w-36 h-7 text-xs">
                      <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="indoor">Indoor</SelectItem>
                      <SelectItem value="screened">Screened</SelectItem>
                      <SelectItem value="open">Open</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Chemical Demand */}
                <FactorRow label="Chemical Demand" weight={WEIGHTS.chemical_demand}>
                  <ScoreDots
                    value={form.chemical_demand_score}
                    onChange={(v) => updateForm("chemical_demand_score", v)}
                  />
                </FactorRow>

                {/* Access Difficulty */}
                <FactorRow label="Access Difficulty" weight={WEIGHTS.access}>
                  <ScoreDots
                    value={form.access_difficulty_score}
                    onChange={(v) => updateForm("access_difficulty_score", v)}
                  />
                </FactorRow>

                {/* Customer Demands */}
                <FactorRow label="Customer Demands" weight={WEIGHTS.customer_demands}>
                  <ScoreDots
                    value={form.customer_demands_score}
                    onChange={(v) => updateForm("customer_demands_score", v)}
                  />
                </FactorRow>

                {/* Callback Frequency */}
                <FactorRow label="Callback Frequency" weight={WEIGHTS.callback}>
                  <ScoreDots
                    value={form.callback_frequency_score}
                    onChange={(v) => updateForm("callback_frequency_score", v)}
                  />
                </FactorRow>
              </div>
            </div>

            {/* Override */}
            <div className="border rounded-md px-3 py-2.5 space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-sm">Override composite score</Label>
                <Switch
                  checked={overrideEnabled}
                  onCheckedChange={(checked) => {
                    setOverrideEnabled(checked);
                    if (checked && form.override_composite == null) {
                      updateForm("override_composite", parseFloat(composite.toFixed(2)));
                    }
                    if (!checked) {
                      updateForm("override_composite", null);
                    }
                  }}
                />
              </div>
              {overrideEnabled && (
                <Input
                  type="number"
                  min={1}
                  max={5}
                  step={0.1}
                  className="w-24 h-8 text-sm"
                  value={form.override_composite ?? ""}
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : parseFloat(e.target.value);
                    updateForm("override_composite", v != null ? Math.min(5, Math.max(1, v)) : null);
                  }}
                />
              )}
            </div>

            {/* Notes */}
            <div className="space-y-1.5">
              <Label className="text-sm">Notes</Label>
              <Textarea
                className="resize-none text-sm"
                rows={2}
                placeholder="Notes about this property's difficulty..."
                value={form.notes}
                onChange={(e) => updateForm("notes", e.target.value)}
              />
            </div>

            {/* Save */}
            <div className="flex justify-end">
              <Button onClick={handleSave} disabled={saving} size="sm">
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Save
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
