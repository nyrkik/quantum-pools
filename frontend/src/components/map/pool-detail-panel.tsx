"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Loader2,
  MapPin,
  Camera,
  Star,
  Trash2,
  DollarSign,
  Calendar,
  Dog,
  Lock,
  Pencil,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
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
import type { SatelliteAnalysis, PoolBowWithCoords } from "@/types/satellite";
import type { PropertyPhoto } from "@/types/photo";
import type { PropertyGroup } from "@/components/maps/satellite-map";
import WfDetailTile from "./wf-detail-tile";
import type { PortfolioMedians, DimensionComparison } from "./map-types";

import { getBackendOrigin } from "@/lib/api";
const API_BASE = typeof window !== "undefined" ? getBackendOrigin() : "http://localhost:7061";

interface PoolDetailPanelProps {
  selectedGroup: PropertyGroup;
  selectedPropertyId: string;
  canEdit: boolean;
  movingProperty: boolean;
  propertyPinPosition: { lat: number; lng: number } | null;
  savingPropertyPin: boolean;
  propDetail: Record<string, unknown> | null;
  profitData: Record<string, unknown> | null;
  medians: PortfolioMedians | null;
  chemicalCosts: Map<string, { sanitizer_cost: number; acid_cost: number; cya_cost: number; salt_cost: number; cell_cost: number; insurance_cost: number; total_monthly: number; source: string }>;
  costExpanded: boolean;
  bowDetails: Map<string, Record<string, unknown>>;
  dimComparisons: Map<string, DimensionComparison>;
  analysisMap: Map<string | null, SatelliteAnalysis>;
  rateAllocation: Record<string, { allocated_rate: number; allocation_method: string; weight: number }>;
  images: PropertyPhoto[];
  capturing: boolean;
  // WF tile state
  activeBowId: string | null;
  highlightedBowId: string | null;
  pinDirty: boolean;
  savingPin: boolean;
  savingPerimeter: boolean;
  measuringPerimeterBow: string | null;
  dismissedDiscrepancies: Set<string>;
  perimeterInputs: Map<string, string>;
  areaInputs: Map<string, string>;
  volumeInputs: Map<string, string>;
  perimeterShapes: Map<string, string>;
  roundedCornersInputs: Map<string, boolean>;
  stepEntryInputs: Map<string, number>;
  benchShelfInputs: Map<string, boolean>;
  shallowDepthInputs: Map<string, string>;
  deepDepthInputs: Map<string, string>;
  perms: { canViewRates: boolean; canViewDimensions: boolean; canViewProfitability: boolean };
  // Callbacks
  onSetMovingProperty: (moving: boolean) => void;
  onSetPropertyPinPosition: (pos: { lat: number; lng: number } | null) => void;
  onSavePropertyLocation: () => void;
  onSetCostExpanded: (expanded: boolean) => void;
  onSetDiffModalOpen: (open: boolean) => void;
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
  onUploadPhoto: (file: File) => void;
  onSetHero: (imageId: string) => void;
  onDeleteImage: (imageId: string) => void;
  // For pin/move reset
  onResetPinState: () => void;
}

