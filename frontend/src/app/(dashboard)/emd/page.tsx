"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Shield,
  Search,
  Building2,
  AlertTriangle,
  ClipboardCheck,
  Link2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Wrench,
  X,
  Users,
  Ban,
  Target,
} from "lucide-react";
import Link from "next/link";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const VIOLATION_LABELS: Record<string, string> = {
  "1a": "Gate Self-Close/Latch",
  "1b": "Gate Hardware",
  "1c": "Emergency Exit Gate",
  "2a": "Pool Enclosure",
  "2b": "Non-Climbable Enclosure",
  "3": "Safety Signs",
  "4": "Safety Equipment",
  "5": "Restrooms/Showers",
  "6": "Hose Bibb Anti-Siphon",
  "7": "Pool Deck",
  "8": "Pool/Deck Lighting",
  "9": "Ladders/Handrails",
  "10a": "Low Chlorine",
  "10b": "High Chlorine",
  "12a": "Low pH",
  "12b": "High pH",
  "13": "High CYA",
  "14": "Test Kit",
  "15": "Records",
  "16": "Water Clarity",
  "17": "Cleanliness",
  "18": "Pool Shell/Tile",
  "19": "Depth Markers",
  "20": "Depth Line",
  "21": "Water Level",
  "22": "Skimmer Assembly",
  "23": "Inlets/Outlets",
  "24": "VGB Suction Covers",
  "25": "Spa Emergency Switch",
  "26": "Spa Temperature",
  "27": "Equipment Room",
  "28": "Safety Vacuum Release",
  "29": "Recirculation System",
  "30": "Equipment/Plumbing",
  "31": "Disinfectant Feeders",
  "32": "Chemical Control System",
  "33": "Turnover Time",
  "34": "Flow Rate",
  "35": "Flow Meters",
  "36": "Pressure/Vacuum Gauges",
  "37": "Electrical Hazards",
  "38": "Filter Maintenance",
  "39": "Wastewater Disposal",
  "43": "EMD Approval Required",
  "44": "Lifeguard Certification",
  "46": "Other",
};

function getViolationLabel(code: string | null, title: string | null): string {
  if (code) {
    const clean = code.replace(/\.$/, "").trim().toLowerCase();
    if (VIOLATION_LABELS[clean]) return VIOLATION_LABELS[clean];
  }
  return title || "Violation";
}

interface EMDFacilityListItem {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  facility_id: string | null;
  facility_type: string | null;
  matched_property_id: string | null;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  is_closed: boolean;
  closure_reasons: string[];
}

interface EMDInspection {
  id: string;
  facility_id: string;
  inspection_id: string | null;
  inspection_date: string | null;
  inspection_type: string | null;
  inspector_name: string | null;
  total_violations: number;
  major_violations: number;
  pool_capacity_gallons: number | null;
  flow_rate_gpm: number | null;
  pdf_path: string | null;
  report_notes: string | null;
  closure_status: string | null;
  closure_required: boolean;
  reinspection_required: boolean;
  water_chemistry: { free_chlorine?: number; combined_chlorine?: number; ph?: number; cyanuric_acid_ppm?: number } | null;
  created_at: string;
  violations?: EMDViolation[];
}

interface EMDViolation {
  id: string;
  violation_code: string | null;
  violation_title: string | null;
  observations: string | null;
  is_major_violation: boolean;
  severity_level: string | null;
  shorthand_summary: string | null;
}

interface EMDEquipment {
  id: string;
  pool_capacity_gallons: number | null;
  flow_rate_gpm: number | null;
  filter_pump_1_make: string | null;
  filter_pump_1_model: string | null;
  filter_pump_1_hp: string | null;
  filter_pump_2_make: string | null;
  filter_pump_2_model: string | null;
  filter_pump_2_hp: string | null;
  filter_pump_3_make: string | null;
  filter_pump_3_model: string | null;
  filter_pump_3_hp: string | null;
  jet_pump_1_make: string | null;
  jet_pump_1_model: string | null;
  jet_pump_1_hp: string | null;
  filter_1_type: string | null;
  filter_1_make: string | null;
  filter_1_model: string | null;
  filter_1_capacity_gpm: number | null;
  sanitizer_1_type: string | null;
  sanitizer_1_details: string | null;
  sanitizer_2_type: string | null;
  sanitizer_2_details: string | null;
  main_drain_type: string | null;
  main_drain_model: string | null;
  main_drain_install_date: string | null;
  equalizer_model: string | null;
  equalizer_install_date: string | null;
  pump_notes: string | null;
  filter_notes: string | null;
  sanitizer_notes: string | null;
  main_drain_notes: string | null;
  equalizer_notes: string | null;
}

