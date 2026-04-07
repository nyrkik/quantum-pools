"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import type { SatelliteAnalysis, PoolBowWithCoords } from "@/types/satellite";
import type { PropertyPhoto } from "@/types/photo";
import { resizeImage } from "@/lib/image-utils";
import type { MapActions, PropertyGroup } from "@/components/maps/satellite-map";
import { usePermissions } from "@/lib/permissions";
import DifficultyModal from "@/components/profitability/difficulty-modal";
import { PoolSidebar, PoolDetailPanel, ModeSwitcher, MapPanel } from "@/components/map";
import {
  type StatusFilter,
  type MapMode,
  type PortfolioMedians,
  type DimensionComparison,
  getBowStatus,
  bestStatus,
} from "@/components/map/map-types";

export default function MapPage() {
  const searchParams = useSearchParams();
  const initialBowId = searchParams.get("wf");
  const perms = usePermissions();
  const canEdit = perms.role !== "technician" && perms.role !== "readonly";
  const [mode, setMode] = useState<MapMode>("pools");
  const [poolBows, setPoolBows] = useState<PoolBowWithCoords[]>([]);
  const [analyses, setAnalyses] = useState<SatelliteAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null);
  const [activeBowId, setActiveBowId] = useState<string | null>(null);
  const [movingProperty, setMovingProperty] = useState(false);
  const [propertyPinPosition, setPropertyPinPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [savingPropertyPin, setSavingPropertyPin] = useState(false);
  const [highlightedBowId, setHighlightedBowId] = useState<string | null>(null);
  const [pinPosition, setPinPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [savingPin, setSavingPin] = useState(false);
  const [search, setSearch] = useState("");
  const [images, setImages] = useState<PropertyPhoto[]>([]);
  const [capturing, setCapturing] = useState(false);
  const [statusFilters, setStatusFilters] = useState<Set<StatusFilter>>(new Set(["analyzed", "pinned", "not_analyzed"]));
  const [shouldFlyTo, setShouldFlyTo] = useState(false);
  const [pinDirty, setPinDirty] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [bowDetails, setBowDetails] = useState<Map<string, Record<string, unknown>>>(new Map());
  const [propDetail, setPropDetail] = useState<Record<string, unknown> | null>(null);
  const [profitData, setProfitData] = useState<Record<string, unknown> | null>(null);
  const [rateAllocation, setRateAllocation] = useState<Record<string, { allocated_rate: number; allocation_method: string; weight: number }>>({});
  const [dimComparisons, setDimComparisons] = useState<Map<string, DimensionComparison>>(new Map());
  const [medians, setMedians] = useState<PortfolioMedians | null>(null);
  const [perimeterInputs, setPerimeterInputs] = useState<Map<string, string>>(new Map());
  const [areaInputs, setAreaInputs] = useState<Map<string, string>>(new Map());
  const [volumeInputs, setVolumeInputs] = useState<Map<string, string>>(new Map());
  const [perimeterShapes, setPerimeterShapes] = useState<Map<string, string>>(new Map());
  const [roundedCornersInputs, setRoundedCornersInputs] = useState<Map<string, boolean>>(new Map());
  const [stepEntryInputs, setStepEntryInputs] = useState<Map<string, number>>(new Map());
  const [benchShelfInputs, setBenchShelfInputs] = useState<Map<string, boolean>>(new Map());
  const [shallowDepthInputs, setShallowDepthInputs] = useState<Map<string, string>>(new Map());
  const [deepDepthInputs, setDeepDepthInputs] = useState<Map<string, string>>(new Map());
  const [savingPerimeter, setSavingPerimeter] = useState(false);
  const [measuringPerimeterBow, setMeasuringPerimeterBow] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const mapActionsRef = useRef<MapActions | null>(null);
  const [mapZoom, setMapZoom] = useState(12);
  const [diffModalOpen, setDiffModalOpen] = useState(false);
  const [chemicalCosts, setChemicalCosts] = useState<Map<string, { sanitizer_cost: number; acid_cost: number; cya_cost: number; salt_cost: number; cell_cost: number; insurance_cost: number; total_monthly: number; source: string }>>(new Map());
  const [costExpanded, setCostExpanded] = useState(false);
  const [dismissedDiscrepancies, setDismissedDiscrepancies] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem("qp_dismissed_discrepancies");
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });

  // --- Data fetching ---

  const loadData = useCallback(async () => {
    try {
      const [wfs, allAnalyses, med] = await Promise.all([
        api.get<PoolBowWithCoords[]>("/v1/satellite/pool-wfs"),
        api.get<SatelliteAnalysis[]>("/v1/satellite/all"),
        api.get<PortfolioMedians>("/v1/profitability/medians").catch(() => null),
      ]);
      setPoolBows(wfs);
      setAnalyses(allAnalyses);
      if (med) setMedians(med);
    } catch {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const onFocus = () => loadData();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [loadData]);

  const analysisMap = useMemo(() => new Map(analyses.map((a) => [a.water_feature_id, a])), [analyses]);

  // --- Property grouping ---

  const propertyGroups = useMemo((): PropertyGroup[] => {
    const groupMap = new Map<string, PropertyGroup>();
    for (const wf of poolBows) {
      let group = groupMap.get(wf.property_id);
      if (!group) {
        group = {
          property_id: wf.property_id,
          customer_id: wf.customer_id,
          customer_name: wf.customer_name,
          customer_type: wf.customer_type,
          address: wf.address,
          city: wf.city,
          lat: wf.lat,
          lng: wf.lng,
          tech_name: wf.tech_name,
          tech_color: wf.tech_color,
          wfs: [],
          best_status: "not_analyzed",
        };
        groupMap.set(wf.property_id, group);
      }
      group.wfs.push(wf);
    }
    for (const group of groupMap.values()) {
      const statuses = group.wfs.map((b) => getBowStatus(b, analysisMap));
      group.best_status = bestStatus(statuses);
    }
    return Array.from(groupMap.values());
  }, [poolBows, analysisMap]);

  // --- Auto-select on load ---

  const autoSelected = useRef(false);
  useEffect(() => {
    if (autoSelected.current || propertyGroups.length === 0) return;
    autoSelected.current = true;
    if (initialBowId) {
      const pg = propertyGroups.find((g) => g.wfs.some((b) => b.id === initialBowId));
      if (pg) {
        setShouldFlyTo(true);
        handlePropertySelect(pg.property_id);
        return;
      }
    }
    const sorted = [...propertyGroups].sort((a, b) => a.customer_name.localeCompare(b.customer_name));
    const first = sorted.find((g) => g.customer_type === "commercial") || sorted[0];
    if (first) selectPropertyQuiet(first.property_id);
  }, [propertyGroups, initialBowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedGroup = useMemo(() =>
    propertyGroups.find((g) => g.property_id === selectedPropertyId) || null,
    [propertyGroups, selectedPropertyId]
  );

  // --- Filtering ---

  const toggleFilter = (f: StatusFilter) => {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  };

  const toggleType = (t: string) => {
    setTypeFilter((prev) => prev === t ? null : t);
  };

  const sortFn = useCallback((a: PropertyGroup, b: PropertyGroup) => {
    return a.customer_name.localeCompare(b.customer_name);
  }, []);

  const filteredGroups = useMemo(() => {
    return propertyGroups.filter((g) => {
      if (typeFilter !== null && g.customer_type !== typeFilter) return false;
      if (!statusFilters.has(g.best_status)) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return g.customer_name.toLowerCase().includes(q)
        || g.address.toLowerCase().includes(q)
        || g.city.toLowerCase().includes(q)
        || g.wfs.some((b) => b.wf_name?.toLowerCase().includes(q));
    });
  }, [propertyGroups, search, statusFilters, typeFilter]);

  const commercialGroups = useMemo(() =>
    filteredGroups.filter((g) => g.customer_type === "commercial").sort(sortFn),
    [filteredGroups, sortFn]
  );
  const residentialGroups = useMemo(() =>
    filteredGroups.filter((g) => g.customer_type !== "commercial").sort(sortFn),
    [filteredGroups, sortFn]
  );

  // --- Detail loading ---

  const loadImages = useCallback(async (propertyId: string) => {
    try {
      const imgs = await api.get<PropertyPhoto[]>(`/v1/photos/properties/${propertyId}`);
      setImages(imgs);
    } catch {
      setImages([]);
    }
  }, []);

  const loadPropertyDetail = useCallback(async (propertyId: string, wfs: PoolBowWithCoords[]) => {
    setBowDetails(new Map());
    setPropDetail(null);
    setProfitData(null);
    setDimComparisons(new Map());
    setRateAllocation({});
    setChemicalCosts(new Map());
    setCostExpanded(false);

    const bowPromises = wfs.map(async (b) => {
      const [wf, comparison] = await Promise.all([
        api.get<Record<string, unknown>>(`/v1/water-features/${b.id}`).catch(() => null),
        api.get<DimensionComparison>(`/v1/dimensions/wfs/${b.id}/comparison`).catch(() => null),
      ]);
      return { bowId: b.id, wf, comparison };
    });

    const [prop, profit, allocation, ...bowResults] = await Promise.all([
      api.get<Record<string, unknown>>(`/v1/properties/${propertyId}`).catch(() => null),
      api.get<Record<string, unknown>>(`/v1/profitability/property/${propertyId}`).catch(() => null),
      api.get<Record<string, { allocated_rate: number; allocation_method: string; weight: number }>>(`/v1/profitability/property/${propertyId}/rate-allocation`).catch(() => ({})),
      ...bowPromises,
    ]);

    setPropDetail(prop);
    setProfitData(profit);
    setRateAllocation(allocation || {});

    const chemCostResults = await Promise.all(
      wfs.map(async (b) => {
        const cc = await api.get<{ sanitizer_cost: number; acid_cost: number; cya_cost: number; salt_cost: number; cell_cost: number; insurance_cost: number; total_monthly: number; source: string }>(`/v1/chemical-costs/wfs/${b.id}`).catch(() => null);
        return { bowId: b.id, cc };
      })
    );
    const newChemCosts = new Map<string, { sanitizer_cost: number; acid_cost: number; cya_cost: number; salt_cost: number; cell_cost: number; insurance_cost: number; total_monthly: number; source: string }>();
    for (const r of chemCostResults) {
      if (r.cc) newChemCosts.set(r.bowId, r.cc);
    }
    setChemicalCosts(newChemCosts);

    const newBowDetails = new Map<string, Record<string, unknown>>();
    const newDimComps = new Map<string, DimensionComparison>();
    for (const r of bowResults) {
      if (r.wf) newBowDetails.set(r.bowId, r.wf);
      if (r.comparison) newDimComps.set(r.bowId, r.comparison);
    }
    setBowDetails(newBowDetails);
    setDimComparisons(newDimComps);

    const newShapes = new Map<string, string>();
    for (const r of bowResults) {
      if (r.wf && (r.wf as { pool_shape?: string }).pool_shape) {
        newShapes.set(r.bowId, (r.wf as { pool_shape: string }).pool_shape);
      } else {
        newShapes.set(r.bowId, "rectangle");
      }
    }
    setPerimeterShapes(newShapes);
    setPerimeterInputs(new Map());
    setAreaInputs(new Map());
    setVolumeInputs(new Map());
    setMeasuringPerimeterBow(null);
  }, []);

  // --- Selection handlers ---

  const selectPropertyQuiet = useCallback((propertyId: string) => {
    setSelectedPropertyId(propertyId);
    setPinDirty(false);
    setPinPosition(null);
    setMapZoom(12);
    setHighlightedBowId(null);
    setMovingProperty(false);
    setPropertyPinPosition(null);

    const group = propertyGroups.find((g) => g.property_id === propertyId);
    if (group) {
      setActiveBowId(group.wfs.length === 1 ? group.wfs[0].id : null);
      loadImages(propertyId);
      loadPropertyDetail(propertyId, group.wfs);
    }
  }, [propertyGroups, analyses, loadImages, loadPropertyDetail]);

  const handlePropertySelect = useCallback((propertyId: string) => {
    setShouldFlyTo(true);
    selectPropertyQuiet(propertyId);
    setTimeout(() => {
      const el = document.getElementById(`prop-${propertyId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 50);
  }, [selectPropertyQuiet]);

  // --- Pin placement ---

  const handlePinPlace = useCallback((lat: number, lng: number) => {
    if (!canEdit || !selectedPropertyId) return;
    if (movingProperty) {
      setPropertyPinPosition({ lat, lng });
      return;
    }
    const group = propertyGroups.find((g) => g.property_id === selectedPropertyId);
    if (!group) return;
    const targetBow = highlightedBowId || activeBowId || group.wfs[0]?.id;
    if (!targetBow) return;
    setActiveBowId(targetBow);
    setHighlightedBowId(targetBow);
    setPinPosition({ lat, lng });
    setPinDirty(true);
  }, [canEdit, selectedPropertyId, propertyGroups, highlightedBowId, activeBowId, movingProperty]);

  const savePin = async () => {
    if (!activeBowId || !pinPosition) return;
    setSavingPin(true);
    try {
      const result = await api.put<SatelliteAnalysis>(
        `/v1/satellite/wfs/${activeBowId}/pin`,
        { pool_lat: pinPosition.lat, pool_lng: pinPosition.lng }
      );
      setAnalyses((prev) => {
        const idx = prev.findIndex((a) => a.water_feature_id === activeBowId);
        if (idx >= 0) return [...prev.slice(0, idx), result, ...prev.slice(idx + 1)];
        return [...prev, result];
      });
      setPoolBows((prev) =>
        prev.map((b) =>
          b.id === activeBowId
            ? { ...b, pool_lat: pinPosition.lat, pool_lng: pinPosition.lng }
            : b
        )
      );
      setPinDirty(false);
      setPinPosition(null);
      toast.success("Pin saved");
    } catch {
      toast.error("Failed to save pin");
    } finally {
      setSavingPin(false);
    }
  };

  const savePropertyLocation = async () => {
    if (!selectedPropertyId || !propertyPinPosition) return;
    setSavingPropertyPin(true);
    try {
      await api.put(`/v1/properties/${selectedPropertyId}`, {
        lat: propertyPinPosition.lat,
        lng: propertyPinPosition.lng,
      });
      setPoolBows((prev) =>
        prev.map((b) =>
          b.property_id === selectedPropertyId
            ? { ...b, lat: propertyPinPosition.lat, lng: propertyPinPosition.lng }
            : b
        )
      );
      setMovingProperty(false);
      setPropertyPinPosition(null);
      toast.success("Property location updated");
    } catch {
      toast.error("Failed to update location");
    } finally {
      setSavingPropertyPin(false);
    }
  };

  // --- Measurement save ---

  const saveMeasurements = async (bowId: string) => {
    const perimeterInput = perimeterInputs.get(bowId) || "";
    const perimeterShape = perimeterShapes.get(bowId) || "rectangle";
    const areaInput = areaInputs.get(bowId) || "";
    const volumeInput = volumeInputs.get(bowId) || "";
    const areaSqft = areaInput ? parseFloat(areaInput) : undefined;
    const volumeGal = volumeInput ? parseInt(volumeInput) : undefined;
    const ft = perimeterInput ? parseFloat(perimeterInput) : undefined;

    const shapeFields: Record<string, unknown> = {};
    if (roundedCornersInputs.has(bowId)) shapeFields.has_rounded_corners = roundedCornersInputs.get(bowId);
    if (stepEntryInputs.has(bowId)) shapeFields.step_entry_count = stepEntryInputs.get(bowId);
    if (benchShelfInputs.has(bowId)) shapeFields.has_bench_shelf = benchShelfInputs.get(bowId);
    const shallowVal = shallowDepthInputs.get(bowId);
    if (shallowVal !== undefined) shapeFields.pool_depth_shallow = shallowVal ? parseFloat(shallowVal) : null;
    const deepVal = deepDepthInputs.get(bowId);
    if (deepVal !== undefined) shapeFields.pool_depth_deep = deepVal ? parseFloat(deepVal) : null;

    const hasShapeChanges = Object.keys(shapeFields).length > 0;

    if (!ft && !areaSqft && !volumeGal && !hasShapeChanges) {
      toast.error("Enter at least one measurement");
      return;
    }
    setSavingPerimeter(true);
    try {
      if (ft && ft > 0) {
        await api.post(`/v1/dimensions/wfs/${bowId}/perimeter`, {
          perimeter_ft: ft,
          pool_shape: perimeterShape,
          ...(areaSqft && areaSqft > 0 ? { area_sqft: areaSqft } : {}),
        });
      } else if (areaSqft && areaSqft > 0) {
        await api.put(`/v1/water-features/${bowId}`, { pool_sqft: areaSqft, pool_shape: perimeterShape });
      }
      if (volumeGal && volumeGal > 0) {
        await api.put(`/v1/water-features/${bowId}`, { pool_gallons: volumeGal });
      }
      if (hasShapeChanges || perimeterShape) {
        await api.put(`/v1/water-features/${bowId}`, { pool_shape: perimeterShape, ...shapeFields });
      }
      toast.success("Measurements saved");
      setPerimeterInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setAreaInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setVolumeInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setRoundedCornersInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setStepEntryInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setBenchShelfInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setShallowDepthInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      setDeepDepthInputs((prev) => { const n = new Map(prev); n.delete(bowId); return n; });
      if (selectedGroup) {
        await loadPropertyDetail(selectedPropertyId!, selectedGroup.wfs);
      }
    } catch {
      toast.error("Failed to save measurements");
    } finally {
      setSavingPerimeter(false);
    }
  };

  // --- Image operations ---

  const uploadPhoto = async (file: File) => {
    if (!selectedPropertyId) return;
    setCapturing(true);
    try {
      const resized = await resizeImage(file, 1600);
      const formData = new FormData();
      formData.append("photo", resized, file.name);
      if (activeBowId) formData.append("water_feature_id", activeBowId);
      const img = await api.upload<PropertyPhoto>(
        `/v1/photos/properties/${selectedPropertyId}/upload`,
        formData
      );
      setImages((prev) => [img, ...prev]);
      toast.success("Photo uploaded");
    } catch {
      toast.error("Upload failed");
    } finally {
      setCapturing(false);
    }
  };

  const setHero = async (imageId: string) => {
    try {
      const updated = await api.put<PropertyPhoto>(`/v1/photos/${imageId}/hero`);
      setImages((prev) =>
        prev.map((img) => ({ ...img, is_hero: img.id === updated.id }))
      );
      toast.success("Hero image set");
    } catch {
      toast.error("Failed to set hero");
    }
  };

  const deleteImage = async (imageId: string) => {
    try {
      await api.delete(`/v1/photos/${imageId}`);
      setImages((prev) => prev.filter((img) => img.id !== imageId));
      toast.success("Photo deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  // --- WF pin activation ---

  const handleBowPinActivate = (bowId: string) => {
    if (activeBowId === bowId) {
      setActiveBowId(null);
      setPinPosition(null);
      setPinDirty(false);
    } else {
      setActiveBowId(bowId);
      setPinDirty(false);
      const wf = poolBows.find((b) => b.id === bowId);
      const analysis = analyses.find((a) => a.water_feature_id === bowId);
      if (analysis?.pool_lat && analysis?.pool_lng) {
        setPinPosition({ lat: analysis.pool_lat, lng: analysis.pool_lng });
      } else if (wf?.pool_lat && wf?.pool_lng) {
        setPinPosition({ lat: wf.pool_lat, lng: wf.pool_lng });
      } else {
        setPinPosition(null);
      }
    }
  };

  // --- Dismiss discrepancy ---

  const handleDismissDiscrepancy = (bowId: string) => {
    setDismissedDiscrepancies((prev) => {
      const next = new Set(prev).add(bowId);
      try { localStorage.setItem("qp_dismissed_discrepancies", JSON.stringify([...next])); } catch {}
      return next;
    });
  };

  // --- Render ---

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const analyzedCount = analyses.filter((a) => a.pool_detected).length;
  const totalBowCount = poolBows.length;

  return (
    <div className="space-y-3">
      <ModeSwitcher
        mode={mode}
        onModeChange={setMode}
        analyzedCount={analyzedCount}
        totalBowCount={totalBowCount}
      />

      {/* 3-Column Layout: List | Map | Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" style={{ height: "calc(100vh - 140px)", minHeight: 500 }}>
        {/* Left Panel */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
          {mode === "pools" ? (
            <PoolSidebar
              search={search}
              onSearchChange={setSearch}
              typeFilter={typeFilter}
              onToggleType={toggleType}
              commercialGroups={commercialGroups}
              residentialGroups={residentialGroups}
              filteredGroups={filteredGroups}
              propertyGroups={propertyGroups}
              selectedPropertyId={selectedPropertyId}
              highlightedBowId={highlightedBowId}
              onPropertySelect={handlePropertySelect}
              onHighlightBow={setHighlightedBowId}
              listRef={listRef}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
              {mode === "routes" ? "Route list coming soon" : "Customer list coming soon"}
            </div>
          )}
        </div>

        {/* Center: Map */}
        <MapPanel
          filteredGroups={filteredGroups}
          selectedPropertyId={selectedPropertyId}
          pinPosition={movingProperty ? propertyPinPosition : pinPosition}
          shouldFlyTo={shouldFlyTo}
          mapActionsRef={mapActionsRef}
          onPropertySelect={handlePropertySelect}
          onPinPlace={handlePinPlace}
          onZoomChange={setMapZoom}
          mapZoom={mapZoom}
          pinDirty={pinDirty}
          onResetPin={() => setPinPosition(null)}
          statusFilters={statusFilters}
          onToggleFilter={toggleFilter}
        />

        {/* Right: Details Panel */}
        <div className="lg:col-span-4 min-h-0 overflow-y-auto">
          {mode !== "pools" ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              {mode === "routes" ? "Route details coming soon" : "Profitability details coming soon"}
            </div>
          ) : selectedGroup ? (
            <PoolDetailPanel
              selectedGroup={selectedGroup}
              selectedPropertyId={selectedPropertyId!}
              canEdit={canEdit}
              movingProperty={movingProperty}
              propertyPinPosition={propertyPinPosition}
              savingPropertyPin={savingPropertyPin}
              propDetail={propDetail}
              profitData={profitData}
              medians={medians}
              chemicalCosts={chemicalCosts}
              costExpanded={costExpanded}
              bowDetails={bowDetails}
              dimComparisons={dimComparisons}
              analysisMap={analysisMap}
              rateAllocation={rateAllocation}
              images={images}
              capturing={capturing}
              activeBowId={activeBowId}
              highlightedBowId={highlightedBowId}
              pinDirty={pinDirty}
              savingPin={savingPin}
              savingPerimeter={savingPerimeter}
              measuringPerimeterBow={measuringPerimeterBow}
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
              onSetMovingProperty={setMovingProperty}
              onSetPropertyPinPosition={setPropertyPinPosition}
              onSavePropertyLocation={savePropertyLocation}
              onSetCostExpanded={setCostExpanded}
              onSetDiffModalOpen={setDiffModalOpen}
              onHighlightBow={setHighlightedBowId}
              onSavePin={savePin}
              onSetMeasuringBow={setMeasuringPerimeterBow}
              onSetPerimeterInput={(bowId, value) => setPerimeterInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetAreaInput={(bowId, value) => setAreaInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetVolumeInput={(bowId, value) => setVolumeInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetPerimeterShape={(bowId, value) => setPerimeterShapes((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetRoundedCorners={(bowId, value) => setRoundedCornersInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetStepEntry={(bowId, value) => setStepEntryInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetBenchShelf={(bowId, value) => setBenchShelfInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetShallowDepth={(bowId, value) => setShallowDepthInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSetDeepDepth={(bowId, value) => setDeepDepthInputs((prev) => { const n = new Map(prev); n.set(bowId, value); return n; })}
              onSaveMeasurements={saveMeasurements}
              onDismissDiscrepancy={handleDismissDiscrepancy}
              onUploadPhoto={uploadPhoto}
              onSetHero={setHero}
              onDeleteImage={deleteImage}
              onResetPinState={() => { setPinPosition(null); setPinDirty(false); }}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a property from the list or map
            </div>
          )}
        </div>
      </div>

      {selectedPropertyId && (
        <DifficultyModal
          open={diffModalOpen}
          onOpenChange={setDiffModalOpen}
          propertyId={selectedPropertyId}
          bowDetail={selectedGroup?.wfs[0] ? (bowDetails.get(selectedGroup.wfs[0].id) || null) : null}
          onSaved={() => {
            if (selectedPropertyId && selectedGroup) {
              loadPropertyDetail(selectedPropertyId, selectedGroup.wfs);
            }
          }}
        />
      )}
    </div>
  );
}
