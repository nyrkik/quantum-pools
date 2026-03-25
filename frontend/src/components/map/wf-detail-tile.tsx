"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Loader2,
  Droplets,
  MapPin,
  Clock,
  Ruler,
  Wrench,
  Gauge,
  FlaskConical,
  Thermometer,
  Zap,
  Calendar,
  Shield,
  Pipette,
  CircleDot,
  ExternalLink,
  AlertTriangle,
  Pencil,
  X,
  Waves,
  WavesLadder,
} from "lucide-react";
import type { SatelliteAnalysis, PoolBowWithCoords } from "@/types/satellite";
import {
  SOURCE_LABELS,
  SOURCE_COLORS,
  POOL_SHAPES,
  ALLOC_LABELS,
  type DimensionComparison,
} from "./map-types";

function waterTypeIcon(type: string, className: string) {
  switch (type) {
    case "spa": case "hot_tub": return <Droplets className={className} />;
    case "fountain": case "water_feature": case "wading_pool": return <Waves className={className} />;
    default: return <WavesLadder className={className} />;
  }
}

interface WfDetailTileProps {
  wf: PoolBowWithCoords;
  bowDetail: Record<string, unknown> | null;
  dimComparison: DimensionComparison | null;
  analysis: SatelliteAnalysis | null;
  activeBowId: string | null;
  highlightedBowId: string | null;
  canEdit: boolean;
  pinDirty: boolean;
  savingPin: boolean;
  savingPerimeter: boolean;
  measuringPerimeterBow: string | null;
  rateAllocation: Record<string, { allocated_rate: number; allocation_method: string; weight: number }>;
  profitData: Record<string, unknown> | null;
  dismissedDiscrepancies: Set<string>;
  // Measurement input maps
  perimeterInputs: Map<string, string>;
  areaInputs: Map<string, string>;
  volumeInputs: Map<string, string>;
  perimeterShapes: Map<string, string>;
  roundedCornersInputs: Map<string, boolean>;
  stepEntryInputs: Map<string, number>;
  benchShelfInputs: Map<string, boolean>;
  shallowDepthInputs: Map<string, string>;
  deepDepthInputs: Map<string, string>;
  perms: { canViewRates: boolean; canViewDimensions: boolean };
  // Callbacks
  onHighlightBow: (bowId: string) => void;
  onSavePin: () => void;
  onSetMeasuringBow: (bowId: string | null) => void;
  onSetPerimeterInput: (bowId: string, value: string) => void;
  onSetAreaInput: (bowId: string, value: string) => void;
  onSetVolumeInput: (bowId: string, value: string) => void;
  onSetPerimeterShape: (bowId: string, value: string) => void;
  onSetRoundedCorners: (bowId: string, value: boolean) => void;
  onSetStepEntry: (bowId: string, value: number) => void;
  onSetBenchShelf: (bowId: string, value: boolean) => void;
  onSetShallowDepth: (bowId: string, value: string) => void;
  onSetDeepDepth: (bowId: string, value: string) => void;
  onSaveMeasurements: (bowId: string) => void;
  onDismissDiscrepancy: (bowId: string) => void;
}