export default function PoolDetailPanel({
  selectedGroup,
  selectedPropertyId,
  canEdit,
  movingProperty,
  propertyPinPosition,
  savingPropertyPin,
  propDetail,
  profitData,
  medians,
  chemicalCosts,
  costExpanded,
  bowDetails,
  dimComparisons,
  analysisMap,
  rateAllocation,
  images,
  capturing,
  activeBowId,
  highlightedBowId,
  pinDirty,
  savingPin,
  savingPerimeter,
  measuringPerimeterBow,
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
  onSetMovingProperty,
  onSetPropertyPinPosition,
  onSavePropertyLocation,
  onSetCostExpanded,
  onSetDiffModalOpen,
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
  onUploadPhoto,
  onSetHero,
  onDeleteImage,
  onResetPinState,
}: PoolDetailPanelProps) {
  const compare = (val: number | null, med: number | null | undefined, higherIsGood: boolean) => {
    if (val == null || med == null || med === 0) return null;
    const pct = ((val - med) / med) * 100;
    if (Math.abs(pct) < 5) return { arrow: "~", color: "text-muted-foreground", tip: `median ${med.toFixed(1)}` };
    const above = pct > 0;
    const good = higherIsGood ? above : !above;
    return {
      arrow: above ? "\u2191" : "\u2193",
      color: good ? "text-emerald-600" : "text-red-500",
      tip: `${above ? "+" : ""}${pct.toFixed(0)}% vs median`,
    };
  };

  return (
    <div className="space-y-3">
      {/* Property header + Profitability combined */}
      <Card className={`shadow-sm ${movingProperty ? "border-l-4 border-l-primary" : ""}`}>
        <CardContent className="p-4">
          <div className="flex gap-4">
            {/* Left: Identity */}
            <div className="w-1/3 shrink-0 min-w-0">
              <Link href={`/customers/${selectedGroup.customer_id}`} className="text-sm font-semibold truncate hover:underline">{selectedGroup.customer_name}</Link>
              <p className="text-xs text-muted-foreground truncate">{selectedGroup.address}</p>
              {selectedGroup.city && (
                <p className="text-[10px] text-muted-foreground/70 truncate">{selectedGroup.city}</p>
              )}
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                {selectedGroup.tech_name && (
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: selectedGroup.tech_color || '#94a3b8' }} />
                    <span className="font-medium truncate">{selectedGroup.tech_name}</span>
                  </div>
                )}
                {propDetail && (propDetail as { service_day_pattern?: string }).service_day_pattern && (
                  <div className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                    <Calendar className="h-2.5 w-2.5" />
                    {((propDetail as { service_day_pattern: string }).service_day_pattern).split(",").map((d: string) => (
                      <Badge key={d} variant="outline" className="text-[9px] px-0.5 py-0">{d.trim().slice(0, 3)}</Badge>
                    ))}
                  </div>
                )}
                {propDetail && (propDetail as { dog_on_property?: boolean }).dog_on_property && (
                  <Dog className="h-3 w-3 text-amber-500" />
                )}
                {propDetail && (propDetail as { gate_code?: string }).gate_code && (
                  <div className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                    <Lock className="h-2.5 w-2.5" />
                    {(propDetail as { gate_code: string }).gate_code}
                  </div>
                )}
                {selectedGroup.wfs.length > 1 && (
                  <Badge variant="secondary" className="text-[9px] px-1 py-0">{selectedGroup.wfs.length} features</Badge>
                )}
              </div>
              {canEdit && (
                <button
                  onClick={() => { onSetMovingProperty(!movingProperty); onSetPropertyPinPosition(null); onResetPinState(); }}
                  className={`flex items-center gap-1 mt-1.5 text-[10px] transition-colors ${
                    movingProperty ? "text-primary font-medium" : "text-muted-foreground/50 hover:text-muted-foreground"
                  }`}
                >
                  <MapPin className="h-2.5 w-2.5" />
                  {movingProperty ? "Placing marker..." : "Move marker"}
                </button>
              )}
            </div>

            {/* Right: Profitability metrics */}
            <div className="flex-1 min-w-0">
              {/* Property move banner */}
              {movingProperty && (
                <div className={`rounded px-2 py-1.5 mb-2 flex items-center justify-between text-[11px] ${
                  propertyPinPosition
                    ? "bg-amber-50 dark:bg-amber-950/30 border border-amber-300"
                    : "bg-muted/50 border border-border"
                }`}>
                  {propertyPinPosition ? (
                    <>
                      <span className="text-amber-700 dark:text-amber-400 font-medium">
                        {propertyPinPosition.lat.toFixed(6)}, {propertyPinPosition.lng.toFixed(6)}
                      </span>
                      <div className="flex gap-1">
                        <Button size="sm" className="h-5 px-2 text-[10px]" disabled={savingPropertyPin} onClick={onSavePropertyLocation}>
                          {savingPropertyPin ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                        </Button>
                        <Button size="sm" variant="ghost" className="h-5 px-2 text-[10px]" onClick={() => { onSetMovingProperty(false); onSetPropertyPinPosition(null); }}>
                          Cancel
                        </Button>
                      </div>
                    </>
                  ) : (
                    <span className="text-muted-foreground">Click map to set property location</span>
                  )}
                </div>
              )}
              {perms.canViewProfitability && profitData && (() => {
                const cost = (profitData as { cost_breakdown: { revenue: number; total_cost: number; profit: number; margin_pct: number; chemical_cost: number; labor_cost: number; travel_cost: number; overhead_cost: number } }).cost_breakdown;
                if (!cost) return null;
                const diff = (profitData as { difficulty_score: number }).difficulty_score;
                const rpg = (profitData as { rate_per_gallon?: number }).rate_per_gallon;
                const m = medians;

                const metrics = [
                  { label: "Rate/gal", value: rpg ? `${(rpg * 100).toFixed(1)}\u00A2` : null, medianLabel: m?.rate_per_gallon ? `${(m.rate_per_gallon * 100).toFixed(1)}\u00A2` : null, color: "text-foreground", cmp: compare(rpg ? rpg * 100 : null, m?.rate_per_gallon ? m.rate_per_gallon * 100 : null, true), editable: false, expandable: false },
                  { label: "Est. Cost", value: `$${cost.total_cost.toFixed(0)}`, medianLabel: m ? `$${m.cost.toFixed(0)}` : null, color: "text-muted-foreground", cmp: compare(cost.total_cost, m?.cost, false), editable: false, expandable: true },
                  { label: "Margin", value: `${cost.margin_pct.toFixed(1)}%`, medianLabel: m ? `${m.margin_pct.toFixed(1)}%` : null, color: cost.margin_pct >= 30 ? "text-emerald-600" : cost.margin_pct >= 0 ? "text-amber-600" : "text-red-600", cmp: compare(cost.margin_pct, m?.margin_pct, true), editable: false, expandable: false },
                  { label: "Diff", value: `${diff.toFixed(1)}`, medianLabel: m ? `${m.difficulty.toFixed(1)}` : null, color: diff > 3.5 ? "text-red-600" : diff > 2.5 ? "text-amber-600" : "text-muted-foreground", cmp: compare(diff, m?.difficulty, false), editable: true, expandable: false },
                ];

                // Sum chemical costs across all WFs
                const chemSum = { sanitizer: 0, acid: 0, insurance: 0, salt_cell: 0, total: 0 };
                let hasSalt = false;
                for (const [, cc] of chemicalCosts) {
                  chemSum.sanitizer += cc.sanitizer_cost;
                  chemSum.acid += cc.acid_cost;
                  chemSum.insurance += cc.insurance_cost;
                  chemSum.salt_cell += cc.salt_cost + cc.cell_cost;
                  chemSum.total += cc.total_monthly;
                  if (cc.salt_cost > 0 || cc.cell_cost > 0) hasSalt = true;
                }

                return (
                  <div className="space-y-1.5">
                    <div className="grid grid-cols-2 gap-1.5">
                      {metrics.map((mt) => (
                        <div
                          key={mt.label}
                          className={`bg-muted/50 rounded px-2 py-1.5 ${mt.expandable ? "cursor-pointer hover:bg-muted/80 transition-colors" : ""}`}
                          onClick={mt.expandable ? () => onSetCostExpanded(!costExpanded) : undefined}
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{mt.label}</p>
                            {mt.expandable && (
                              costExpanded
                                ? <ChevronUp className="h-2.5 w-2.5 text-muted-foreground" />
                                : <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" />
                            )}
                            {mt.editable && canEdit && selectedPropertyId && (
                              <button className="text-muted-foreground hover:text-foreground" onClick={(e) => { e.stopPropagation(); onSetDiffModalOpen(true); }}>
                                <Pencil className="h-2.5 w-2.5" />
                              </button>
                            )}
                          </div>
                          <div className="flex items-baseline gap-1">
                            {mt.cmp ? (
                              <>
                                <p className={`text-sm font-bold leading-tight ${mt.cmp.color}`}>{mt.value ?? "\u2014"}</p>
                                <span className={`text-[10px] font-bold ${mt.cmp.color}`}>
                                  {mt.cmp.arrow === "~" ? "\u00B7" : mt.cmp.arrow === "\u2191" ? "\u25B2" : "\u25BC"}
                                </span>
                                {mt.medianLabel && (
                                  <span className="text-[9px] text-muted-foreground/50">/ {mt.medianLabel}</span>
                                )}
                              </>
                            ) : (
                              <p className={`text-sm font-bold leading-tight ${mt.color}`}>{mt.value ?? "\u2014"}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    {costExpanded && (
                      <div className="bg-muted/50 rounded px-3 py-2 space-y-1">
                        <p className="text-[9px] text-muted-foreground uppercase tracking-wide mb-1.5">Cost Breakdown</p>
                        {[
                          { label: "Sanitizer", value: chemSum.sanitizer },
                          { label: "Acid", value: chemSum.acid },
                          { label: "Insurance", value: chemSum.insurance },
                          ...(hasSalt ? [{ label: "Salt/Cell", value: chemSum.salt_cell }] : []),
                          { label: "Total Chemical", value: chemSum.total, bold: true },
                          { label: "Labor", value: cost.labor_cost },
                          { label: "Travel", value: cost.travel_cost },
                          { label: "Overhead", value: cost.overhead_cost },
                        ].map((row) => (
                          <div key={row.label} className={`flex justify-between text-[11px] ${(row as { bold?: boolean }).bold ? "border-t border-border/50 pt-1 font-medium" : ""}`}>
                            <span className="text-muted-foreground">{row.label}</span>
                            <span className={`${(row as { bold?: boolean }).bold ? "text-foreground" : "text-foreground/80"}`}>${row.value.toFixed(2)}</span>
                          </div>
                        ))}
                        <div className="flex justify-between text-[11px] border-t border-border pt-1 font-bold">
                          <span className="text-foreground">Total</span>
                          <span className="text-foreground">${cost.total_cost.toFixed(2)}</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* WF tiles — one per pool at this property */}
      {selectedGroup.wfs.map((wf) => (
        <WfDetailTile
          key={wf.id}
          wf={wf}
          bowDetail={bowDetails.get(wf.id) || null}
          dimComparison={dimComparisons.get(wf.id) || null}
          analysis={analysisMap.get(wf.id) || null}
          activeBowId={activeBowId}
          highlightedBowId={highlightedBowId}
          canEdit={canEdit}
          pinDirty={pinDirty}
          savingPin={savingPin}
          savingPerimeter={savingPerimeter}
          measuringPerimeterBow={measuringPerimeterBow}
          rateAllocation={rateAllocation}
          profitData={profitData}
          dismissedDiscrepancies={dismissedDiscrepancies}
          perimeterInputs={perimeterInputs}
          areaInputs={areaInputs}
          volumeInputs={volumeInputs}
          perimeterShapes={perimeterShapes}
          roundedCornersInputs={roundedCornersInputs}
          stepEntryInputs={stepEntryInputs}
          benchShelfInputs={benchShelfInputs}
          shallowDepthInputs={shallowDepthInputs}
          deepDepthInputs={deepDepthInputs}
          perms={perms}
          onHighlightBow={onHighlightBow}
          onSavePin={onSavePin}
          onSetMeasuringBow={onSetMeasuringBow}
          onSetPerimeterInput={onSetPerimeterInput}
          onSetAreaInput={onSetAreaInput}
          onSetVolumeInput={onSetVolumeInput}
          onSetPerimeterShape={onSetPerimeterShape}
          onSetRoundedCorners={onSetRoundedCorners}
          onSetStepEntry={onSetStepEntry}
          onSetBenchShelf={onSetBenchShelf}
          onSetShallowDepth={onSetShallowDepth}
          onSetDeepDepth={onSetDeepDepth}
          onSaveMeasurements={onSaveMeasurements}
          onDismissDiscrepancy={onDismissDiscrepancy}
        />
      ))}

      {/* Photos — property-level */}
      <Card className="shadow-sm">
        <CardContent className="p-4 space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Camera className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Photos</span>
              <span className="text-[10px] text-muted-foreground/50">{images.length}/8</span>
            </div>
            {canEdit && (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2 text-[11px] text-muted-foreground"
                  disabled={capturing || images.length >= 8}
                  onClick={() => document.getElementById("photo-upload")?.click()}
                >
                  {capturing ? <Loader2 className="h-3 w-3 animate-spin" /> : "Upload"}
                </Button>
                <input
                  id="photo-upload"
                  type="file"
                  accept="image/*"
                  capture="environment"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) onUploadPhoto(file);
                    e.target.value = "";
                  }}
                />
              </>
            )}
          </div>
          {images.length > 0 ? (
            <div className="grid grid-cols-3 gap-1.5">
              {images.map((img) => (
                <div key={img.id} className="relative group">
                  <img
                    src={`${API_BASE}${img.url}`}
                    alt={img.caption || "Property photo"}
                    className={`w-full aspect-square object-cover rounded border-2 ${
                      img.is_hero ? "border-amber-400" : "border-transparent"
                    }`}
                  />
                  {img.is_hero && (
                    <div className="absolute top-0.5 left-0.5">
                      <Star className="h-3 w-3 fill-amber-400 text-amber-400 drop-shadow" />
                    </div>
                  )}
                  {canEdit && (
                  <div className="absolute top-0.5 right-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5">
                    {!img.is_hero && (
                      <Button variant="secondary" size="icon" className="h-5 w-5 bg-white/90 hover:bg-white shadow-sm" onClick={() => onSetHero(img.id)} title="Set as hero">
                        <Star className="h-2.5 w-2.5" />
                      </Button>
                    )}
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="secondary" size="icon" className="h-5 w-5 bg-white/90 hover:bg-white shadow-sm text-destructive" title="Delete">
                          <Trash2 className="h-2.5 w-2.5" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete photo?</AlertDialogTitle>
                          <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDeleteImage(img.id)}>Delete</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground/50 italic">No photos yet</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
