"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Clock,
  Copy,
  Dog,
  Droplets,
  Pencil,
  StickyNote,
  Waves,
  WavesLadder,
} from "lucide-react";
import { toast } from "sonner";
import type { Permissions } from "@/lib/permissions";
import { WfDetailSections } from "./wf-detail-sections";

export interface WfQuickViewReading {
  ph?: number | null;
  free_chlorine?: number | null;
  cyanuric_acid?: number | null;
  created_at?: string;
}

interface WfData {
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

interface PropertyData {
  gate_code: string | null;
  access_instructions: string | null;
  dog_on_property: boolean;
  service_day_pattern: string | null;
}

interface CustomerData {
  preferred_day: string | null;
}

interface WfQuickViewProps {
  wf: WfData;
  property: PropertyData;
  customer: CustomerData;
  lastReading?: WfQuickViewReading | null;
  perms: Permissions;
  onEdit?: () => void;
}

function waterTypeIcon(type: string, className: string) {
  switch (type) {
    case "spa":
    case "hot_tub":
      return <Droplets className={className} />;
    case "fountain":
    case "water_feature":
    case "wading_pool":
      return <Waves className={className} />;
    default:
      return <WavesLadder className={className} />;
  }
}

const SANITIZER_STYLES: Record<string, string> = {
  tabs: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
  liquid: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  salt: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-400",
  granular: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400",
  cal_hypo: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400",
  bromine: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-400",
  uv_ozone: "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-400",
};

const SANITIZER_LABELS: Record<string, string> = {
  tabs: "Tabs",
  liquid: "Liquid",
  salt: "Salt",
  granular: "Granular",
  cal_hypo: "Cal-Hypo",
  bromine: "Bromine",
  uv_ozone: "UV/Ozone",
};

function dayBadges(pattern: string | null) {
  if (!pattern) return null;
  const days = pattern.split(",").map((d) => d.trim()).filter(Boolean);
  return days.length > 0 ? days : null;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks === 1) return "1 week ago";
  if (weeks < 4) return `${weeks} weeks ago`;
  const months = Math.floor(days / 30);
  if (months === 1) return "1 month ago";
  return `${months} months ago`;
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success("Copied to clipboard"),
    () => toast.error("Failed to copy")
  );
}

export function WfQuickView({
  wf,
  property,
  customer,
  lastReading,
  perms,
  onEdit,
}: WfQuickViewProps) {
  const serviceDays = dayBadges(property.service_day_pattern || customer.preferred_day);
  const hasNotes = !!wf.notes;
  const hasGateOrAccess = !!property.gate_code || !!property.access_instructions;

  return (
    <div className="rounded-lg border shadow-sm bg-card overflow-hidden">
      {/* Notes/alerts banner */}
      {hasNotes && (
        <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200/50 dark:border-amber-800/50">
          <StickyNote className="h-3.5 w-3.5 text-amber-600 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-800 dark:text-amber-300 line-clamp-2">{wf.notes}</p>
        </div>
      )}

      {/* Quick view content */}
      <div className="px-3 py-3 space-y-2">
        {/* Line 1: WF name + gallons */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {waterTypeIcon(wf.water_type, "h-4 w-4 text-primary/60 shrink-0")}
            <span className="text-sm font-semibold truncate">
              {wf.name || wf.water_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {wf.pool_gallons && (
              <span className="text-sm font-medium text-muted-foreground">
                {wf.pool_gallons.toLocaleString()} <span className="text-xs">gal</span>
              </span>
            )}
            {onEdit && (
              <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onEdit}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>

        {/* Line 2: Sanitizer + service minutes */}
        <div className="flex items-center justify-between gap-2">
          {wf.sanitizer_type ? (
            <span className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${SANITIZER_STYLES[wf.sanitizer_type] || "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}>
              {SANITIZER_LABELS[wf.sanitizer_type] || wf.sanitizer_type.replace(/_/g, " ")}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground/50 italic">No sanitizer set</span>
          )}
          <div className="flex items-center gap-1 text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span className="text-xs">~{wf.estimated_service_minutes} min</span>
          </div>
        </div>

        {/* Line 3: Service days + dog */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1 flex-wrap">
            {serviceDays ? (
              serviceDays.map((d) => (
                <Badge key={d} variant="secondary" className="text-[10px] px-1.5 py-0 font-medium">{d}</Badge>
              ))
            ) : (
              <span className="text-xs text-muted-foreground/50 italic">No schedule set</span>
            )}
          </div>
          {property.dog_on_property && (
            <div className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
              <Dog className="h-4 w-4" />
              <span className="text-xs font-medium">Dog</span>
            </div>
          )}
        </div>

        {/* Line 4: Gate code + access */}
        {hasGateOrAccess && (
          <div className="flex items-start gap-2 text-xs">
            {property.gate_code && (
              <button
                type="button"
                onClick={() => copyToClipboard(property.gate_code!)}
                className="flex items-center gap-1 text-foreground font-mono bg-muted px-1.5 py-0.5 rounded hover:bg-muted/80 transition-colors cursor-pointer shrink-0 min-h-[28px]"
              >
                <span>Gate: {property.gate_code}</span>
                <Copy className="h-3 w-3 text-muted-foreground" />
              </button>
            )}
            {property.access_instructions && (
              <span className="text-muted-foreground truncate pt-0.5">{property.access_instructions}</span>
            )}
          </div>
        )}

        {/* Line 5: Last reading summary */}
        <div className="flex items-center justify-between gap-2 pt-1 border-t border-dashed">
          {lastReading && lastReading.created_at ? (
            <>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Last:</span>
                {lastReading.ph != null && (
                  <span>pH <span className="font-medium">{lastReading.ph.toFixed(1)}</span></span>
                )}
                {lastReading.free_chlorine != null && (
                  <span>
                    {lastReading.ph != null && <span className="text-muted-foreground"> | </span>}
                    FC <span className="font-medium">{lastReading.free_chlorine.toFixed(1)}</span>
                  </span>
                )}
                {lastReading.cyanuric_acid != null && (
                  <span>
                    {(lastReading.ph != null || lastReading.free_chlorine != null) && <span className="text-muted-foreground"> | </span>}
                    CYA <span className="font-medium">{lastReading.cyanuric_acid.toFixed(0)}</span>
                  </span>
                )}
              </div>
              <span className="text-[10px] text-muted-foreground shrink-0">{timeAgo(lastReading.created_at)}</span>
            </>
          ) : (
            <span className="text-xs text-muted-foreground/50 italic">No readings yet</span>
          )}
        </div>
      </div>

      {/* Expandable detail sections */}
      <WfDetailSections wf={wf} perms={perms} />
    </div>
  );
}
