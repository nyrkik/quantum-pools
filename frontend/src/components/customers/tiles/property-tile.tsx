"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { MapPin, Copy, ChevronDown, Search, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Property, WaterFeatureSummary } from "../customer-types";

interface PropertyTileProps {
  properties: Property[];
  preferredDay: string | null;
}

export function PropertyTile({ properties, preferredDay }: PropertyTileProps) {
  if (properties.length === 0) return null;

  return (
    <div className="space-y-3">
      {properties.map((prop) => (
        <PropertyCard key={prop.id} property={prop} preferredDay={preferredDay} />
      ))}
    </div>
  );
}

interface InspectionInfo {
  id: string;
  inspection_date: string | null;
  total_violations: number;
  closure_required: boolean;
}

function PropertyCard({ property, preferredDay }: { property: Property; preferredDay: string | null }) {
  const [expandedWfId, setExpandedWfId] = useState<string | null>(null);
  const [inspections, setInspections] = useState<InspectionInfo[]>([]);

  useEffect(() => {
    api.get<InspectionInfo[]>(`/v1/emd/property/${property.id}/inspections`)
      .then(data => setInspections((data || []).slice(0, 3)))
      .catch(() => {});
  }, [property.id]);

  const copyGate = () => {
    if (!property.gate_code) return;
    navigator.clipboard.writeText(property.gate_code);
    toast.success("Gate code copied");
  };

  const days = property.service_day_pattern || preferredDay;
  const wfs = property.water_features || [];

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <span className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-muted-foreground" />
            {property.name || property.address}
          </span>
          {property.dog_on_property && (
            <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px]">Dog</Badge>
          )}
        </CardTitle>
        {property.name && (
          <p className="text-xs text-muted-foreground ml-6">{property.address}, {property.city}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Access + schedule */}
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {property.gate_code && (
            <button onClick={copyGate} className="flex items-center gap-1.5 hover:text-primary transition-colors" title="Copy gate code">
              <span className="text-xs text-muted-foreground">Gate:</span>
              <span className="font-bold text-base">{property.gate_code}</span>
              <Copy className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
          {days && (
            <div className="flex gap-1">
              {days.split(",").map((d) => (
                <Badge key={d.trim()} variant="secondary" className="text-[10px] px-1.5">{d.trim()}</Badge>
              ))}
            </div>
          )}
        </div>

        {property.access_instructions && (
          <p className="text-xs text-muted-foreground">{property.access_instructions}</p>
        )}

        {/* Inspections (property-level, above pools) */}
        {inspections.length > 0 && (
          <div className="space-y-1 pt-1 border-t">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium flex items-center gap-1.5">
              <ShieldCheck className="h-3 w-3" /> Inspections
            </p>
            {inspections.map(insp => {
              const passed = insp.total_violations === 0 && !insp.closure_required;
              const dateStr = insp.inspection_date
                ? new Date(insp.inspection_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                : "No date";
              return (
                <div key={insp.id} className="flex items-center justify-between text-xs py-0.5">
                  <span className="text-muted-foreground">{dateStr}</span>
                  {passed ? (
                    <Badge variant="default" className="bg-green-600 text-[10px] px-1.5">Pass</Badge>
                  ) : (
                    <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px] px-1.5">
                      {insp.total_violations} violations
                    </Badge>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Pools / Water features — nested children */}
        {wfs.length > 0 && (
          <div className="pt-2 border-t space-y-1">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">
              {wfs.length === 1 ? "Pool" : `Pools (${wfs.length})`}
            </p>
            <div className="border-l-2 border-muted ml-1 pl-3 space-y-0.5">
              {wfs.map((wf) => (
                <WfRow
                  key={wf.id}
                  wf={wf}
                  expanded={expandedWfId === wf.id}
                  onToggle={() => setExpandedWfId(expandedWfId === wf.id ? null : wf.id)}
                />
              ))}
            </div>
          </div>
        )}

      </CardContent>
    </Card>
  );
}

function WfRow({ wf, expanded, onToggle }: { wf: WaterFeatureSummary; expanded: boolean; onToggle: () => void }) {
  return (
    <div>
      <div
        className="flex items-center justify-between py-2 cursor-pointer hover:bg-muted/50 -mx-2 px-2 rounded transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium truncate">{wf.name || wf.water_type}</span>
          {wf.pool_gallons && (
            <span className="text-xs text-muted-foreground shrink-0">{wf.pool_gallons.toLocaleString()} gal</span>
          )}
          {wf.sanitizer_type && (
            <Badge variant="outline" className="text-[10px] px-1.5 shrink-0">{wf.sanitizer_type}</Badge>
          )}
        </div>
        <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform shrink-0 ${expanded ? "rotate-180" : ""}`} />
      </div>

      {expanded && (
        <div className="ml-4 pb-2 space-y-2.5">
          {/* Equipment */}
          {[
            { label: "Pump", value: wf.pump_type },
            { label: "Filter", value: wf.filter_type },
            { label: "Heater", value: wf.heater_type },
            { label: "Chlorinator", value: wf.chlorinator_type },
            { label: "Automation", value: wf.automation_system },
          ].filter(e => e.value).length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Equipment</p>
              {[
                { label: "Pump", value: wf.pump_type },
                { label: "Filter", value: wf.filter_type },
                { label: "Heater", value: wf.heater_type },
                { label: "Chlorinator", value: wf.chlorinator_type },
                { label: "Automation", value: wf.automation_system },
              ].filter(e => e.value).map((eq) => (
                <div key={eq.label} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{eq.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">{eq.value}</span>
                    <a
                      href={`https://www.google.com/search?q=${encodeURIComponent(eq.value + " pool parts")}`}
                      target="_blank" rel="noopener noreferrer"
                      className="text-muted-foreground hover:text-primary"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Search className="h-3 w-3" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Pool specs */}
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
    </div>
  );
}
