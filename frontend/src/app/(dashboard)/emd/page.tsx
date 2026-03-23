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
  TrendingUp,
  Bell,
  ArrowUpRight,
  FileText,
  Lock,
  ShoppingCart,
  Clock,
  Unlock,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import Link from "next/link";
import { PropertyMatching } from "@/components/emd/property-matching";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

// --- Types ---

interface EMDFacilityListItem {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  facility_id: string | null;
  facility_type: string | null;
  program_identifier: string | null;
  permit_id: string | null;
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
  program_identifier: string | null;
  permit_id: string | null;
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
  has_pdf: boolean;
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

interface EMDProgram {
  permit_id: string | null;
  program_identifier: string;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  is_closed: boolean;
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
  programs: EMDProgram[];
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  matched_property_address: string | null;
  matched_customer_name: string | null;
  matched_customer_id?: string | null;
  matched_wf_names?: Record<string, string>;
}

interface DashboardData {
  my_inspections_this_week: {
    facility_name: string;
    facility_id: string;
    inspection_date: string | null;
    total_violations: number;
    major_violations: number;
    closure_required: boolean;
    is_matched: boolean;
  }[];
  season_alerts: {
    facility_name: string;
    facility_id: string;
    alert_type: string;
    description: string;
    last_inspection_date: string | null;
  }[];
  fresh_leads: {
    facility_name: string;
    facility_id: string;
    address: string;
    inspection_date: string | null;
    total_violations: number;
    closure_required: boolean;
  }[];
  trending_worse: {
    facility_name: string;
    facility_id: string;
    recent_violations: number;
    previous_violations: number;
    trend: string;
  }[];
}

type FacilityStatus = "compliant" | "violations" | "reinspection" | "closure";

function hasClosureViolations(insp: EMDInspection): boolean {
  if (!insp.violations) return false;
  const re = /MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE/i;
  return insp.violations.some(v => v.observations && re.test(v.observations));
}

function getFacilityStatus(inspections: EMDInspection[]): FacilityStatus {
  if (inspections.length === 0) return "compliant";
  const latest = inspections[0];
  if (hasClosureViolations(latest)) return "closure";
  if (latest.reinspection_required) return "reinspection";
  if (latest.total_violations > 0) return "violations";
  return "compliant";
}

function getListItemStatus(f: EMDFacilityListItem): "green" | "amber" | "red" {
  if (f.total_violations > 10) return "red";
  if (f.total_violations > 0) return "amber";
  return "green";
}

function getStatusDotColor(status: "green" | "amber" | "red") {
  if (status === "red") return "bg-red-500";
  if (status === "amber") return "bg-amber-500";
  return "bg-green-500";
}

function StatusBadge({ status }: { status: FacilityStatus }) {
  switch (status) {
    case "closure":
      return <Badge variant="destructive" className="text-xs font-semibold">Closed</Badge>;
    case "reinspection":
      return <Badge variant="outline" className="text-xs font-semibold border-amber-400 text-amber-600">Reinspection</Badge>;
    case "violations":
      return <Badge variant="outline" className="text-xs font-semibold border-amber-400 text-amber-600">Open</Badge>;
    case "compliant":
      return <Badge className="text-xs font-semibold bg-green-600 hover:bg-green-700 text-white">Open</Badge>;
  }
}

function getTimelineDotColor(insp: EMDInspection): string {
  if (hasClosureViolations(insp)) return "bg-red-500";
  if (insp.major_violations > 0) return "bg-red-500";
  if (insp.total_violations > 0) return "bg-amber-500";
  return "bg-green-500";
}

/** Clean program identifier: "POOL @ 4407 OAK HOLLOW DR" → "Pool", "3612 - SPA" → "Spa" */
function cleanProgramId(raw: string | null): string {
  if (!raw) return "Pool";
  // Strip address suffixes and PR numbers
  let clean = raw.replace(/@\s*.*/i, "").replace(/PR\d+/i, "").replace(/\d{4}\s*-\s*/g, "").trim();
  if (!clean) return "Pool";
  // Title case
  return clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase();
}

type DashboardTile = "inspections" | "alerts" | "leads" | "trending" | null;

interface EMDLookup {
  id: string;
  facility_id: string;
  facility_name: string;
  city: string | null;
  purchased_at: string;
  expires_at: string;
  days_remaining: number;
}

interface SearchResult extends EMDFacilityListItem {
  redacted?: boolean;
  has_lookup?: boolean;
}

export default function EMDPage() {
  const { emdTier } = useAuth();
  const [facilities, setFacilities] = useState<EMDFacilityListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedFacility, setSelectedFacility] = useState<EMDFacilityDetail | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<EMDEquipment | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedInspectionId, setSelectedInspectionId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | "closed">("all");
  const [matchFilter, setMatchFilter] = useState<"all" | "matched" | "unmatched">("matched");
  const [sortBy, setSortBy] = useState<string>("name");
  const [cart, setCart] = useState<Set<string>>(new Set());
  const [lookups, setLookups] = useState<EMDLookup[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchMode, setSearchMode] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [redactedDetail, setRedactedDetail] = useState<{
    id: string; name: string; city: string | null; total_inspections: number;
    total_violations: number; last_inspection_date: string | null;
    unlock_price_cents: number;
  } | null>(null);
  const isFullResearch = emdTier === "full_research";
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [expandedTile, setExpandedTile] = useState<DashboardTile>(null);
  const [scraperHealth, setScraperHealth] = useState<{
    state?: string;
    last_success?: string;
    last_error?: string;
    consecutive_failures?: number;
    total_scrapes?: number;
  } | null>(null);

