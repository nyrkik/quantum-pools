"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertTriangle,
  ClipboardCheck,
  Loader2,
  Wrench,
  FileText,
} from "lucide-react";
import type { InspectionFacilityDetail as InspectionFacilityDetailType, Inspection, InspectionEquipment, FacilityStatus } from "./inspection-types";
import { cleanProgramId, formatDate, getTimelineDotColor, getViolationLabel, hasClosureViolations } from "./inspection-constants";

interface FacilityDetailProps {
  facility: InspectionFacilityDetailType;
  allInspections: Inspection[];
  selectedInspection: Inspection | null;
  selectedEquipment: InspectionEquipment | null;
  facilityStatus: FacilityStatus | null;
  selectedProgramId: string | null;
  detailLoading: boolean;
  onSelectInspection: (id: string) => void;
}

export function FacilityDetail({
  facility,
  allInspections,
  selectedInspection,
  selectedEquipment,
  facilityStatus,
  selectedProgramId,
  detailLoading,
  onSelectInspection,
}: FacilityDetailProps) {
  if (detailLoading) {
    return (
      <div className="lg:col-span-8 min-h-0 overflow-y-auto space-y-3">
        <Card className="shadow-sm">
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="lg:col-span-8 min-h-0 overflow-y-auto space-y-3">
      {/* Facility Header */}
      <Card className="shadow-sm">
        <CardContent className="p-4">
          <div className="flex items-center gap-2.5">
            <h2 className="text-lg font-semibold truncate">
              {facility.matched_customer_name || facility.name}
              {facility.matched_customer_name && facility.matched_customer_name !== facility.name && (
                <span className="font-normal text-muted-foreground"> ({facility.name})</span>
              )}
            </h2>
            {facilityStatus && (
              facilityStatus === "closure" ? (
                <Badge variant="destructive" className="text-xs font-semibold">Closed</Badge>
              ) : (
                <Badge className="text-xs font-semibold bg-green-600 hover:bg-green-700 text-white">Open</Badge>
              )
            )}
          </div>
          {(() => {
            const latestInsp = allInspections[0];
            const rawProgName = latestInsp?.program_identifier || null;
            const cleanName = rawProgName ? cleanProgramId(rawProgName) : null;
            const prId = latestInsp?.permit_id;
            const bowType = cleanName?.toLowerCase() || "pool";
            const userBowName = facility.matched_wf_names?.[bowType];
            const displayName = userBowName || cleanName;
            const emdName = userBowName && rawProgName ? cleanProgramId(rawProgName) : null;
            return displayName ? (
              <p className="text-base font-semibold uppercase mt-1">
                {displayName}
                {(emdName || prId) && (
                  <span className="text-sm text-muted-foreground font-normal normal-case">
                    {" ("}
                    {emdName && <>{emdName}</>}
                    {emdName && prId && " · "}
                    {prId}
                    {")"}
                  </span>
                )}
              </p>
            ) : null;
          })()}
          <p className="text-sm text-muted-foreground mt-0.5">
            {facility.street_address}
            {facility.city ? `, ${facility.city}` : ""}
            {facility.state ? `, ${facility.state}` : ""}
            {facility.zip_code ? ` ${facility.zip_code}` : ""}
          </p>
          {selectedEquipment?.pool_capacity_gallons && (
            <p className="text-sm mt-1">
              <span className="text-lg font-bold">{selectedEquipment.pool_capacity_gallons.toLocaleString()}</span>
              <span className="text-muted-foreground ml-1">gallons</span>
            </p>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 pt-2 border-t text-xs text-muted-foreground">
            {facility.facility_id && (
              <span>Facility <span className="font-medium text-foreground">{facility.facility_id}</span></span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Inspections list */}
      <Card className="shadow-sm">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <ClipboardCheck className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Inspections</span>
            <div className="flex-1 border-t border-border ml-1" />
            <span className="text-[11px] text-muted-foreground/50">{allInspections.length}</span>
          </div>
          {allInspections.length === 0 ? (
            <p className="text-center py-4 text-muted-foreground text-sm">No inspection records</p>
          ) : (
            <div className="space-y-0.5">
              {allInspections.map((insp) => {
                const isActive = selectedInspection?.id === insp.id;
                return (
                  <button
                    key={insp.id}
                    onClick={() => onSelectInspection(insp.id)}
                    className={`w-full text-left flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
                      isActive ? "bg-accent font-medium" : "hover:bg-muted"
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={`w-2 h-2 rounded-full shrink-0 ${getTimelineDotColor(insp)}`} />
                      <span>{formatDate(insp.inspection_date)}</span>
                      {insp.program_identifier && (
                        <span className="text-[10px] text-muted-foreground">{cleanProgramId(insp.program_identifier)}</span>
                      )}
                      <span className="text-xs text-muted-foreground">{insp.inspection_type || "Inspection"}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {hasClosureViolations(insp) && (
                        <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Closure</Badge>
                      )}
                      {insp.total_violations > 0 && (
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{insp.total_violations} viol</Badge>
                      )}
                      {insp.has_pdf && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          title="View PDF"
                          onClick={(e) => {
                            e.stopPropagation();
                            window.open(`/api/v1/inspections/inspections/${insp.id}/pdf`, "_blank");
                          }}
                        >
                          <FileText className="h-3 w-3 text-blue-500" />
                        </Button>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Selected inspection detail */}
      {selectedInspection && (
        <InspectionDetailCard
          inspection={selectedInspection}
          facility={facility}
          equipment={selectedEquipment}
        />
      )}
    </div>
  );
}

function InspectionDetailCard({
  inspection,
  facility,
  equipment,
}: {
  inspection: Inspection;
  facility: InspectionFacilityDetailType;
  equipment: InspectionEquipment | null;
}) {
  return (
    <Card className="shadow-sm">
      <CardContent className="p-0">
        {/* Header bar */}
        <div className="bg-slate-100 dark:bg-slate-800 px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <p className="text-sm font-semibold">{formatDate(inspection.inspection_date)}</p>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">{inspection.inspection_type || "Inspection"}</Badge>
            {inspection.has_pdf && (
              <Button variant="ghost" size="icon" className="h-6 w-6" title="View PDF"
                onClick={() => window.open(`/api/v1/inspections/inspections/${inspection.id}/pdf`, "_blank")}>
                <FileText className="h-3.5 w-3.5 text-blue-500" />
              </Button>
            )}
          </div>
          <div className="flex items-center text-xs text-muted-foreground">
            {inspection.inspector_name && (
              <span>Inspector <span className="font-medium text-foreground">{inspection.inspector_name}</span></span>
            )}
            {inspection.inspector_name && facility.permit_holder && (
              <span className="mx-2">·</span>
            )}
            {facility.permit_holder && (
              <span>Permit Holder <span className="font-medium text-foreground">{facility.permit_holder}</span></span>
            )}
            {facility.phone && (
              <span className="ml-3"><span className="font-medium text-foreground">{facility.phone}</span></span>
            )}
          </div>
        </div>

        {/* Chemistry + gauges */}
        <div className="px-4 py-3 border-b">
          <div className="grid grid-cols-4 sm:grid-cols-7 gap-1.5">
            {[
              { label: "FC", value: inspection.water_chemistry?.free_chlorine ?? null, bad: (v: number) => v < 1 || v > 10 },
              { label: "CC", value: inspection.water_chemistry?.combined_chlorine ?? null, bad: (v: number) => v > 0.5 },
              { label: "pH", value: inspection.water_chemistry?.ph ?? null, bad: (v: number) => v < 7.2 || v > 7.8 },
              { label: "CYA", value: inspection.water_chemistry?.cyanuric_acid_ppm ?? null, bad: (v: number) => v > 100 },
              { label: "Flow", value: inspection.flow_rate_gpm ?? null, bad: () => false },
              { label: "Press", value: null, bad: () => false },
              { label: "Temp", value: null, bad: () => false },
            ].map((m) => (
              <div key={m.label} className="bg-muted/50 rounded px-1.5 py-1 text-center">
                <p className="text-[8px] font-medium uppercase tracking-wide text-muted-foreground">{m.label}</p>
                <p className={`text-sm font-bold leading-tight ${m.value != null && m.bad(m.value) ? "text-red-600" : ""}`}>
                  {m.value != null ? m.value : <span className="text-muted-foreground/30">--</span>}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Equipment */}
        <div className="px-4 py-3 border-b">
          <div className="flex items-center gap-2 mb-2.5">
            <Wrench className="h-3 w-3 text-muted-foreground" />
            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Equipment</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Pump", value: equipment ? [equipment.filter_pump_1_make, equipment.filter_pump_1_model, equipment.filter_pump_1_hp ? `${equipment.filter_pump_1_hp}hp` : null].filter(Boolean).join(" ") : null, sub: null },
              { label: "Filter", value: equipment ? [equipment.filter_1_type, equipment.filter_1_make, equipment.filter_1_model].filter(Boolean).join(" ") : null, sub: null },
              { label: "Sanitizer", value: equipment ? [equipment.sanitizer_1_type, equipment.sanitizer_1_details].filter(Boolean).join(" · ") : null, sub: null },
              { label: "Main Drain", value: equipment?.main_drain_model || null, sub: equipment?.main_drain_install_date ? `Installed ${equipment.main_drain_install_date}` : null },
              { label: "Equalizer", value: equipment?.equalizer_model || null, sub: equipment?.equalizer_install_date ? `Installed ${equipment.equalizer_install_date}` : null },
            ].map((r) => (
              <div key={r.label} className="bg-muted/50 rounded-md px-3 py-2">
                <p className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">{r.label}</p>
                <p className="text-sm font-medium leading-snug mt-0.5">
                  {r.value || <span className="text-muted-foreground/30">--</span>}
                </p>
                {r.sub && (
                  <p className="text-[10px] text-muted-foreground mt-0.5">{r.sub}</p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Violations */}
        {inspection.violations && inspection.violations.length > 0 && (
          <div className="px-4 py-3 border-b">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-3 w-3 text-muted-foreground" />
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Violations</p>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-1">{inspection.violations.length}</Badge>
            </div>
            <div className="space-y-1.5">
              {inspection.violations.map((v) => {
                const isClosure = v.observations && /MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE/i.test(v.observations);
                const isMajor = v.is_major_violation || (v.observations && /^-?\s*MAJOR/i.test(v.observations));
                return (
                  <div
                    key={v.id}
                    className={`rounded-md px-3 py-2 text-sm ${
                      isClosure
                        ? "bg-red-50 dark:bg-red-950/30 border-l-3 border-red-500"
                        : isMajor
                          ? "bg-amber-50 dark:bg-amber-950/20 border-l-3 border-amber-400"
                          : "bg-muted/40"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {v.violation_code && (
                        <span className="text-xs font-mono text-muted-foreground bg-background rounded px-1 py-0.5 shrink-0">{v.violation_code}</span>
                      )}
                      <span className="font-medium text-sm flex-1">{getViolationLabel(v.violation_code, v.violation_title)}</span>
                      {isClosure && <Badge variant="destructive" className="text-[9px] px-1 py-0 shrink-0">CLOSURE</Badge>}
                      {isMajor && !isClosure && <Badge variant="outline" className="text-[9px] px-1 py-0 border-amber-400 text-amber-600 shrink-0">MAJOR</Badge>}
                    </div>
                    {v.observations && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-3 leading-relaxed">{v.observations}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Notes */}
        {inspection.report_notes && (
          <div className="px-4 py-3">
            <div className="flex items-center gap-2 mb-1.5">
              <FileText className="h-3 w-3 text-muted-foreground" />
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Notes</p>
            </div>
            <p className="text-xs text-muted-foreground whitespace-pre-line leading-relaxed">{inspection.report_notes}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