export default function WfDetailTile({
  wf,
  bowDetail,
  dimComparison,
  analysis,
  activeBowId,
  highlightedBowId,
  canEdit,
  pinDirty,
  savingPin,
  savingPerimeter,
  measuringPerimeterBow,
  rateAllocation,
  profitData,
  dismissedDiscrepancies,
  perimeterInputs,
  areaInputs,
  volumeInputs,
  perimeterShapes,
  roundedCornersInputs,
  stepEntryInputs,
  benchShelfInputs,
  shallowDepthInputs,
  deepDepthInputs,
  perms,
  onHighlightBow,
  onSavePin,
  onSetMeasuringBow,
  onSetPerimeterInput,
  onSetAreaInput,
  onSetVolumeInput,
  onSetPerimeterShape,
  onSetRoundedCorners,
  onSetStepEntry,
  onSetBenchShelf,
  onSetShallowDepth,
  onSetDeepDepth,
  onSaveMeasurements,
  onDismissDiscrepancy,
}: WfDetailTileProps) {
  const isBowActive = activeBowId === wf.id;
  const perimeterInput = perimeterInputs.get(wf.id) || "";
  const perimeterShape = perimeterShapes.get(wf.id) || "rectangle";
  const isMeasuring = measuringPerimeterBow === wf.id;

  const renderSourceBadge = (source: string | null | undefined) => {
    if (!source) return null;
    const label = SOURCE_LABELS[source] || source;
    const colorClass = SOURCE_COLORS[source] || "bg-gray-100 text-gray-600";
    return (
      <Badge className={`${colorClass} text-[9px] px-1 py-0 leading-tight font-medium hover:${colorClass.split(" ")[0]}`}>
        {label}
      </Badge>
    );
  };

  return (
    <Card id={`wf-tile-${wf.id}`} className={`shadow-sm border-l-4 cursor-pointer ${isBowActive ? "border-l-primary" : highlightedBowId === wf.id ? "border-l-amber-400" : "border-l-blue-500"}`} onClick={() => onHighlightBow(wf.id)}>
      <CardContent className="p-4 space-y-3">
        {/* Pool header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-baseline gap-3">
              <div className="flex items-center gap-2">
                {waterTypeIcon(wf.water_type, "h-3.5 w-3.5 text-blue-500")}
                <span className="text-base font-semibold">{wf.wf_name || wf.water_type.replace("_", " ")}</span>
              </div>
              <span className="text-muted-foreground/30">&middot;</span>
              {bowDetail && (
                <span className="text-base font-bold">{(bowDetail as { estimated_service_minutes: number }).estimated_service_minutes}<span className="text-[10px] font-normal text-muted-foreground ml-0.5">min</span></span>
              )}
              {perms.canViewRates && (() => {
                const alloc = rateAllocation[wf.id];
                const bowRate = (bowDetail as { monthly_rate?: number })?.monthly_rate;
                const rate = bowRate || alloc?.allocated_rate || null;
                const margin = profitData ? (profitData as { cost_breakdown: { margin_pct: number } }).cost_breakdown?.margin_pct : null;
                return (<>
                  <span className="text-muted-foreground/30">&middot;</span>
                  <span className={`text-base font-bold ${
                    rate
                      ? margin !== null
                        ? margin >= 30 ? "text-emerald-600" : margin >= 0 ? "text-amber-600" : "text-red-600"
                        : "text-foreground"
                      : "text-muted-foreground/40"
                  }`}>
                    {rate ? `$${rate.toFixed(0)}` : "$\u2014"}<span className="text-[10px] font-normal text-muted-foreground ml-0.5">/mo</span>
                  </span>
                  {alloc && alloc.allocation_method !== "sole" && (
                    <span className="text-[9px] text-muted-foreground/50" title={`Allocated by ${alloc.allocation_method} (${(alloc.weight * 100).toFixed(0)}%)`}>
                      ({ALLOC_LABELS[alloc.allocation_method] || alloc.allocation_method})
                    </span>
                  )}
                </>);
              })()}
            </div>
          </div>
        </div>

        {/* Pin dirty banner */}
        {isBowActive && canEdit && pinDirty && (
          <div className="rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-700 px-3 py-2 flex items-center justify-between">
            <span className="text-xs text-amber-700 dark:text-amber-400 font-medium">Pin moved — save to keep new location</span>
            <Button size="sm" className="h-7 px-3 text-xs" disabled={savingPin} onClick={onSavePin}>
              {savingPin ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Pin"}
            </Button>
          </div>
        )}

        {/* Discrepancy alert */}
        {dimComparison && dimComparison.discrepancy_level && dimComparison.discrepancy_level !== "ok" && !dismissedDiscrepancies.has(wf.id) && (() => {
          const e1 = dimComparison.estimates[0];
          const e2 = dimComparison.estimates[1];
          const desc = e1 && e2
            ? `${e1.estimated_sqft?.toLocaleString() ?? "?"} ft\u00B2 (${SOURCE_LABELS[e1.source] || e1.source}) vs ${e2.estimated_sqft?.toLocaleString() ?? "?"} ft\u00B2 (${SOURCE_LABELS[e2.source] || e2.source})`
            : "estimates";
          const isAlert = dimComparison.discrepancy_level === "alert";
          return (
            <div className={`rounded-md p-2.5 flex items-start gap-2 ${
              isAlert
                ? "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800"
                : "bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800"
            }`}>
              <AlertTriangle className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${isAlert ? "text-red-600" : "text-amber-600"}`} />
              <div className="flex-1 text-[11px]">
                <span className={`font-medium ${isAlert ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"}`}>
                  {dimComparison.discrepancy_pct?.toFixed(0)}% discrepancy — {desc}
                </span>
              </div>
              <button
                onClick={() => onDismissDiscrepancy(wf.id)}
                className={`shrink-0 ${isAlert ? "text-red-400 hover:text-red-600" : "text-amber-400 hover:text-amber-600"}`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          );
        })()}

        {/* Measurements + Equipment */}
        {bowDetail && perms.canViewDimensions && (
          <div className="grid grid-cols-2 gap-2">
            {/* Measurements */}
            <div className={`bg-muted/50 rounded-md overflow-hidden ${isMeasuring ? "border-l-3 border-l-primary" : ""}`}>
              <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                <Ruler className="h-3 w-3 text-muted-foreground" />
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Measurements</span>
                {canEdit && (
                  <button
                    className={`ml-auto transition-colors ${isMeasuring ? "text-primary" : "text-muted-foreground/40 hover:text-muted-foreground"}`}
                    onClick={() => onSetMeasuringBow(isMeasuring ? null : wf.id)}
                    title={isMeasuring ? "Close edit" : "Edit measurements"}
                  >
                    {isMeasuring ? <X className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                  </button>
                )}
              </div>
              <div className="px-2.5 py-2 space-y-1">
                {/* Area + source */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Area</span>
                  <div className="flex items-center gap-1.5">
                    {isMeasuring ? (
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          placeholder="ft\u00B2"
                          value={areaInputs.get(wf.id) ?? ((bowDetail as { pool_sqft?: number }).pool_sqft?.toString() || "")}
                          onChange={(e) => onSetAreaInput(wf.id, e.target.value)}
                          className="h-6 w-20 text-[11px] px-1.5"
                          min={0}
                          step={1}
                        />
                        <span className="text-muted-foreground">ft&sup2;</span>
                      </div>
                    ) : (
                      <>
                        {(bowDetail as { pool_sqft?: number }).pool_sqft
                          ? <span className="font-semibold">{((bowDetail as { pool_sqft: number }).pool_sqft).toLocaleString()} ft&sup2;</span>
                          : <span className="text-muted-foreground/50 italic">&mdash;</span>}
                        {renderSourceBadge((bowDetail as { dimension_source?: string }).dimension_source)}
                      </>
                    )}
                  </div>
                </div>
                {/* Volume */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Volume</span>
                  {isMeasuring ? (
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        placeholder="gal"
                        value={volumeInputs.get(wf.id) ?? ((bowDetail as { pool_gallons?: number }).pool_gallons?.toString() || "")}
                        onChange={(e) => onSetVolumeInput(wf.id, e.target.value)}
                        className="h-6 w-20 text-[11px] px-1.5"
                        min={0}
                        step={100}
                      />
                      <span className="text-muted-foreground">gal</span>
                    </div>
                  ) : (
                    (bowDetail as { pool_gallons?: number }).pool_gallons
                      ? <span className="font-medium">{((bowDetail as { pool_gallons: number }).pool_gallons).toLocaleString()} gal</span>
                      : <span className="text-muted-foreground/50 italic">&mdash;</span>
                  )}
                </div>
                {/* Perimeter */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Perimeter</span>
                  {isMeasuring ? (
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        placeholder="ft"
                        value={perimeterInput || ((bowDetail as { perimeter_ft?: number }).perimeter_ft?.toString() || "")}
                        onChange={(e) => onSetPerimeterInput(wf.id, e.target.value)}
                        className="h-6 w-20 text-[11px] px-1.5"
                        min={0}
                        step={0.1}
                      />
                      <span className="text-muted-foreground">ft</span>
                    </div>
                  ) : (
                    (bowDetail as { perimeter_ft?: number }).perimeter_ft
                      ? <span className="font-medium">{(bowDetail as { perimeter_ft: number }).perimeter_ft} ft</span>
                      : <span className="text-muted-foreground/50 italic">&mdash;</span>
                  )}
                </div>
                {/* Shape & Structure */}
                <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70 pt-1.5 mt-1.5 border-t border-border/50">Shape & Structure</p>
                {/* Shape */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Shape</span>
                  {isMeasuring ? (
                    <select
                      value={perimeterShape}
                      onChange={(e) => onSetPerimeterShape(wf.id, e.target.value)}
                      className="h-6 text-[11px] rounded border border-input bg-background px-1.5"
                    >
                      {POOL_SHAPES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  ) : (
                    (bowDetail as { pool_shape?: string }).pool_shape
                      ? <span className="font-medium capitalize">{(bowDetail as { pool_shape: string }).pool_shape.replace(/_/g, " ")}</span>
                      : <span className="text-muted-foreground/50 italic">&mdash;</span>
                  )}
                </div>
                {/* Rounded corners — only for rectangle/irregular_rectangle */}
                {(perimeterShape === "rectangle" || perimeterShape === "irregular_rectangle") && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Rounded corners</span>
                    {isMeasuring ? (
                      <input
                        type="checkbox"
                        checked={roundedCornersInputs.get(wf.id) ?? (bowDetail as { has_rounded_corners?: boolean }).has_rounded_corners ?? false}
                        onChange={(e) => onSetRoundedCorners(wf.id, e.target.checked)}
                        className="h-3.5 w-3.5 accent-primary"
                      />
                    ) : (
                      <span className="font-medium">{(bowDetail as { has_rounded_corners?: boolean }).has_rounded_corners ? "Yes" : "No"}</span>
                    )}
                  </div>
                )}
                {/* Step entries */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Step entries</span>
                  {isMeasuring ? (
                    <Input
                      type="number"
                      placeholder="0"
                      value={stepEntryInputs.get(wf.id) ?? (bowDetail as { step_entry_count?: number }).step_entry_count ?? 0}
                      onChange={(e) => onSetStepEntry(wf.id, parseInt(e.target.value) || 0)}
                      className="h-6 w-14 text-[11px] px-1.5"
                      min={0}
                      max={4}
                      step={1}
                    />
                  ) : (
                    <span className="font-medium">{(bowDetail as { step_entry_count?: number }).step_entry_count || 0}</span>
                  )}
                </div>
                {/* Bench/sun shelf */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Bench/sun shelf</span>
                  {isMeasuring ? (
                    <input
                      type="checkbox"
                      checked={benchShelfInputs.get(wf.id) ?? (bowDetail as { has_bench_shelf?: boolean }).has_bench_shelf ?? false}
                      onChange={(e) => onSetBenchShelf(wf.id, e.target.checked)}
                      className="h-3.5 w-3.5 accent-primary"
                    />
                  ) : (
                    <span className="font-medium">{(bowDetail as { has_bench_shelf?: boolean }).has_bench_shelf ? "Yes" : "No"}</span>
                  )}
                </div>
                {/* Shallow depth */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Shallow depth</span>
                  {isMeasuring ? (
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        placeholder="ft"
                        value={shallowDepthInputs.get(wf.id) ?? ((bowDetail as { pool_depth_shallow?: number }).pool_depth_shallow?.toString() || "")}
                        onChange={(e) => onSetShallowDepth(wf.id, e.target.value)}
                        className="h-6 w-16 text-[11px] px-1.5"
                        min={0}
                        max={12}
                        step={0.5}
                      />
                      <span className="text-muted-foreground">ft</span>
                    </div>
                  ) : (
                    (bowDetail as { pool_depth_shallow?: number }).pool_depth_shallow
                      ? <span className="font-medium">{(bowDetail as { pool_depth_shallow: number }).pool_depth_shallow} ft</span>
                      : <span className="text-muted-foreground/50 italic">&mdash;</span>
                  )}
                </div>
                {/* Deep depth */}
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-muted-foreground">Deep depth</span>
                  {isMeasuring ? (
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        placeholder="ft"
                        value={deepDepthInputs.get(wf.id) ?? ((bowDetail as { pool_depth_deep?: number }).pool_depth_deep?.toString() || "")}
                        onChange={(e) => onSetDeepDepth(wf.id, e.target.value)}
                        className="h-6 w-16 text-[11px] px-1.5"
                        min={0}
                        max={15}
                        step={0.5}
                      />
                      <span className="text-muted-foreground">ft</span>
                    </div>
                  ) : (
                    (bowDetail as { pool_depth_deep?: number }).pool_depth_deep
                      ? <span className="font-medium">{(bowDetail as { pool_depth_deep: number }).pool_depth_deep} ft</span>
                      : <span className="text-muted-foreground/50 italic">&mdash;</span>
                  )}
                </div>
                {/* Surface & Structure */}
                <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70 pt-1.5 mt-1.5 border-t border-border/50">Surface & Structure</p>
                {[
                  { label: "Surface", value: (bowDetail as { pool_surface?: string }).pool_surface?.replace(/_/g, " ") || null },
                  { label: "Cover", value: (bowDetail as { pool_cover_type?: string }).pool_cover_type?.replace(/_/g, " ") || null },
                  { label: "Skimmers", value: (bowDetail as { skimmer_count?: number }).skimmer_count != null ? String((bowDetail as { skimmer_count: number }).skimmer_count) : null },
                ].map((d) => (
                  <div key={d.label} className="flex justify-between text-[11px]">
                    <span className="text-muted-foreground">{d.label}</span>
                    {d.value ? <span className="font-medium capitalize">{d.value}</span> : <span className="text-muted-foreground/50 italic">&mdash;</span>}
                  </div>
                ))}
                {/* Edit mode: Save + Google Maps link */}
                {isMeasuring && canEdit && (
                  <div className="flex items-center justify-between pt-1.5 border-t border-border/50 mt-1.5">
                    {(wf.pool_lat || (wf.lat && wf.lng)) ? (
                      <a
                        href={`https://www.google.com/maps/@${(wf.pool_lat ?? wf.lat)},${(wf.pool_lng ?? wf.lng)},20z/data=!3m1!1e3`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <ExternalLink className="h-2.5 w-2.5" />
                        Measure in Google Maps
                      </a>
                    ) : <span />}
                    <Button
                      size="sm"
                      className="h-6 px-3 text-[11px]"
                      disabled={savingPerimeter || (!perimeterInput && !areaInputs.get(wf.id) && !volumeInputs.get(wf.id) && !roundedCornersInputs.has(wf.id) && !stepEntryInputs.has(wf.id) && !benchShelfInputs.has(wf.id) && !shallowDepthInputs.has(wf.id) && !deepDepthInputs.has(wf.id))}
                      onClick={() => onSaveMeasurements(wf.id)}
                    >
                      {savingPerimeter ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                    </Button>
                  </div>
                )}
              </div>
            </div>

            {/* Pool & Equipment */}
            <div className="bg-muted/50 rounded-md overflow-hidden">
              <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                <Wrench className="h-3 w-3 text-muted-foreground" />
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Equipment & Plumbing</span>
              </div>
              <div className="px-2.5 py-2 space-y-3">
                {/* Plumbing & Drains */}
                <div className="space-y-1">
                  <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">Plumbing & Drains</p>
                  {[
                    { icon: Pipette, label: "Plumbing", value: (bowDetail as Record<string, unknown>).plumbing_size_inches != null ? `${(bowDetail as Record<string, unknown>).plumbing_size_inches} in` : undefined },
                    { icon: Droplets, label: "Fill", value: (bowDetail as Record<string, unknown>).fill_method as string | undefined },
                    { icon: CircleDot, label: "Drain type", value: (bowDetail as Record<string, unknown>).drain_type as string | undefined },
                    { icon: CircleDot, label: "Drain method", value: (bowDetail as Record<string, unknown>).drain_method as string | undefined },
                    { icon: CircleDot, label: "Drains", value: (bowDetail as Record<string, unknown>).drain_count != null ? String((bowDetail as Record<string, unknown>).drain_count) : undefined },
                    { icon: Clock, label: "Turnover", value: (bowDetail as Record<string, unknown>).turnover_hours != null ? `${(bowDetail as Record<string, unknown>).turnover_hours} hrs` : undefined },
                  ].map((e) => (
                    <div key={e.label} className="flex items-center gap-1.5 text-[11px]">
                      <e.icon className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                      <span className="text-muted-foreground">{e.label}</span>
                      <span className="truncate ml-auto">
                        {e.value ? <span className="font-medium capitalize">{e.value.replace(/_/g, " ")}</span> : <span className="text-muted-foreground/50 italic">&mdash;</span>}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Drain Covers */}
                {((bowDetail as Record<string, unknown>).drain_cover_compliant != null || (bowDetail as Record<string, unknown>).equalizer_cover_compliant != null) && (
                  <div className="space-y-1">
                    <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">Drain Covers</p>
                    {(bowDetail as Record<string, unknown>).drain_cover_compliant != null && (
                      <div className="text-[11px] space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <Shield className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                          <span className="text-muted-foreground">Drain covers</span>
                          <Badge className={`ml-auto text-[9px] px-1 py-0 ${(bowDetail as Record<string, unknown>).drain_cover_compliant ? "bg-green-100 text-green-800 hover:bg-green-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                            {(bowDetail as Record<string, unknown>).drain_cover_compliant ? "Compliant" : "Non-compliant"}
                          </Badge>
                        </div>
                        {!!((bowDetail as Record<string, unknown>).drain_cover_install_date || (bowDetail as Record<string, unknown>).drain_cover_expiry_date) && (
                          <p className="text-[10px] text-muted-foreground pl-4">
                            {!!(bowDetail as Record<string, unknown>).drain_cover_install_date && `Installed: ${new Date(String((bowDetail as Record<string, unknown>).drain_cover_install_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                            {!!(bowDetail as Record<string, unknown>).drain_cover_install_date && !!(bowDetail as Record<string, unknown>).drain_cover_expiry_date && " \u00B7 "}
                            {!!(bowDetail as Record<string, unknown>).drain_cover_expiry_date && `Expires: ${new Date(String((bowDetail as Record<string, unknown>).drain_cover_expiry_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                          </p>
                        )}
                      </div>
                    )}
                    {(bowDetail as Record<string, unknown>).equalizer_cover_compliant != null && (
                      <div className="text-[11px] space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <Shield className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                          <span className="text-muted-foreground">Equalizer covers</span>
                          <Badge className={`ml-auto text-[9px] px-1 py-0 ${(bowDetail as Record<string, unknown>).equalizer_cover_compliant ? "bg-green-100 text-green-800 hover:bg-green-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                            {(bowDetail as Record<string, unknown>).equalizer_cover_compliant ? "Compliant" : "Non-compliant"}
                          </Badge>
                        </div>
                        {!!((bowDetail as Record<string, unknown>).equalizer_cover_install_date || (bowDetail as Record<string, unknown>).equalizer_cover_expiry_date) && (
                          <p className="text-[10px] text-muted-foreground pl-4">
                            {!!(bowDetail as Record<string, unknown>).equalizer_cover_install_date && `Installed: ${new Date(String((bowDetail as Record<string, unknown>).equalizer_cover_install_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                            {!!(bowDetail as Record<string, unknown>).equalizer_cover_install_date && !!(bowDetail as Record<string, unknown>).equalizer_cover_expiry_date && " \u00B7 "}
                            {!!(bowDetail as Record<string, unknown>).equalizer_cover_expiry_date && `Expires: ${new Date(String((bowDetail as Record<string, unknown>).equalizer_cover_expiry_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Equipment */}
                <div className="space-y-1">
                  <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">Equipment</p>
                  {[
                    { icon: Gauge, label: "Pump", value: (bowDetail as Record<string, unknown>).pump_type as string | undefined },
                    { icon: FlaskConical, label: "Filter", value: (bowDetail as Record<string, unknown>).filter_type as string | undefined },
                    { icon: Thermometer, label: "Heater", value: (bowDetail as Record<string, unknown>).heater_type as string | undefined },
                    { icon: FlaskConical, label: "Chlor.", value: (bowDetail as Record<string, unknown>).chlorinator_type as string | undefined },
                    { icon: Zap, label: "Auto", value: (bowDetail as Record<string, unknown>).automation_system as string | undefined },
                    { icon: Calendar, label: "Year", value: (bowDetail as Record<string, unknown>).equipment_year != null ? String((bowDetail as Record<string, unknown>).equipment_year) : undefined },
                    { icon: MapPin, label: "Location", value: (bowDetail as Record<string, unknown>).equipment_pad_location as string | undefined },
                  ].map((e) => (
                    <div key={e.label} className="flex items-center gap-1.5 text-[11px]">
                      <e.icon className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                      <span className="text-muted-foreground">{e.label}</span>
                      <span className="truncate ml-auto">
                        {e.value ? <span className="font-medium">{e.value}</span> : <span className="text-muted-foreground/50 italic">&mdash;</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Aerial analysis */}
        {analysis && !analysis.error_message && analysis.pool_detected && (
          <div className="rounded-md bg-muted/50 p-2.5 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100 text-[10px]">Aerial</Badge>
              <Badge className={`text-[10px] ${analysis.pool_confidence >= 0.7 ? "bg-green-100 text-green-800 hover:bg-green-100" : analysis.pool_confidence >= 0.4 ? "bg-yellow-100 text-yellow-800 hover:bg-yellow-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                {(analysis.pool_confidence * 100).toFixed(0)}%
              </Badge>
              <span className="text-[10px] text-muted-foreground ml-auto">
                Veg {analysis.vegetation_pct}% &middot; Canopy {analysis.canopy_overhang_pct}% &middot; Shadow {analysis.shadow_pct}%
              </span>
            </div>
          </div>
        )}
        {analysis?.error_message && (
          <div className="rounded-md bg-destructive/5 p-2.5">
            <Badge variant="destructive" className="text-[10px]">Analysis Error</Badge>
            <p className="text-[11px] text-muted-foreground mt-1">{analysis.error_message}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