  // Poll scraper health every 60s
  useEffect(() => {
    const fetchStatus = () => {
      api.get<Record<string, unknown>>("/v1/emd/backfill-status")
        .then((d) => setScraperHealth(d as typeof scraperHealth))
        .catch(() => setScraperHealth(null));
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 60000);
    return () => clearInterval(interval);
  }, []);

  // Fetch active lookups
  useEffect(() => {
    api.get<EMDLookup[]>("/v1/emd/lookups")
      .then(setLookups)
      .catch(() => setLookups([]));
  }, []);

  // Fetch dashboard data
  useEffect(() => {
    api.get<DashboardData>("/v1/emd/dashboard")
      .then(setDashboard)
      .catch(() => setDashboard(null));
  }, []);

  const fetchFacilities = useCallback(async () => {
    setLoading(true);
    try {
      // Non-full-research with search → use search endpoint for redacted results
      if (!isFullResearch && search && search.length >= 2) {
        setSearchMode(true);
        const params = new URLSearchParams();
        params.set("q", search);
        params.set("limit", "20");
        const data = await api.get<SearchResult[]>(
          `/v1/emd/search?${params.toString()}`
        );
        setSearchResults(data);
        // Also fetch the main list (matched only, handled server-side)
        const mainParams = new URLSearchParams();
        if (search) mainParams.set("search", search);
        mainParams.set("limit", "5000");
        mainParams.set("sort", sortBy);
        const mainData = await api.get<EMDFacilityListItem[]>(
          `/v1/emd/facilities?${mainParams.toString()}`
        );
        setFacilities(mainData);
      } else {
        setSearchMode(false);
        setSearchResults([]);
        const params = new URLSearchParams();
        if (search) params.set("search", search);
        params.set("limit", "5000");
        params.set("sort", sortBy);
        const data = await api.get<EMDFacilityListItem[]>(
          `/v1/emd/facilities?${params.toString()}`
        );
        setFacilities(data);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [search, sortBy, isFullResearch]);

  useEffect(() => {
    const timer = setTimeout(fetchFacilities, 300);
    return () => clearTimeout(timer);
  }, [fetchFacilities]);

  const [selectedPermitId, setSelectedPermitId] = useState<string | null>(null);

  const selectFacility = async (id: string, permitId?: string | null) => {
    setDetailLoading(true);
    setSelectedEquipment(null);
    setRedactedDetail(null);
    setSelectedFacility(null);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const detail: any = await api.get(`/v1/emd/facilities/${id}`);
      if (detail.redacted) {
        setRedactedDetail(detail);
        setSelectedFacility(null);
      } else {
        setSelectedFacility(detail);
        setRedactedDetail(null);
        setSelectedPermitId(permitId ?? null);
        setSelectedInspectionId(null); // will auto-select latest via useMemo
      }
      setSelectedInspectionId(null);
    } catch {
      // ignore
    } finally {
      setDetailLoading(false);
    }
  };

  const toggleCart = (facilityId: string) => {
    setCart(prev => {
      const next = new Set(prev);
      if (next.has(facilityId)) next.delete(facilityId);
      else next.add(facilityId);
      return next;
    });
  };

  const purchaseCart = async () => {
    if (cart.size === 0) return;
    setPurchasing(true);
    try {
      await api.post("/v1/emd/lookups/purchase", { facility_ids: Array.from(cart) });
      setCart(new Set());
      // Refresh lookups
      const newLookups = await api.get<EMDLookup[]>("/v1/emd/lookups");
      setLookups(newLookups);
      // Refresh facility list
      fetchFacilities();
    } catch {
      // ignore
    } finally {
      setPurchasing(false);
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

  const selectedProgramId = useMemo(() => {
    if (!selectedFacility || !selectedPermitId) return null;
    const insp = selectedFacility.inspections?.find(i => i.permit_id === selectedPermitId);
    return insp?.program_identifier || null;
  }, [selectedFacility, selectedPermitId]);

  const allInspections = useMemo(() => {
    if (!selectedFacility) return [];
    const inspections = selectedFacility.inspections ?? [];
    if (selectedProgramId) {
      return inspections.filter(i => i.program_identifier === selectedProgramId);
    }
    return inspections;
  }, [selectedFacility, selectedProgramId]);
  const facilityStatus = allInspections.length > 0 ? getFacilityStatus(allInspections) : null;
  const selectedInspection = useMemo(() => {
    if (!allInspections.length) return null;
    if (selectedInspectionId) {
      const found = allInspections.find(i => i.id === selectedInspectionId);
      if (found) return found;
    }
    return allInspections[0]; // default to latest
  }, [allInspections, selectedInspectionId]);

  const filteredFacilities = useMemo(() => {
    return facilities.filter((f) => {
      if (matchFilter === "matched" && !f.matched_property_id) return false;
      if (matchFilter === "unmatched" && f.matched_property_id) return false;
      if (statusFilter === "open" && f.is_closed) return false;
      if (statusFilter === "closed" && !f.is_closed) return false;
      return true;
    });
  }, [facilities, statusFilter, matchFilter]);

  // Re-fetch equipment when selected water feature changes
  useEffect(() => {
    if (!selectedFacility) return;
    const url = selectedPermitId
      ? `/v1/emd/facilities/${selectedFacility.id}/equipment?permit_id=${selectedPermitId}`
      : `/v1/emd/facilities/${selectedFacility.id}/equipment`;
    api.get<EMDEquipment | null>(url)
      .then(setSelectedEquipment)
      .catch(() => setSelectedEquipment(null));
  }, [selectedPermitId, selectedFacility?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTileClick = (tile: DashboardTile) => {
    setExpandedTile(expandedTile === tile ? null : tile);
  };

  const handleDashboardItemClick = (facilityId: string) => {
    selectFacility(facilityId);
    setExpandedTile(null);
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col gap-3 overflow-hidden">
      {/* ===== OPERATIONS DASHBOARD ===== */}
      <div className="shrink-0 space-y-2">
        {/* Backfill status bar */}
        {scraperHealth?.state === "scraping" && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 dark:bg-green-950/30 border border-green-200/50 dark:border-green-800/50 rounded-md text-xs">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-green-700 dark:text-green-400 font-medium">Scraping new inspections</span>
          </div>
        )}
        {scraperHealth?.state === "error" && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 dark:bg-red-950/30 border border-red-200/50 dark:border-red-800/50 rounded-md text-xs">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500" />
            <span className="text-red-700 dark:text-red-400 font-medium">Scraper error</span>
            <span className="text-muted-foreground">{scraperHealth.consecutive_failures} consecutive failures</span>
          </div>
        )}

        {/* 4 Dashboard Tiles */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Tile 1: My Inspections */}
          <Card
            className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "inspections" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
            onClick={() => handleTileClick("inspections")}
          >
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">My Inspections</p>
                  {dashboard ? (
                    dashboard.my_inspections_this_week.length > 0 ? (
                      <div className="flex items-center gap-2 mt-0.5">
                        <p className="text-2xl font-bold leading-tight text-primary">{dashboard.my_inspections_this_week.length}</p>
                        {dashboard.my_inspections_this_week.some(i => i.closure_required) ? (
                          <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
                        ) : (
                          <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground mt-1">No inspections this week</p>
                    )
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                  )}
                </div>
                <ClipboardCheck className="h-5 w-5 text-primary opacity-40" />
              </div>
            </CardContent>
          </Card>

          {/* Tile 2: Alerts */}
          <Card
            className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "alerts" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
            onClick={() => handleTileClick("alerts")}
          >
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Alerts</p>
                  {dashboard ? (
                    dashboard.season_alerts.length > 0 ? (
                      <div>
                        <p className="text-2xl font-bold leading-tight mt-0.5 text-amber-600">{dashboard.season_alerts.length}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {dashboard.season_alerts.filter(a => a.alert_type === "recent_closure").length > 0
                            ? `${dashboard.season_alerts.filter(a => a.alert_type === "recent_closure").length} closures`
                            : `${dashboard.season_alerts.filter(a => a.alert_type === "repeat_violation").length} repeat violations`}
                        </p>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground mt-1">No active alerts</p>
                    )
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                  )}
                </div>
                <Bell className="h-5 w-5 text-amber-600 opacity-40" />
              </div>
            </CardContent>
          </Card>

          {/* Tile 3: Fresh Leads */}
          <Card
            className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "leads" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
            onClick={() => handleTileClick("leads")}
          >
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Fresh Leads</p>
                  {dashboard ? (
                    <div>
                      <p className="text-2xl font-bold leading-tight mt-0.5 text-green-600">{dashboard.fresh_leads.length}</p>
                      <p className="text-[10px] text-muted-foreground">inspected this week</p>
                    </div>
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                  )}
                </div>
                <Target className="h-5 w-5 text-green-600 opacity-40" />
              </div>
            </CardContent>
          </Card>

          {/* Tile 4: Trending Worse */}
          <Card
            className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "trending" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
            onClick={() => handleTileClick("trending")}
          >
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Trending Worse</p>
                  {dashboard ? (
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <p className="text-2xl font-bold leading-tight text-red-600">{dashboard.trending_worse.length}</p>
                      <ArrowUpRight className="h-4 w-4 text-red-500" />
                    </div>
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                  )}
                </div>
                <TrendingUp className="h-5 w-5 text-red-600 opacity-40" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Expanded Alert Panel */}
        {expandedTile && dashboard && (
          <Card className="shadow-sm border-l-4 border-primary">
            <CardContent className="p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  {expandedTile === "inspections" && "My Inspections This Week"}
                  {expandedTile === "alerts" && "Season Alerts"}
                  {expandedTile === "leads" && "Fresh Leads"}
                  {expandedTile === "trending" && "Trending Worse"}
                </span>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setExpandedTile(null)}>
                  <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                </Button>
              </div>

              {/* Inspections panel */}
              {expandedTile === "inspections" && (
                dashboard.my_inspections_this_week.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">No inspections for matched facilities this week.</p>
                ) : (
                  <div className="space-y-1">
                    {dashboard.my_inspections_this_week.map((item, idx) => (
                      <button
                        key={idx}
                        className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                        onClick={() => handleDashboardItemClick(item.facility_id)}
                      >
                        <div className="min-w-0 flex items-center gap-2">
                          <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${item.closure_required ? "bg-red-500" : item.total_violations > 0 ? "bg-amber-500" : "bg-green-500"}`} />
                          <span className="font-medium truncate">{item.facility_name}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs text-muted-foreground">{formatDate(item.inspection_date)}</span>
                          {item.total_violations > 0 && (
                            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{item.total_violations} viol</Badge>
                          )}
                          {item.closure_required && (
                            <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Closure</Badge>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )
              )}

              {/* Alerts panel */}
              {expandedTile === "alerts" && (
                dashboard.season_alerts.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">No active alerts.</p>
                ) : (
                  <div className="space-y-1">
                    {dashboard.season_alerts.map((alert, idx) => (
                      <button
                        key={idx}
                        className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                        onClick={() => handleDashboardItemClick(alert.facility_id)}
                      >
                        <div className="min-w-0 flex items-center gap-2">
                          <Badge
                            variant={alert.alert_type === "recent_closure" ? "destructive" : "outline"}
                            className={`text-[10px] px-1.5 py-0 shrink-0 ${alert.alert_type === "repeat_violation" ? "border-amber-400 text-amber-600" : ""}`}
                          >
                            {alert.alert_type === "recent_closure" ? "Closure" : alert.alert_type === "repeat_violation" ? "Repeat" : "Unresolved"}
                          </Badge>
                          <span className="font-medium truncate">{alert.facility_name}</span>
                        </div>
                        <span className="text-xs text-muted-foreground shrink-0 max-w-[40%] truncate">{alert.description}</span>
                      </button>
                    ))}
                  </div>
                )
              )}

              {/* Leads panel */}
              {expandedTile === "leads" && (
                dashboard.fresh_leads.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">No new leads this week.</p>
                ) : (
                  <div className="space-y-1">
                    {dashboard.fresh_leads.map((lead, idx) => (
                      <button
                        key={idx}
                        className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                        onClick={() => handleDashboardItemClick(lead.facility_id)}
                      >
                        <div className="min-w-0">
                          <span className="font-medium truncate block">{lead.facility_name}</span>
                          <span className="text-xs text-muted-foreground truncate block">{lead.address}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{lead.total_violations} viol</Badge>
                          {lead.closure_required && (
                            <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Closure</Badge>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )
              )}

              {/* Trending panel */}
              {expandedTile === "trending" && (
                dashboard.trending_worse.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">No facilities trending worse.</p>
                ) : (
                  <div className="space-y-1">
                    {dashboard.trending_worse.map((item, idx) => (
                      <button
                        key={idx}
                        className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                        onClick={() => handleDashboardItemClick(item.facility_id)}
                      >
                        <span className="font-medium truncate">{item.facility_name}</span>
                        <div className="flex items-center gap-1 shrink-0 text-xs">
                          <span className="text-muted-foreground">{item.previous_violations}</span>
                          <ArrowUpRight className="h-3 w-3 text-red-500" />
                          <span className="text-red-600 font-medium">{item.recent_violations}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* ===== RECENT LOOKUPS ===== */}
      {lookups.length > 0 && (
        <div className="shrink-0">
          <div className="flex items-center gap-2 mb-1.5">
            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Recent Lookups</span>
            <div className="flex-1 border-t border-border ml-1" />
          </div>
          <div className="flex gap-2 flex-wrap">
            {lookups.map((l) => (
              <button
                key={l.id}
                className="flex items-center gap-2 px-2.5 py-1.5 bg-muted/50 rounded-md hover:bg-accent text-sm transition-colors"
                onClick={() => selectFacility(l.facility_id)}
              >
                <Unlock className="h-3 w-3 text-green-500" />
                <span className="font-medium truncate max-w-[180px]">{l.facility_name}</span>
                <span className="text-[10px] text-muted-foreground">{l.days_remaining}d left</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ===== CART ===== */}
      {cart.size > 0 && (
        <div className="shrink-0">
          <Card className="shadow-sm border-primary/30 bg-primary/5">
            <CardContent className="p-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ShoppingCart className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium">{cart.size} {cart.size === 1 ? "facility" : "facilities"} in cart</span>
                <span className="text-sm text-muted-foreground">${(cart.size * 0.99).toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setCart(new Set())}>
                  Clear
                </Button>
                <Button size="sm" className="h-7 text-xs" onClick={purchaseCart} disabled={purchasing}>
                  {purchasing ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                  Unlock {cart.size} — ${(cart.size * 0.99).toFixed(2)}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ===== MY PROPERTIES EMD MATCHING ===== */}
      <div className="shrink-0 max-h-80 overflow-y-auto">
        <PropertyMatching />
      </div>

      {/* ===== RESEARCH SECTION ===== */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0">
        {/* Left: Facility list */}
        <div className={`${selectedFacility || redactedDetail ? "lg:col-span-4" : "lg:col-span-12"} min-h-0 flex flex-col`}>
          <Card className="shadow-sm flex-1 flex flex-col min-h-0">
            {/* Search + sort + filters */}
            <div className="p-3 pb-0 shrink-0 space-y-2">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder={isFullResearch ? "Search all facilities..." : "Search facilities..."}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="w-[140px]">
                    <SelectValue placeholder="Sort by" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="name">Name</SelectItem>
                    <SelectItem value="violations">Violations</SelectItem>
                    <SelectItem value="last_inspection">Last Inspected</SelectItem>
                    <SelectItem value="status">Status</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                {isFullResearch ? (
                  <>
                    {/* Full research: ownership + status filters */}
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mr-1">Show</span>
                      {([
                        { value: "all" as const, label: "All Facilities" },
                        { value: "matched" as const, label: "My Clients" },
                        { value: "unmatched" as const, label: "Prospects" },
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
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mr-1">Status</span>
                      {([
                        { value: "all" as const, label: "All" },
                        { value: "open" as const, label: "Open" },
                        { value: "closed" as const, label: "Closed" },
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
                    </div>
                  </>
                ) : (
                  <>
                    {/* My Inspections tier: show "My Clients" label + Full Research tease */}
                    <div className="flex items-center gap-1.5">
                      <Badge variant="secondary" className="text-[10px]">My Clients</Badge>
                      <span className="text-[10px] text-muted-foreground">Showing your matched facilities</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mr-1">Status</span>
                      {([
                        { value: "all" as const, label: "All" },
                        { value: "open" as const, label: "Open" },
                        { value: "closed" as const, label: "Closed" },
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
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Facility list -- table-like layout */}
            <div className="flex-1 flex flex-col min-h-0">
              {/* Column headers */}
              <div className="grid grid-cols-[auto_auto_auto_1fr] gap-x-2 items-center bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground shrink-0 sticky top-0 z-10">
                <span className="w-14 text-center">Status</span>
                <span className="w-[70px] text-center">Last Insp</span>
                <span className="w-10 text-center">Viol</span>
                <span>Facility</span>
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
                      const rowKey = `${f.id}-${f.permit_id || "default"}`;
                      const isSelected = selectedFacility?.id === f.id && selectedPermitId === f.permit_id;
                      return (
                        <button
                          key={rowKey}
                          onClick={() => selectFacility(f.id, f.permit_id)}
                          className={`w-full text-left grid grid-cols-[auto_auto_auto_1fr] gap-x-2 items-center px-3 py-2 text-sm transition-colors border-b border-border/40 ${
                            isSelected
                              ? "bg-accent border-l-3 border-l-primary font-medium"
                              : f.is_closed
                                ? "bg-red-50/50 dark:bg-red-950/10 hover:bg-red-50 dark:hover:bg-red-950/20 border-l-2 border-l-red-400"
                                : "hover:bg-blue-50 dark:hover:bg-blue-950"
                          }`}
                        >
                          {/* Status: OPEN / CLOSED */}
                          <div className="w-14 text-center">
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
                                  <TooltipContent side="right" className="max-w-xs">
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

                          {/* Last inspection date */}
                          <div className="w-[70px] text-center">
                            <span className="text-[11px] text-muted-foreground">
                              {f.last_inspection_date ? formatDate(f.last_inspection_date) : "--"}
                            </span>
                          </div>

                          {/* Violation count */}
                          <div className="w-10 text-center">
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

                          {/* Facility name + water feature + address */}
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="font-medium truncate">{f.name}</span>
                              {f.program_identifier && (
                                <span className="text-[10px] text-muted-foreground shrink-0">{cleanProgramId(f.program_identifier)}</span>
                              )}
                              {f.matched_property_id && (
                                <Link2 className="h-3 w-3 text-green-500 shrink-0" />
                              )}
                            </div>
                            <div className="text-xs truncate text-muted-foreground">
                              {f.street_address}{f.city ? `, ${f.city}` : ""}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </TooltipProvider>
                )}

                {/* Search results (redacted facilities for non-full-research) */}
                {searchMode && searchResults.filter(r => r.redacted).length > 0 && (
                  <>
                    <div className="bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-2">
                      <Search className="h-3 w-3" />
                      <span>Other Facilities</span>
                      <span className="text-muted-foreground/50">— unlock for $0.99 each</span>
                    </div>
                    {searchResults.filter(r => r.redacted).map((f) => {
                      const inCart = cart.has(f.id);
                      return (
                        <div
                          key={f.id}
                          className="w-full text-left grid grid-cols-[1fr_auto_auto] gap-x-2 items-center px-3 py-2 text-sm border-b border-border/40 bg-muted/30"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <Lock className="h-3 w-3 text-muted-foreground shrink-0" />
                              <span className="font-medium truncate">{f.name}</span>
                            </div>
                            <div className="text-xs text-muted-foreground truncate ml-5">
                              {f.city || "Sacramento County"}
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            {f.total_violations > 0 && (
                              <Badge
                                variant={f.total_violations > 10 ? "destructive" : "secondary"}
                                className="text-[10px] px-1.5 py-0"
                              >
                                {f.total_violations} viol
                              </Badge>
                            )}
                          </div>
                          <Button
                            variant={inCart ? "default" : "outline"}
                            size="sm"
                            className="h-6 px-2 text-[10px]"
                            onClick={() => toggleCart(f.id)}
                          >
                            {inCart ? (
                              <><X className="h-3 w-3 mr-0.5" />Remove</>
                            ) : (
                              <><ShoppingCart className="h-3 w-3 mr-0.5" />$0.99</>
                            )}
                          </Button>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            </div>

            {/* Footer count */}
            <div className="text-[11px] text-muted-foreground px-3 py-1.5 border-t shrink-0">
              {filteredFacilities.length} of {facilities.length} facilities
              {searchMode && searchResults.filter(r => r.redacted).length > 0 && (
                <span> + {searchResults.filter(r => r.redacted).length} available to unlock</span>
              )}
            </div>
          </Card>
        </div>

        {/* Right: Redacted detail panel (unlock tease) */}
        {redactedDetail && !selectedFacility && (
          <div className="lg:col-span-8 min-h-0 overflow-y-auto space-y-3">
            {detailLoading ? (
              <Card className="shadow-sm">
                <CardContent className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </CardContent>
              </Card>
            ) : (
              <Card className="shadow-sm">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold">{redactedDetail.name}</h2>
                      <p className="text-sm text-muted-foreground mt-0.5">{redactedDetail.city || "Sacramento County"}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0"
                      onClick={() => setRedactedDetail(null)}
                    >
                      <X className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </div>

                  <div className="grid grid-cols-3 gap-3 mt-4">
                    <div className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Inspections</p>
                      <p className="text-xl font-bold leading-tight mt-0.5">{redactedDetail.total_inspections}</p>
                    </div>
                    <div className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Violations</p>
                      <p className={`text-xl font-bold leading-tight mt-0.5 ${redactedDetail.total_violations > 10 ? "text-red-600" : redactedDetail.total_violations > 0 ? "text-amber-600" : ""}`}>{redactedDetail.total_violations}</p>
                    </div>
                    <div className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Last Inspected</p>
                      <p className="text-xl font-bold leading-tight mt-0.5">{formatDate(redactedDetail.last_inspection_date)}</p>
                    </div>
                  </div>

                  {/* Blurred tease area */}
                  <div className="mt-6 relative">
                    <div className="blur-sm pointer-events-none select-none">
                      <div className="space-y-2">
                        <div className="h-4 w-3/4 bg-muted rounded" />
                        <div className="h-4 w-1/2 bg-muted rounded" />
                        <div className="h-4 w-2/3 bg-muted rounded" />
                        <div className="h-12 w-full bg-muted rounded" />
                        <div className="h-4 w-1/2 bg-muted rounded" />
                      </div>
                    </div>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <div className="rounded-full bg-background p-3 shadow-sm border mb-3">
                        <Lock className="h-6 w-6 text-muted-foreground" />
                      </div>
                      <p className="text-sm font-medium mb-1">Full details locked</p>
                      <p className="text-xs text-muted-foreground mb-3 text-center max-w-xs">
                        Unlock this facility to see address, permit holder, inspection timeline, equipment, and violations.
                      </p>
                      {cart.has(redactedDetail.id) ? (
                        <Button variant="outline" size="sm" onClick={() => toggleCart(redactedDetail.id)}>
                          <X className="h-3 w-3 mr-1" /> Remove from Cart
                        </Button>
                      ) : (
                        <Button size="sm" onClick={() => toggleCart(redactedDetail.id)}>
                          <ShoppingCart className="h-3.5 w-3.5 mr-1.5" />
                          Add to Cart — $0.99
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}

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
                    <div className="flex items-center gap-2.5">
                      <h2 className="text-lg font-semibold truncate">
                        {selectedFacility.matched_customer_name || selectedFacility.name}
                        {selectedFacility.matched_customer_name && selectedFacility.matched_customer_name !== selectedFacility.name && (
                          <span className="font-normal text-muted-foreground"> ({selectedFacility.name})</span>
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
                      const userBowName = selectedFacility.matched_wf_names?.[bowType];
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
                      {selectedFacility.street_address}
                      {selectedFacility.city ? `, ${selectedFacility.city}` : ""}
                      {selectedFacility.state ? `, ${selectedFacility.state}` : ""}
                      {selectedFacility.zip_code ? ` ${selectedFacility.zip_code}` : ""}
                    </p>
                    {selectedEquipment?.pool_capacity_gallons && (
                      <p className="text-sm mt-1">
                        <span className="text-lg font-bold">{selectedEquipment.pool_capacity_gallons.toLocaleString()}</span>
                        <span className="text-muted-foreground ml-1">gallons</span>
                      </p>
                    )}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 pt-2 border-t text-xs text-muted-foreground">
                      {selectedFacility.facility_id && (
                        <span>Facility <span className="font-medium text-foreground">{selectedFacility.facility_id}</span></span>
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
                              onClick={() => setSelectedInspectionId(insp.id)}
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
                                      window.open(`/api/v1/emd/inspections/${insp.id}/pdf`, "_blank");
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
                  <Card className="shadow-sm">
                    <CardContent className="p-0">
                      {/* Header bar */}
                      <div className="bg-slate-100 dark:bg-slate-800 px-4 py-2.5 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <p className="text-sm font-semibold">{formatDate(selectedInspection.inspection_date)}</p>
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0">{selectedInspection.inspection_type || "Inspection"}</Badge>
                          {selectedInspection.has_pdf && (
                            <Button variant="ghost" size="icon" className="h-6 w-6" title="View PDF"
                              onClick={() => window.open(`/api/v1/emd/inspections/${selectedInspection.id}/pdf`, "_blank")}>
                              <FileText className="h-3.5 w-3.5 text-blue-500" />
                            </Button>
                          )}
                        </div>
                        <div className="flex items-center text-xs text-muted-foreground">
                          {selectedInspection.inspector_name && (
                            <span>Inspector <span className="font-medium text-foreground">{selectedInspection.inspector_name}</span></span>
                          )}
                          {selectedInspection.inspector_name && selectedFacility.permit_holder && (
                            <span className="mx-2">·</span>
                          )}
                          {selectedFacility.permit_holder && (
                            <span>Permit Holder <span className="font-medium text-foreground">{selectedFacility.permit_holder}</span></span>
                          )}
                          {selectedFacility.phone && (
                            <span className="ml-3"><span className="font-medium text-foreground">{selectedFacility.phone}</span></span>
                          )}
                        </div>
                      </div>

                      {/* Chemistry + gauges — always shown */}
                      <div className="px-4 py-3 border-b">
                        <div className="grid grid-cols-4 sm:grid-cols-7 gap-1.5">
                          {[
                            { label: "FC", value: selectedInspection.water_chemistry?.free_chlorine ?? null, bad: (v: number) => v < 1 || v > 10 },
                            { label: "CC", value: selectedInspection.water_chemistry?.combined_chlorine ?? null, bad: (v: number) => v > 0.5 },
                            { label: "pH", value: selectedInspection.water_chemistry?.ph ?? null, bad: (v: number) => v < 7.2 || v > 7.8 },
                            { label: "CYA", value: selectedInspection.water_chemistry?.cyanuric_acid_ppm ?? null, bad: (v: number) => v > 100 },
                            { label: "Flow", value: selectedInspection.flow_rate_gpm ?? null, bad: () => false },
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

                      {/* Equipment — always shown */}
                      <div className="px-4 py-3 border-b">
                        <div className="flex items-center gap-2 mb-2.5">
                          <Wrench className="h-3 w-3 text-muted-foreground" />
                          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Equipment</p>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {[
                            { label: "Pump", value: selectedEquipment ? [selectedEquipment.filter_pump_1_make, selectedEquipment.filter_pump_1_model, selectedEquipment.filter_pump_1_hp ? `${selectedEquipment.filter_pump_1_hp}hp` : null].filter(Boolean).join(" ") : null, sub: null },
                            { label: "Filter", value: selectedEquipment ? [selectedEquipment.filter_1_type, selectedEquipment.filter_1_make, selectedEquipment.filter_1_model].filter(Boolean).join(" ") : null, sub: null },
                            { label: "Sanitizer", value: selectedEquipment ? [selectedEquipment.sanitizer_1_type, selectedEquipment.sanitizer_1_details].filter(Boolean).join(" · ") : null, sub: null },
                            { label: "Main Drain", value: selectedEquipment?.main_drain_model || null, sub: selectedEquipment?.main_drain_install_date ? `Installed ${selectedEquipment.main_drain_install_date}` : null },
                            { label: "Equalizer", value: selectedEquipment?.equalizer_model || null, sub: selectedEquipment?.equalizer_install_date ? `Installed ${selectedEquipment.equalizer_install_date}` : null },
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
                      {selectedInspection.violations && selectedInspection.violations.length > 0 && (
                        <div className="px-4 py-3 border-b">
                          <div className="flex items-center gap-2 mb-2">
                            <AlertTriangle className="h-3 w-3 text-muted-foreground" />
                            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Violations</p>
                            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-1">{selectedInspection.violations.length}</Badge>
                          </div>
                          <div className="space-y-1.5">
                            {selectedInspection.violations.map((v) => {
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
                      {selectedInspection.report_notes && (
                        <div className="px-4 py-3">
                          <div className="flex items-center gap-2 mb-1.5">
                            <FileText className="h-3 w-3 text-muted-foreground" />
                            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Notes</p>
                          </div>
                          <p className="text-xs text-muted-foreground whitespace-pre-line leading-relaxed">{selectedInspection.report_notes}</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </div>
        )}

        {/* Empty state when no facility selected and wide view */}
        {!selectedFacility && !redactedDetail && !loading && facilities.length > 0 && (
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

      {/* Water Chemistry -- blue tinted row */}
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
                  <div className="flex items-center gap-2">
                    <p className={`font-medium text-sm ${v.is_major_violation ? "text-red-700 dark:text-red-400" : ""}`}>
                      {v.violation_code && (
                        <span className="text-muted-foreground mr-1">{v.violation_code}.</span>
                      )}
                      {getViolationLabel(v.violation_code, v.violation_title)}
                    </p>
                    {v.observations?.toLowerCase().includes("closure") && (
                      <Badge variant="destructive" className="text-[9px] px-1 py-0">CLOSURE</Badge>
                    )}
                  </div>
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
