"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  ChevronDown,
  ChevronUp,
  DollarSign,
  Ruler,
  Search,
  Shield,
  Wrench,
} from "lucide-react";
import type { Permissions } from "@/lib/permissions";

interface WfFields {
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
  pool_volume_method: string | null;
  drain_cover_compliant: boolean | null;
  drain_cover_install_date: string | null;
  drain_cover_expiry_date: string | null;
  equalizer_cover_compliant: boolean | null;
  equalizer_cover_install_date: string | null;
  equalizer_cover_expiry_date: string | null;
  plumbing_size_inches: number | null;
  turnover_hours: number | null;
  drain_count: number | null;
  drain_type: string | null;
  skimmer_count: number | null;
  pool_cover_type: string | null;
  fill_method: string | null;
  monthly_rate: number | null;
  pool_type: string | null;
}

interface WfDetailSectionsProps {
  wf: WfFields;
  perms: Permissions;
}

function CollapsibleSection({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 w-full px-3 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors cursor-pointer min-h-[44px]"
        >
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {title}
          </span>
          <span className="ml-auto">
            {open ? (
              <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            )}
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
      {value ? (
        <span className="font-medium capitalize">{value.replace(/_/g, " ")}</span>
      ) : (
        <span className="text-muted-foreground/50 italic">--</span>
      )}
    </div>
  );
}

function EquipmentSearchLink({ query }: { query: string }) {
  return (
    <a
      href={`https://www.google.com/search?q=${encodeURIComponent(query + " parts")}`}
      target="_blank"
      rel="noopener noreferrer"
      className="text-muted-foreground hover:text-foreground transition-colors"
      onClick={(e) => e.stopPropagation()}
    >
      <Search className="h-3 w-3" />
    </a>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function WfDetailSections({ wf, perms }: WfDetailSectionsProps) {
  return (
    <div className="border-t">
      {/* Equipment */}
      <CollapsibleSection icon={Wrench} title="Equipment">
        <div className="px-3 py-2.5 space-y-1.5 border-b">
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
                  <span className="font-medium">{eq.value}</span>
                  <EquipmentSearchLink query={eq.value} />
                </div>
              ) : (
                <span className="text-muted-foreground/50 italic">--</span>
              )}
            </div>
          ))}
          {wf.equipment_year && <DetailRow label="Year" value={String(wf.equipment_year)} />}
          {wf.equipment_pad_location && <DetailRow label="Pad Location" value={wf.equipment_pad_location} />}
        </div>
      </CollapsibleSection>

      {/* Dimensions */}
      {perms.canViewDimensions && (
        <CollapsibleSection icon={Ruler} title="Dimensions">
          <div className="px-3 py-2.5 space-y-1.5 border-b">
            <DetailRow label="Shape" value={wf.pool_shape} />
            <div className="flex justify-between text-xs py-0.5">
              <span className="text-muted-foreground">L x W</span>
              {wf.pool_length_ft && wf.pool_width_ft ? (
                <span className="font-medium">{wf.pool_length_ft} x {wf.pool_width_ft} ft</span>
              ) : (
                <span className="text-muted-foreground/50 italic">--</span>
              )}
            </div>
            <div className="flex justify-between text-xs py-0.5">
              <span className="text-muted-foreground">Depth</span>
              {wf.pool_depth_shallow && wf.pool_depth_deep ? (
                <span className="font-medium">{wf.pool_depth_shallow}&ndash;{wf.pool_depth_deep} ft</span>
              ) : wf.pool_depth_avg ? (
                <span className="font-medium">{wf.pool_depth_avg} ft avg</span>
              ) : (
                <span className="text-muted-foreground/50 italic">--</span>
              )}
            </div>
            <DetailRow label="Surface" value={wf.pool_surface} />
            {wf.pool_sqft && <DetailRow label="Area" value={`${wf.pool_sqft.toLocaleString()} sqft`} />}
            {wf.perimeter_ft && <DetailRow label="Perimeter" value={`${wf.perimeter_ft} ft`} />}
            {wf.pool_volume_method && <DetailRow label="Volume Method" value={wf.pool_volume_method} />}
          </div>
        </CollapsibleSection>
      )}

      {/* Compliance */}
      <CollapsibleSection icon={Shield} title="Compliance">
        <div className="px-3 py-2.5 space-y-2 border-b">
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Drain Covers</span>
              {wf.drain_cover_compliant != null ? (
                <Badge className={`text-[10px] px-1.5 py-0 ${wf.drain_cover_compliant ? "bg-green-100 text-green-800 hover:bg-green-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                  {wf.drain_cover_compliant ? "Compliant" : "Non-compliant"}
                </Badge>
              ) : (
                <span className="text-muted-foreground/50 italic text-xs">--</span>
              )}
            </div>
            {(wf.drain_cover_install_date || wf.drain_cover_expiry_date) && (
              <p className="text-[10px] text-muted-foreground pl-2">
                {wf.drain_cover_install_date && `Installed: ${formatDate(wf.drain_cover_install_date)}`}
                {wf.drain_cover_install_date && wf.drain_cover_expiry_date && " \u00b7 "}
                {wf.drain_cover_expiry_date && `Expires: ${formatDate(wf.drain_cover_expiry_date)}`}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Equalizer Covers</span>
              {wf.equalizer_cover_compliant != null ? (
                <Badge className={`text-[10px] px-1.5 py-0 ${wf.equalizer_cover_compliant ? "bg-green-100 text-green-800 hover:bg-green-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                  {wf.equalizer_cover_compliant ? "Compliant" : "Non-compliant"}
                </Badge>
              ) : (
                <span className="text-muted-foreground/50 italic text-xs">--</span>
              )}
            </div>
            {(wf.equalizer_cover_install_date || wf.equalizer_cover_expiry_date) && (
              <p className="text-[10px] text-muted-foreground pl-2">
                {wf.equalizer_cover_install_date && `Installed: ${formatDate(wf.equalizer_cover_install_date)}`}
                {wf.equalizer_cover_install_date && wf.equalizer_cover_expiry_date && " \u00b7 "}
                {wf.equalizer_cover_expiry_date && `Expires: ${formatDate(wf.equalizer_cover_expiry_date)}`}
              </p>
            )}
          </div>
          <DetailRow label="Plumbing Size" value={wf.plumbing_size_inches != null ? `${wf.plumbing_size_inches} in` : null} />
          <DetailRow label="Turnover" value={wf.turnover_hours != null ? `${wf.turnover_hours} hrs` : null} />
          <DetailRow label="Drains" value={wf.drain_count != null ? `${wf.drain_count} (${wf.drain_type?.replace(/_/g, " ") || "unknown"})` : null} />
          <DetailRow label="Skimmers" value={wf.skimmer_count != null ? String(wf.skimmer_count) : null} />
          <DetailRow label="Cover" value={wf.pool_cover_type} />
          <DetailRow label="Fill Method" value={wf.fill_method} />
        </div>
      </CollapsibleSection>

      {/* Rate & Billing */}
      {perms.canViewRates && (
        <CollapsibleSection icon={DollarSign} title="Rate & Billing">
          <div className="px-3 py-2.5 space-y-1.5 border-b">
            <div className="flex justify-between text-xs py-0.5">
              <span className="text-muted-foreground">Monthly Rate</span>
              {wf.monthly_rate != null ? (
                <span className="font-medium">${wf.monthly_rate.toFixed(2)}/mo</span>
              ) : (
                <span className="text-muted-foreground/50 italic">Not set</span>
              )}
            </div>
            <DetailRow label="Pool Type" value={wf.pool_type} />
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