interface EMDFacilityDetail {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  state: string;
  zip_code: string | null;
  phone: string | null;
  facility_id: string | null;
  permit_holder: string | null;
  facility_type: string | null;
  matched_property_id: string | null;
  matched_at: string | null;
  inspections: EMDInspection[];
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  matched_property_address: string | null;
  matched_customer_name: string | null;
  matched_customer_id?: string | null;
}

type FacilityStatus = "compliant" | "violations" | "reinspection" | "closure";

function getFacilityStatus(inspections: EMDInspection[]): FacilityStatus {
  if (inspections.length === 0) return "compliant";
  const latest = inspections[0];
  if (latest.closure_required) return "closure";
  if (latest.reinspection_required) return "reinspection";
  if (latest.total_violations > 0) return "violations";
  return "compliant";
}

function getListItemStatus(f: EMDFacilityListItem): "green" | "amber" | "red" {
  // Heuristic from list data: high violations = red, some = amber, none = green
  if (f.total_violations > 10) return "red";
  if (f.total_violations > 0) return "amber";
  return "green";
}

function getStatusDotColor(status: "green" | "amber" | "red") {
  if (status === "red") return "bg-red-500";
  if (status === "amber") return "bg-amber-500";
  return "bg-green-500";
}

function StatusBadge({ status, violationCount }: { status: FacilityStatus; violationCount?: number }) {
  switch (status) {
    case "closure":
      return <Badge variant="destructive" className="text-xs font-semibold">CLOSURE REQUIRED</Badge>;
    case "reinspection":
      return <Badge variant="outline" className="text-xs font-semibold border-amber-400 text-amber-600">REINSPECTION NEEDED</Badge>;
    case "violations":
      return <Badge variant="outline" className="text-xs font-semibold border-amber-400 text-amber-600">VIOLATIONS {violationCount ? `(${violationCount})` : ""}</Badge>;
    case "compliant":
      return <Badge className="text-xs font-semibold bg-green-600 hover:bg-green-700 text-white">COMPLIANT</Badge>;
  }
}

function getTimelineDotColor(insp: EMDInspection): string {
  if (insp.closure_required) return "bg-red-500";
  if (insp.major_violations > 0) return "bg-red-500";
  if (insp.total_violations > 0) return "bg-amber-500";
  return "bg-green-500";
}

