"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Shield } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { useAuth } from "@/lib/auth-context";
import { PropertyMatching } from "@/components/inspections/property-matching";
import { InspectionDashboard } from "@/components/inspections/inspection-dashboard";
import { FacilityList } from "@/components/inspections/facility-list";
import { FacilityDetail } from "@/components/inspections/facility-detail";
import { RecentLookups, LookupCart, RedactedDetailPanel } from "@/components/inspections/lookup-cart";
import { getFacilityStatus } from "@/components/inspections/inspection-constants";
import type {
  InspectionFacilityListItem,
  InspectionFacilityDetail,
  InspectionEquipment,
  InspectionLookup,
  SearchResult,
  RedactedDetail,
  DashboardData,
  DashboardTile,
  ScraperHealth,
} from "@/components/inspections/inspection-types";

export default function InspectionsPage() {
  const { inspectionTier } = useAuth();
  const [facilities, setFacilities] = useState<InspectionFacilityListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedFacility, setSelectedFacility] = useState<InspectionFacilityDetail | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<InspectionEquipment | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedInspectionId, setSelectedInspectionId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | "closed">("all");
  const [matchFilter, setMatchFilter] = useState<"all" | "matched" | "unmatched">("matched");
  const [sortBy, setSortBy] = useState<string>("name");
  const [cart, setCart] = useState<Set<string>>(new Set());
  const [lookups, setLookups] = useState<InspectionLookup[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchMode, setSearchMode] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [redactedDetail, setRedactedDetail] = useState<RedactedDetail | null>(null);
  const isFullResearch = inspectionTier === "full_research";
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [expandedTile, setExpandedTile] = useState<DashboardTile>(null);
  const [scraperHealth, setScraperHealth] = useState<ScraperHealth | null>(null);

  // Poll scraper health every 60s
  useEffect(() => {
    const fetchStatus = () => {
      api.get<Record<string, unknown>>("/v1/inspections/backfill-status")
        .then((d) => setScraperHealth(d as ScraperHealth))
        .catch(() => setScraperHealth(null));
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 60000);
    return () => clearInterval(interval);
  }, []);

  // Fetch active lookups
  useEffect(() => {
    api.get<InspectionLookup[]>("/v1/inspections/lookups")
      .then(setLookups)
      .catch(() => setLookups([]));
  }, []);

  // Fetch dashboard data
  useEffect(() => {
    api.get<DashboardData>("/v1/inspections/dashboard")
      .then(setDashboard)
      .catch(() => setDashboard(null));
  }, []);

  const fetchFacilities = useCallback(async () => {
    setLoading(true);
    try {
      if (!isFullResearch && search && search.length >= 2) {
        setSearchMode(true);
        const params = new URLSearchParams();
        params.set("q", search);
        params.set("limit", "20");
        const data = await api.get<SearchResult[]>(
          `/v1/inspections/search?${params.toString()}`
        );
        setSearchResults(data);
        const mainParams = new URLSearchParams();
        if (search) mainParams.set("search", search);
        mainParams.set("limit", "5000");
        mainParams.set("sort", sortBy);
        const mainData = await api.get<InspectionFacilityListItem[]>(
          `/v1/inspections/facilities?${mainParams.toString()}`
        );
        setFacilities(mainData);
      } else {
        setSearchMode(false);
        setSearchResults([]);
        const params = new URLSearchParams();
        if (search) params.set("search", search);
        params.set("limit", "5000");
        params.set("sort", sortBy);
        const data = await api.get<InspectionFacilityListItem[]>(
          `/v1/inspections/facilities?${params.toString()}`
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
      const detail: any = await api.get(`/v1/inspections/facilities/${id}`);
      if (detail.redacted) {
        setRedactedDetail(detail);
        setSelectedFacility(null);
      } else {
        setSelectedFacility(detail);
        setRedactedDetail(null);
        setSelectedPermitId(permitId ?? null);
        setSelectedInspectionId(null);
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
      await api.post("/v1/inspections/lookups/purchase", { facility_ids: Array.from(cart) });
      setCart(new Set());
      const newLookups = await api.get<InspectionLookup[]>("/v1/inspections/lookups");
      setLookups(newLookups);
      fetchFacilities();
    } catch {
      // ignore
    } finally {
      setPurchasing(false);
    }
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
    return allInspections[0];
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
      ? `/v1/inspections/facilities/${selectedFacility.id}/equipment?permit_id=${selectedPermitId}`
      : `/v1/inspections/facilities/${selectedFacility.id}/equipment`;
    api.get<InspectionEquipment | null>(url)
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
    <PageLayout
      title="Inspections"
      icon={<Shield className="h-5 w-5 text-muted-foreground" />}
      subtitle="Health department inspection data"
    >
    <div className="h-[calc(100vh-8rem)] flex flex-col gap-3 overflow-hidden">
      {/* Operations Dashboard */}
      <InspectionDashboard
        dashboard={dashboard}
        expandedTile={expandedTile}
        scraperHealth={scraperHealth}
        onTileClick={handleTileClick}
        onItemClick={handleDashboardItemClick}
      />

      {/* Recent Lookups */}
      <RecentLookups lookups={lookups} onSelectFacility={(id) => selectFacility(id)} />

      {/* Cart */}
      <LookupCart
        cart={cart}
        purchasing={purchasing}
        onClear={() => setCart(new Set())}
        onPurchase={purchaseCart}
      />

      {/* My Properties EMD Matching */}
      <div className="shrink-0 max-h-80 overflow-y-auto">
        <PropertyMatching />
      </div>

      {/* Research Section */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0">
        {/* Left: Facility list */}
        <FacilityList
          facilities={facilities}
          filteredFacilities={filteredFacilities}
          search={search}
          setSearch={setSearch}
          sortBy={sortBy}
          setSortBy={setSortBy}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          matchFilter={matchFilter}
          setMatchFilter={setMatchFilter}
          loading={loading}
          isFullResearch={isFullResearch}
          selectedFacility={selectedFacility}
          selectedPermitId={selectedPermitId}
          hasDetailOpen={!!(selectedFacility || redactedDetail)}
          searchMode={searchMode}
          searchResults={searchResults}
          cart={cart}
          onSelectFacility={selectFacility}
          onToggleCart={toggleCart}
        />

        {/* Right: Redacted detail panel */}
        {redactedDetail && !selectedFacility && (
          <RedactedDetailPanel
            detail={redactedDetail}
            cart={cart}
            detailLoading={detailLoading}
            onClose={() => setRedactedDetail(null)}
            onToggleCart={toggleCart}
          />
        )}

        {/* Right: Detail panel */}
        {selectedFacility && (
          <FacilityDetail
            facility={selectedFacility}
            allInspections={allInspections}
            selectedInspection={selectedInspection}
            selectedEquipment={selectedEquipment}
            facilityStatus={facilityStatus}
            selectedProgramId={selectedProgramId}
            detailLoading={detailLoading}
            onSelectInspection={setSelectedInspectionId}
          />
        )}

        {/* Empty state */}
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
    </PageLayout>
  );
}
