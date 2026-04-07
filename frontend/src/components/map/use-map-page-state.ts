"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { resizeImage } from "@/lib/image-utils";
import type { SatelliteAnalysis, PoolBowWithCoords } from "@/types/satellite";
import type { PropertyPhoto } from "@/types/photo";
import type { MapActions, PropertyGroup } from "@/components/maps/satellite-map";
import { usePermissions } from "@/lib/permissions";
import {
  type StatusFilter,
  type MapMode,
  type PortfolioMedians,
  type DimensionComparison,
  getBowStatus,
  bestStatus,
} from "./map-types";

export type ChemicalCostEntry = {
  sanitizer_cost: number;
  acid_cost: number;
  cya_cost: number;
  salt_cost: number;
  cell_cost: number;
  insurance_cost: number;
  total_monthly: number;
  source: string;
};

export function useMapPageState(initialBowId: string | null) {
  const perms = usePermissions();
  const canEdit = perms.role !== "technician" && perms.role !== "readonly";

  // --- Core data ---
  const [mode, setMode] = useState<MapMode>("pools");
  const [poolBows, setPoolBows] = useState<PoolBowWithCoords[]>([]);
  const [analyses, setAnalyses] = useState<SatelliteAnalysis[]>([]);
  const [loading, setLoading] = useState(true);

  // --- Selection ---
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null);
  const [activeBowId, setActiveBowId] = useState<string | null>(null);
  const [highlightedBowId, setHighlightedBowId] = useState<string | null>(null);
  const [shouldFlyTo, setShouldFlyTo] = useState(false);

  // --- Property pin movement ---
  const [movingProperty, setMovingProperty] = useState(false);
  const [propertyPinPosition, setPropertyPinPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [savingPropertyPin, setSavingPropertyPin] = useState(false);

  // --- BOW pin placement ---
  const [pinPosition, setPinPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [savingPin, setSavingPin] = useState(false);
  const [pinDirty, setPinDirty] = useState(false);

  // --- Filters ---
  const [search, setSearch] = useState("");
  const [statusFilters, setStatusFilters] = useState<Set<StatusFilter>>(new Set(["analyzed", "pinned", "not_analyzed"]));
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  // --- Detail data ---
  const [images, setImages] = useState<PropertyPhoto[]>([]);
  const [capturing, setCapturing] = useState(false);
  const [bowDetails, setBowDetails] = useState<Map<string, Record<string, unknown>>>(new Map());
  const [propDetail, setPropDetail] = useState<Record<string, unknown> | null>(null);
  const [profitData, setProfitData] = useState<Record<string, unknown> | null>(null);
  const [rateAllocation, setRateAllocation] = useState<Record<string, { allocated_rate: number; allocation_method: string; weight: number }>>({});
  const [dimComparisons, setDimComparisons] = useState<Map<string, DimensionComparison>>(new Map());
  const [medians, setMedians] = useState<PortfolioMedians | null>(null);
  const [chemicalCosts, setChemicalCosts] = useState<Map<string, ChemicalCostEntry>>(new Map());
  const [costExpanded, setCostExpanded] = useState(false);

  // --- Measurement form inputs ---
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

  // --- Map state ---
  const [mapZoom, setMapZoom] = useState(12);
  const [diffModalOpen, setDiffModalOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const mapActionsRef = useRef<MapActions | null>(null);

  // --- Dismissed discrepancies ---
  const [dismissedDiscrepancies, setDismissedDiscrepancies] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem("qp_dismissed_discrepancies");
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });

  // === Data fetching ===

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

  // === Property grouping ===

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

  // === Auto-select on load ===

  const autoSelected = useRef(false);

  const selectedGroup = useMemo(() =>
    propertyGroups.find((g) => g.property_id === selectedPropertyId) || null,
    [propertyGroups, selectedPropertyId]
  );

  // === Filtering ===

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

  // === Detail loading ===

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
        const cc = await api.get<ChemicalCostEntry>(`/v1/chemical-costs/wfs/${b.id}`).catch(() => null);
        return { bowId: b.id, cc };
      })
    );
    const newChemCosts = new Map<string, ChemicalCostEntry>();
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

  // === Selection handlers ===

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
  }, [propertyGroups, analyses, loadImages, loadPropertyDetail]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePropertySelect = useCallback((propertyId: string) => {
    setShouldFlyTo(true);
    selectPropertyQuiet(propertyId);
    setTimeout(() => {
      const el = document.getElementById(`prop-${propertyId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 50);
  }, [selectPropertyQuiet]);

  // Auto-select effect
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

  // === Pin placement ===

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

  // === Measurement save ===

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

  // === Image operations ===

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

  // === WF pin activation ===

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

  // === Dismiss discrepancy ===

  const handleDismissDiscrepancy = (bowId: string) => {
    setDismissedDiscrepancies((prev) => {
      const next = new Set(prev).add(bowId);
      try { localStorage.setItem("qp_dismissed_discrepancies", JSON.stringify([...next])); } catch {}
      return next;
    });
  };

  // === Measurement input setters (Map updaters) ===

  const setMapEntry = <T,>(setter: React.Dispatch<React.SetStateAction<Map<string, T>>>) =>
    (bowId: string, value: T) => setter((prev) => { const n = new Map(prev); n.set(bowId, value); return n; });

  const onSetPerimeterInput = setMapEntry(setPerimeterInputs);
  const onSetAreaInput = setMapEntry(setAreaInputs);
  const onSetVolumeInput = setMapEntry(setVolumeInputs);
  const onSetPerimeterShape = setMapEntry(setPerimeterShapes);
  const onSetRoundedCorners = setMapEntry(setRoundedCornersInputs);
  const onSetStepEntry = setMapEntry(setStepEntryInputs);
  const onSetBenchShelf = setMapEntry(setBenchShelfInputs);
  const onSetShallowDepth = setMapEntry(setShallowDepthInputs);
  const onSetDeepDepth = setMapEntry(setDeepDepthInputs);

  // === Computed values ===

  const analyzedCount = analyses.filter((a) => a.pool_detected).length;
  const totalBowCount = poolBows.length;

  return {
    // Permissions
    perms,
    canEdit,

    // Core data
    mode,
    setMode,
    loading,
    analysisMap,

    // Property groups
    propertyGroups,
    filteredGroups,
    commercialGroups,
    residentialGroups,
    selectedGroup,

    // Selection
    selectedPropertyId,
    activeBowId,
    highlightedBowId,
    setHighlightedBowId,
    shouldFlyTo,
    handlePropertySelect,

    // Property pin
    movingProperty,
    setMovingProperty,
    propertyPinPosition,
    setPropertyPinPosition,
    savingPropertyPin,
    savePropertyLocation,

    // BOW pin
    pinPosition,
    setPinPosition,
    pinDirty,
    setPinDirty,
    savingPin,
    savePin,
    handlePinPlace,
    handleBowPinActivate,

    // Filters
    search,
    setSearch,
    typeFilter,
    toggleType,
    statusFilters,
    toggleFilter,

    // Detail data
    images,
    capturing,
    bowDetails,
    propDetail,
    profitData,
    medians,
    chemicalCosts,
    costExpanded,
    setCostExpanded,
    rateAllocation,
    dimComparisons,

    // Measurement inputs
    perimeterInputs,
    areaInputs,
    volumeInputs,
    perimeterShapes,
    roundedCornersInputs,
    stepEntryInputs,
    benchShelfInputs,
    shallowDepthInputs,
    deepDepthInputs,
    savingPerimeter,
    measuringPerimeterBow,
    setMeasuringPerimeterBow,
    onSetPerimeterInput,
    onSetAreaInput,
    onSetVolumeInput,
    onSetPerimeterShape,
    onSetRoundedCorners,
    onSetStepEntry,
    onSetBenchShelf,
    onSetShallowDepth,
    onSetDeepDepth,
    saveMeasurements,

    // Discrepancies
    dismissedDiscrepancies,
    handleDismissDiscrepancy,

    // Image operations
    uploadPhoto,
    setHero,
    deleteImage,

    // Map
    mapZoom,
    setMapZoom,
    diffModalOpen,
    setDiffModalOpen,
    listRef,
    mapActionsRef,

    // Stats
    analyzedCount,
    totalBowCount,

    // Detail loading (for difficulty modal callback)
    loadPropertyDetail,
  };
}