export default function EMDPage() {
  const [facilities, setFacilities] = useState<EMDFacilityListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedFacility, setSelectedFacility] = useState<EMDFacilityDetail | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<EMDEquipment | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedInspection, setExpandedInspection] = useState<string | null>(null);
  const [showMine, setShowMine] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | "violations" | "high_risk" | "clean">("all");
  const [matchFilter, setMatchFilter] = useState<"all" | "matched" | "unmatched">("all");
  const [backfillStatus, setBackfillStatus] = useState<{
    state?: string;
    current_date?: string;
    newest_date?: string;
    oldest_date?: string;
    days_completed?: number;
    total_found?: number;
    total_new?: number;
    total_pdfs?: number;
  } | null>(null);

  // Poll backfill status every 30s
  useEffect(() => {
    const fetchStatus = () => {
      api.get<Record<string, unknown>>("/v1/emd/backfill-status")
        .then((d) => setBackfillStatus(d as typeof backfillStatus))
        .catch(() => setBackfillStatus(null));
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchFacilities = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      params.set("limit", "5000");
      const data = await api.get<EMDFacilityListItem[]>(
        `/v1/emd/facilities?${params.toString()}`
      );
      setFacilities(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const timer = setTimeout(fetchFacilities, 300);
    return () => clearTimeout(timer);
  }, [fetchFacilities]);

  const selectFacility = async (id: string) => {
    setDetailLoading(true);
    setSelectedEquipment(null);
    try {
      const [detail, equipment] = await Promise.all([
        api.get<EMDFacilityDetail>(`/v1/emd/facilities/${id}`),
        api.get<EMDEquipment | null>(`/v1/emd/facilities/${id}/equipment`),
      ]);
      setSelectedFacility(detail);
      setSelectedEquipment(equipment);
      setExpandedInspection(null);
    } catch {
      // ignore
    } finally {
      setDetailLoading(false);
    }
  };

  const formatDate = (d: string | null) => {
    if (!d) return "--";
    return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  // Computed summary metrics
  const summaryMetrics = useMemo(() => {
    const now = new Date();
    const oneYearAgo = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());

    // These are approximations from list data
    const totalFacilities = facilities.length;
    const withViolations = facilities.filter(f => f.total_violations > 0).length;
    const highViolation = facilities.filter(f => f.total_violations > 10).length;
    const potentialLeads = facilities.filter(f => f.total_violations >= 3 && !f.matched_property_id).length;

    return {
      totalFacilities,
      activeViolations: withViolations,
      closuresRequired: highViolation,
      potentialLeads,
    };
  }, [facilities]);

  const facilityStatus = selectedFacility ? getFacilityStatus(selectedFacility.inspections) : null;

  const filteredFacilities = useMemo(() => {
    return facilities.filter((f) => {
      if (showMine && !f.matched_property_id) return false;
      if (matchFilter === "matched" && !f.matched_property_id) return false;
      if (matchFilter === "unmatched" && f.matched_property_id) return false;
      if (statusFilter === "violations" && f.total_violations === 0) return false;
      if (statusFilter === "high_risk" && f.total_violations <= 10) return false;
      if (statusFilter === "clean" && f.total_violations > 0) return false;
      return true;
    });
  }, [facilities, showMine, statusFilter, matchFilter]);

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col gap-3 overflow-hidden">
      {/* Summary Dashboard — 4 metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 shrink-0">
        {/* Total Facilities — with backfill status */}
        <Card className="shadow-sm">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Total Facilities</p>
                <p className="text-2xl font-bold leading-tight mt-0.5 text-primary">{summaryMetrics.totalFacilities}</p>
              </div>
              <div className="text-right">
                {backfillStatus?.state === "running" ? (
                  <div className="space-y-0.5 text-right">
                    <div className="flex items-center gap-1 justify-end">
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                      <span className="text-[10px] text-green-600 font-medium">Scraping</span>
                    </div>
                    {backfillStatus.oldest_date && backfillStatus.newest_date && (
                      <p className="text-[10px] text-muted-foreground">
                        {new Date(backfillStatus.oldest_date + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
                        {" — "}
                        {new Date(backfillStatus.newest_date + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
                      </p>
                    )}
                    <p className="text-[10px] text-muted-foreground">
                      {backfillStatus.total_new ? `${backfillStatus.total_new} new` : ""}
                      {backfillStatus.total_new && backfillStatus.total_pdfs ? " · " : ""}
                      {backfillStatus.total_pdfs ? `${backfillStatus.total_pdfs} PDFs` : ""}
                      {!backfillStatus.total_new && !backfillStatus.total_pdfs ? "Scanning..." : ""}
                    </p>
                  </div>
                ) : backfillStatus?.state === "stopped" && backfillStatus.days_completed ? (
                  <div className="space-y-0.5 text-right">
                    <span className="text-[10px] text-muted-foreground">Paused</span>
                    {backfillStatus.oldest_date && backfillStatus.newest_date && (
                      <p className="text-[10px] text-muted-foreground">
                        {new Date(backfillStatus.oldest_date + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
                        {" — "}
                        {new Date(backfillStatus.newest_date + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
                      </p>
                    )}
                  </div>
                ) : (
                  <Building2 className="h-5 w-5 text-primary opacity-40" />
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Other metric cards */}
        {[
          { label: "With Violations", value: summaryMetrics.activeViolations, Icon: AlertTriangle, color: "text-amber-600" },
          { label: "High Risk", value: summaryMetrics.closuresRequired, Icon: Ban, color: "text-red-600" },
          { label: "Potential Leads", value: summaryMetrics.potentialLeads, Icon: Target, color: "text-green-600" },
        ].map((m) => (
          <Card key={m.label} className="shadow-sm">
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{m.label}</p>
                  <p className={`text-2xl font-bold leading-tight mt-0.5 ${m.color}`}>{m.value}</p>
                </div>
                <m.Icon className={`h-5 w-5 ${m.color} opacity-40`} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Main content: list + detail */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0">
        {/* Left: Facility list */}
        <div className={`${selectedFacility ? "lg:col-span-4" : "lg:col-span-12"} min-h-0 flex flex-col`}>
          <Card className="shadow-sm flex-1 flex flex-col min-h-0">
            {/* Search + filters */}
            <div className="p-3 pb-0 shrink-0 space-y-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search facilities..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <Button
                  variant={showMine ? "default" : "outline"}
                  size="sm"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => setShowMine(!showMine)}
                >
                  <Link2 className="h-3 w-3 mr-1" />
                  Mine
                </Button>
                <span className="w-px h-4 bg-border" />
                {([
                  { value: "all" as const, label: "All" },
                  { value: "violations" as const, label: "Violations" },
                  { value: "high_risk" as const, label: "High Risk" },
                  { value: "clean" as const, label: "Clean" },
                ] as const).map((f) => (
                  <Button
                    key={f.value}
                    variant={statusFilter === f.value ? "default" : "outline"}
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => setStatusFilter(f.value)}
                  >
                    {f.label}
                  </Button>
                ))}
                <span className="w-px h-4 bg-border" />
                {([
                  { value: "all" as const, label: "All" },
                  { value: "matched" as const, label: "Matched" },
                  { value: "unmatched" as const, label: "Unmatched" },
                ] as const).map((f) => (
                  <Button
                    key={f.value}
                    variant={matchFilter === f.value ? "default" : "outline"}
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => setMatchFilter(f.value)}
                  >
                    {f.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* Facility list — table-like layout */}
            <div className="flex-1 flex flex-col min-h-0">
              {/* Column headers */}
              <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 items-center bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground shrink-0 sticky top-0 z-10">
                <span>Facility</span>
                <span className="w-12 text-center">Viol</span>
                <span className="w-20 text-center">Last Insp</span>
                <span className="w-16 text-center">Status</span>
              </div>

              <div className="flex-1 overflow-y-auto min-h-0">
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : filteredFacilities.length === 0 ? (
                  <div className="text-center py-8 text-sm text-muted-foreground">No facilities found</div>
                ) : (
                  <TooltipProvider delayDuration={200}>
                    {filteredFacilities.map((f) => {
                      const isSelected = selectedFacility?.id === f.id;
                      const status = getListItemStatus(f);
                      return (
                        <button
                          key={f.id}
                          onClick={() => selectFacility(f.id)}
                          className={`w-full text-left grid grid-cols-[1fr_auto_auto_auto] gap-x-2 items-center px-3 py-2 text-sm transition-colors border-b border-border/40 ${
                            isSelected
                              ? "bg-accent border-l-3 border-l-primary font-medium"
                              : "hover:bg-blue-50 dark:hover:bg-blue-950"
                          }`}
                        >
                          {/* Facility name + address */}
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${getStatusDotColor(status)}`} />
                              <span className="font-medium truncate">{f.name}</span>
                              {f.matched_property_id && (
                                <Link2 className="h-3 w-3 text-green-500 shrink-0" />
                              )}
                            </div>
                            <div className="text-xs truncate ml-4 text-muted-foreground">
                              {f.street_address}{f.city ? `, ${f.city}` : ""}
                            </div>
                          </div>

                          {/* Violation count */}
                          <div className="w-12 text-center">
                            {f.total_violations > 0 ? (
                              <Badge
                                variant={f.total_violations > 10 ? "destructive" : "secondary"}
                                className="text-[10px] px-1.5 py-0"
                              >
                                {f.total_violations}
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground/40">0</span>
                            )}
                          </div>

                          {/* Last inspection date */}
                          <div className="w-20 text-center">
                            <span className="text-[11px] text-muted-foreground">
                              {f.last_inspection_date ? formatDate(f.last_inspection_date) : "--"}
                            </span>
                          </div>

                          {/* Status: OPEN / CLOSED */}
                          <div className="w-16 text-center">
                            {f.is_closed ? (
                              f.closure_reasons.length > 0 ? (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span>
                                      <Badge variant="destructive" className="text-[10px] px-1.5 py-0 cursor-help">
                                        CLOSED
                                      </Badge>
                                    </span>
                                  </TooltipTrigger>
                                  <TooltipContent side="left" className="max-w-xs">
                                    <ul className="text-xs space-y-0.5">
                                      {f.closure_reasons.map((r, i) => (
                                        <li key={i}>{r}</li>
                                      ))}
                                    </ul>
                                  </TooltipContent>
                                </Tooltip>
                              ) : (
                                <Badge variant="destructive" className="text-[10px] px-1.5 py-0">
                                  CLOSED
                                </Badge>
                              )
                            ) : (
                              <span className="text-[10px] font-semibold text-green-600">OPEN</span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </TooltipProvider>
                )}
              </div>
            </div>

            {/* Footer count */}
            <div className="text-[11px] text-muted-foreground px-3 py-1.5 border-t shrink-0">
              {filteredFacilities.length} of {facilities.length} facilities
            </div>
          </Card>
        </div>

        {/* Right: Detail panel */}
        {selectedFacility && (
          <div className="lg:col-span-8 min-h-0 overflow-y-auto space-y-3">
            {detailLoading ? (
              <Card className="shadow-sm">
                <CardContent className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </CardContent>
              </Card>
            ) : (
              <>
                {/* Facility Header */}
                <Card className="shadow-sm">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <h2 className="text-lg font-semibold truncate">{selectedFacility.name}</h2>
                          {facilityStatus && (
                            <StatusBadge
                              status={facilityStatus}
                              violationCount={selectedFacility.inspections[0]?.total_violations}
                            />
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground mt-0.5">
                          {selectedFacility.street_address}
                          {selectedFacility.city ? `, ${selectedFacility.city}` : ""}
                          {selectedFacility.state ? `, ${selectedFacility.state}` : ""}
                          {selectedFacility.zip_code ? ` ${selectedFacility.zip_code}` : ""}
                        </p>

                        {/* Info row */}
                        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-muted-foreground">
                          {selectedFacility.facility_id && (
                            <span>Permit <span className="font-medium text-foreground">{selectedFacility.facility_id}</span></span>
                          )}
                          {selectedFacility.facility_type && (
                            <span>Type <span className="font-medium text-foreground">{selectedFacility.facility_type}</span></span>
                          )}
                          {selectedFacility.permit_holder && (
                            <span>Holder <span className="font-medium text-foreground">{selectedFacility.permit_holder}</span></span>
                          )}
                          {selectedFacility.phone && (
                            <span>Phone <span className="font-medium text-foreground">{selectedFacility.phone}</span></span>
                          )}
                        </div>

                        {/* Match status */}
                        <div className="flex items-center gap-2 mt-2.5 pt-2.5 border-t">
                          {selectedFacility.matched_property_id ? (
                            <>
                              <Link2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                              <span className="text-xs">
                                Matched to{" "}
                                {selectedFacility.matched_customer_id ? (
                                  <Link href={`/customers/${selectedFacility.matched_customer_id}`} className="font-medium hover:underline text-primary">
                                    {selectedFacility.matched_customer_name}
                                  </Link>
                                ) : (
                                  <span className="font-medium">{selectedFacility.matched_customer_name}</span>
                                )}
                                {selectedFacility.matched_property_address && (
                                  <span className="text-muted-foreground"> -- {selectedFacility.matched_property_address}</span>
                                )}
                              </span>
                            </>
                          ) : (
                            <>
                              <Link2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                              <span className="text-xs text-muted-foreground">Unmatched</span>
                            </>
                          )}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="shrink-0"
                        onClick={() => setSelectedFacility(null)}
                      >
                        <X className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Stats row — 3 metric tiles */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "Inspections", value: String(selectedFacility.total_inspections), color: "" },
                    { label: "Total Violations", value: String(selectedFacility.total_violations), color: selectedFacility.total_violations > 10 ? "text-red-600" : selectedFacility.total_violations > 0 ? "text-amber-600" : "" },
                    { label: "Last Inspected", value: formatDate(selectedFacility.last_inspection_date), color: "" },
                  ].map((s) => (
                    <div key={s.label} className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{s.label}</p>
                      <p className={`text-xl font-bold leading-tight mt-0.5 ${s.color}`}>{s.value}</p>
                    </div>
                  ))}
                </div>

                {/* Equipment */}
                {selectedEquipment && (
                  <Card className="shadow-sm">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Equipment</span>
                        <div className="flex-1 border-t border-border ml-1" />
                      </div>

                      {/* Pool specs — headline numbers */}
                      <div className="grid grid-cols-3 gap-2 mb-3">
                        {[
                          { label: "Capacity", value: selectedEquipment.pool_capacity_gallons ? `${selectedEquipment.pool_capacity_gallons.toLocaleString()}` : null, unit: "gal" },
                          { label: "Flow Rate", value: selectedEquipment.flow_rate_gpm ? `${selectedEquipment.flow_rate_gpm}` : null, unit: "GPM" },
                          { label: "Filter Cap", value: selectedEquipment.filter_1_capacity_gpm ? `${selectedEquipment.filter_1_capacity_gpm}` : null, unit: "GPM" },
                        ].map((s) => (
                          <div key={s.label} className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
                            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{s.label}</p>
                            {s.value ? (
                              <p className="text-lg font-bold leading-tight">{s.value}<span className="text-xs font-normal text-muted-foreground ml-0.5">{s.unit}</span></p>
                            ) : (
                              <p className="text-sm text-muted-foreground/40">--</p>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Equipment grid */}
                      <div className="grid grid-cols-2 gap-2">
                        {/* Pumps tile */}
                        {(() => {
                          const pumps = [
                            { label: "Filter 1", make: selectedEquipment.filter_pump_1_make, model: selectedEquipment.filter_pump_1_model, hp: selectedEquipment.filter_pump_1_hp },
                            { label: "Filter 2", make: selectedEquipment.filter_pump_2_make, model: selectedEquipment.filter_pump_2_model, hp: selectedEquipment.filter_pump_2_hp },
                            { label: "Filter 3", make: selectedEquipment.filter_pump_3_make, model: selectedEquipment.filter_pump_3_model, hp: selectedEquipment.filter_pump_3_hp },
                            { label: "Jet", make: selectedEquipment.jet_pump_1_make, model: selectedEquipment.jet_pump_1_model, hp: selectedEquipment.jet_pump_1_hp },
                          ].filter(p => p.make);
                          if (pumps.length === 0) return null;
                          return (
                            <div className="bg-muted/50 rounded-md overflow-hidden">
                              <div className="bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Pumps</span>
                              </div>
                              <div className="px-3 py-2.5 space-y-2">
                                {pumps.map((p) => (
                                  <div key={p.label}>
                                    <span className="text-[10px] text-muted-foreground uppercase">{p.label}</span>
                                    <p className="text-sm font-medium leading-tight">{p.make} {p.model || ""}{p.hp ? ` \u00b7 ${p.hp}HP` : ""}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })()}

                        {/* Filter + Sanitizer tile */}
                        <div className="bg-muted/50 rounded-md overflow-hidden">
                          <div className="bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                            <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Filter & Sanitizer</span>
                          </div>
                          <div className="px-3 py-2.5 space-y-2">
                            {(selectedEquipment.filter_1_type || selectedEquipment.filter_1_make) && (
                              <div>
                                <span className="text-[10px] text-muted-foreground uppercase">Filter</span>
                                <p className="text-sm font-medium leading-tight">{[selectedEquipment.filter_1_type, selectedEquipment.filter_1_make, selectedEquipment.filter_1_model].filter(Boolean).join(" ")}</p>
                              </div>
                            )}
                            {selectedEquipment.sanitizer_1_type && (
                              <div>
                                <span className="text-[10px] text-muted-foreground uppercase">Sanitizer</span>
                                <p className="text-sm font-medium leading-tight">{selectedEquipment.sanitizer_1_type}{selectedEquipment.sanitizer_1_details ? ` \u00b7 ${selectedEquipment.sanitizer_1_details}` : ""}</p>
                              </div>
                            )}
                            {selectedEquipment.sanitizer_2_type && (
                              <div>
                                <span className="text-[10px] text-muted-foreground uppercase">Secondary</span>
                                <p className="text-sm font-medium leading-tight">{selectedEquipment.sanitizer_2_type}{selectedEquipment.sanitizer_2_details ? ` \u00b7 ${selectedEquipment.sanitizer_2_details}` : ""}</p>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Drain Covers tile */}
                        {(selectedEquipment.main_drain_install_date || selectedEquipment.equalizer_install_date) && (
                          <div className="col-span-2 bg-muted/50 rounded-md overflow-hidden">
                            <div className="bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                              <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Drain Covers</span>
                            </div>
                            <div className="px-3 py-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5">
                              {selectedEquipment.main_drain_install_date && (
                                <div className="text-sm flex justify-between">
                                  <span className="text-muted-foreground">Main drain</span>
                                  <span className="font-medium">{selectedEquipment.main_drain_install_date}</span>
                                </div>
                              )}
                              {selectedEquipment.equalizer_install_date && (
                                <div className="text-sm flex justify-between">
                                  <span className="text-muted-foreground">Equalizer</span>
                                  <span className="font-medium">{selectedEquipment.equalizer_install_date}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Inspection Timeline */}
                <Card className="shadow-sm">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <ClipboardCheck className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Inspection Timeline</span>
                      <div className="flex-1 border-t border-border ml-1" />
                      <span className="text-[11px] text-muted-foreground/50">{selectedFacility.inspections.length}</span>
                    </div>

                    <div className="max-h-[500px] overflow-y-auto">
                      {selectedFacility.inspections.length === 0 ? (
                        <p className="text-center py-8 text-muted-foreground text-sm">No inspection records</p>
                      ) : (
                        <div className="relative ml-3">
                          {/* Vertical timeline line */}
                          <div className="absolute left-0 top-2 bottom-2 w-px bg-border" />

                          {selectedFacility.inspections.map((insp, idx) => (
                            <div key={insp.id} className="relative pl-6 pb-1">
                              {/* Timeline dot */}
                              <div className={`absolute left-0 top-2.5 w-2.5 h-2.5 rounded-full -translate-x-[4.5px] ring-2 ring-background ${getTimelineDotColor(insp)}`} />

                              <button
                                className={`w-full text-left rounded-md px-3 py-2.5 transition-colors ${
                                  expandedInspection === insp.id
                                    ? "bg-accent"
                                    : "hover:bg-muted"
                                }`}
                                onClick={() =>
                                  setExpandedInspection(
                                    expandedInspection === insp.id ? null : insp.id
                                  )
                                }
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <div className="min-w-0">
                                    <p className="text-sm font-medium">
                                      {formatDate(insp.inspection_date)}
                                    </p>
                                    <p className="text-[10px] text-muted-foreground">
                                      {insp.inspection_type || "Inspection"}
                                      {insp.inspector_name ? ` -- ${insp.inspector_name}` : ""}
                                    </p>
                                  </div>
                                  <div className="flex items-center gap-1.5 shrink-0">
                                    {insp.closure_required && (
                                      <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Closure</Badge>
                                    )}
                                    {insp.reinspection_required && (
                                      <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-amber-400 text-amber-600">Reinspection</Badge>
                                    )}
                                    {insp.major_violations > 0 && (
                                      <Badge variant="destructive" className="text-[10px] px-1.5 py-0">{insp.major_violations} major</Badge>
                                    )}
                                    {insp.total_violations > 0 && (
                                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{insp.total_violations} viol</Badge>
                                    )}
                                    {insp.water_chemistry && (
                                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400" title="Chemistry data available" />
                                    )}
                                    {expandedInspection === insp.id ? (
                                      <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                                    ) : (
                                      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                                    )}
                                  </div>
                                </div>
                              </button>

                              {expandedInspection === insp.id && (
                                <div className="ml-3">
                                  <InspectionDetail inspection={insp} />
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        )}

        {/* Empty state when no facility selected and wide view */}
        {!selectedFacility && !loading && facilities.length > 0 && (
          <div className="hidden lg:flex lg:col-span-8 items-center justify-center text-muted-foreground text-sm">
            <div className="text-center">
              <Shield className="h-8 w-8 mx-auto mb-2 opacity-30" />
              <p>Select a facility to view details</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function InspectionDetail({ inspection }: { inspection: EMDInspection }) {
  const [violations, setViolations] = useState<EMDViolation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (inspection.violations && inspection.violations.length > 0) {
      setViolations(inspection.violations);
      setLoading(false);
      return;
    }
    setViolations([]);
    setLoading(false);
  }, [inspection]);

  return (
    <div className="px-3 pb-3 pt-1 space-y-2.5">
      {/* Pool specs */}
      {(inspection.pool_capacity_gallons || inspection.flow_rate_gpm) && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {inspection.pool_capacity_gallons && (
            <span className="text-muted-foreground">
              Capacity: <span className="font-medium text-foreground">{inspection.pool_capacity_gallons.toLocaleString()} gal</span>
            </span>
          )}
          {inspection.flow_rate_gpm && (
            <span className="text-muted-foreground">
              Flow: <span className="font-medium text-foreground">{inspection.flow_rate_gpm} GPM</span>
            </span>
          )}
        </div>
      )}

      {/* Water Chemistry — blue tinted row */}
      {inspection.water_chemistry && (
        <div className="bg-blue-50 dark:bg-blue-950/30 rounded-md p-2.5 border border-blue-200/50 dark:border-blue-800/50">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-blue-600 dark:text-blue-400 mb-1">Chemistry</p>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-sm">
            {inspection.water_chemistry.free_chlorine != null && (
              <span>
                <span className="text-muted-foreground text-xs">FC </span>
                <span className={`font-medium ${inspection.water_chemistry.free_chlorine < 1 || inspection.water_chemistry.free_chlorine > 10 ? "text-red-600" : "text-foreground"}`}>
                  {inspection.water_chemistry.free_chlorine} ppm
                </span>
              </span>
            )}
            {inspection.water_chemistry.combined_chlorine != null && (
              <span>
                <span className="text-muted-foreground text-xs">CC </span>
                <span className={`font-medium ${inspection.water_chemistry.combined_chlorine > 0.5 ? "text-red-600" : "text-foreground"}`}>
                  {inspection.water_chemistry.combined_chlorine} ppm
                </span>
              </span>
            )}
            {inspection.water_chemistry.ph != null && (
              <span>
                <span className="text-muted-foreground text-xs">pH </span>
                <span className={`font-medium ${inspection.water_chemistry.ph < 7.2 || inspection.water_chemistry.ph > 7.8 ? "text-red-600" : "text-foreground"}`}>
                  {inspection.water_chemistry.ph}
                </span>
              </span>
            )}
            {inspection.water_chemistry.cyanuric_acid_ppm != null && (
              <span>
                <span className="text-muted-foreground text-xs">CYA </span>
                <span className={`font-medium ${inspection.water_chemistry.cyanuric_acid_ppm > 100 ? "text-red-600" : inspection.water_chemistry.cyanuric_acid_ppm > 70 ? "text-amber-600" : "text-foreground"}`}>
                  {inspection.water_chemistry.cyanuric_acid_ppm} ppm
                </span>
              </span>
            )}
          </div>
        </div>
      )}

      {/* Notes */}
      {inspection.report_notes && (
        <div className="bg-muted/50 rounded-md p-2.5">
          <p className="text-xs text-muted-foreground whitespace-pre-line line-clamp-6">
            {inspection.report_notes}
          </p>
        </div>
      )}

      {/* Violations */}
      {violations.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Violations
          </p>
          {violations.map((v) => (
            <div
              key={v.id}
              className={`rounded-md p-2.5 text-sm ${
                v.is_major_violation
                  ? "bg-red-50 dark:bg-red-950/30 border border-red-200/50 dark:border-red-800/50"
                  : "bg-muted/50"
              }`}
            >
              <div className="flex items-start gap-2">
                {v.is_major_violation && (
                  <AlertTriangle className="h-3.5 w-3.5 text-red-500 mt-0.5 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="font-medium text-sm">
                    {v.violation_code && (
                      <span className="text-muted-foreground mr-1">{v.violation_code}.</span>
                    )}
                    {getViolationLabel(v.violation_code, v.violation_title)}
                  </p>
                  {v.observations && (
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-3">
                      {v.observations}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        loading && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )
      )}
    </div>
  );
}
