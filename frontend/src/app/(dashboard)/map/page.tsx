"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  Loader2,
  Satellite,
  Droplets,
  MapPin,
  Crosshair,
  Search,
  Camera,
  Star,
  Trash2,
  Building2,
  Home,
  Route,
  TrendingUp,
  DollarSign,
  Clock,
  Move,
  Ruler,
  Wrench,
  Gauge,
  FlaskConical,
  Thermometer,
  Zap,
  Dog,
  Lock,
  Calendar,
  Shield,
  Pipette,
  CircleDot,
  ZoomIn,
  ZoomOut,
  ExternalLink,
  AlertTriangle,
  Pencil,
  X,
  ChevronDown,
  ChevronUp,
  WavesLadder,
  Waves,
} from "lucide-react";

function waterTypeIcon(type: string, className: string) {
  switch (type) {
    case "spa": case "hot_tub": return <Droplets className={className} />;
    case "fountain": case "water_feature": case "wading_pool": return <Waves className={className} />;
    default: return <WavesLadder className={className} />;
  }
}
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
import { resizeImage } from "@/lib/image-utils";
import SatelliteMap from "@/components/maps/satellite-map";
import type { MapActions, PropertyGroup } from "@/components/maps/satellite-map";
import { usePermissions } from "@/lib/permissions";
import DifficultyModal from "@/components/profitability/difficulty-modal";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://100.121.52.15:7061";

type StatusFilter = "analyzed" | "pinned" | "not_analyzed";
type MapMode = "pools" | "routes" | "profitability";

interface PortfolioMedians {
  rate_per_gallon: number | null;
  cost: number;
  margin_pct: number;
  difficulty: number;
}

interface DimensionComparison {
  estimates: { id: string; source: string; estimated_sqft: number | null; perimeter_ft: number | null; notes: string | null; created_at: string }[];
  active_source: string | null;
  active_sqft: number | null;
  discrepancy_pct: number | null;
  discrepancy_level: string | null;
}

const SOURCE_LABELS: Record<string, string> = {
  inspection: "Inspection",
  perimeter: "Perimeter",
  measurement: "Measured",
  satellite: "Satellite",
  manual: "Manual",
};

const SOURCE_COLORS: Record<string, string> = {
  inspection: "bg-green-100 text-green-800",
  perimeter: "bg-green-100 text-green-800",
  measurement: "bg-blue-100 text-blue-800",
  satellite: "bg-yellow-100 text-yellow-800",
  manual: "bg-gray-100 text-gray-600",
};

const POOL_SHAPES = [
  { value: "rectangle", label: "Rectangle" },
  { value: "irregular_rectangle", label: "Irregular Rectangle" },
  { value: "round", label: "Round" },
  { value: "oval", label: "Oval" },
  { value: "irregular_oval", label: "Irregular Oval" },
  { value: "kidney", label: "Kidney" },
  { value: "L-shape", label: "L-Shape" },
  { value: "freeform", label: "Freeform" },
];

const MAP_MODES = [
  { key: "pools" as MapMode, label: "Pools", Icon: Droplets },
  { key: "routes" as MapMode, label: "Routes", Icon: Route },
  { key: "profitability" as MapMode, label: "Profitability", Icon: TrendingUp },
];

function getBowStatus(bow: PoolBowWithCoords, analysisMap: Map<string | null, SatelliteAnalysis>): StatusFilter {
  const a = analysisMap.get(bow.id);
  if (a?.pool_detected && bow.pool_lat) return "pinned";
  if (a?.pool_detected) return "analyzed";
  return "not_analyzed";
}

function bestStatus(statuses: StatusFilter[]): StatusFilter {
  if (statuses.includes("pinned")) return "pinned";
  if (statuses.includes("analyzed")) return "analyzed";
  return "not_analyzed";
}

export default function MapPage() {
  const searchParams = useSearchParams();
  const initialBowId = searchParams.get("bow");
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
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set(["commercial", "residential"]));
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

  const loadData = useCallback(async () => {
    try {
      const [bows, allAnalyses, med] = await Promise.all([
        api.get<PoolBowWithCoords[]>("/v1/satellite/pool-bows"),
        api.get<SatelliteAnalysis[]>("/v1/satellite/all"),
        api.get<PortfolioMedians>("/v1/profitability/medians").catch(() => null),
      ]);
      setPoolBows(bows);
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

  const analysisMap = useMemo(() => new Map(analyses.map((a) => [a.body_of_water_id, a])), [analyses]);

  // Group BOWs by property
  const propertyGroups = useMemo((): PropertyGroup[] => {
    const groupMap = new Map<string, PropertyGroup>();
    for (const bow of poolBows) {
      let group = groupMap.get(bow.property_id);
      if (!group) {
        group = {
          property_id: bow.property_id,
          customer_id: bow.customer_id,
          customer_name: bow.customer_name,
          customer_type: bow.customer_type,
          address: bow.address,
          city: bow.city,
          lat: bow.lat,
          lng: bow.lng,
          tech_name: bow.tech_name,
          tech_color: bow.tech_color,
          bows: [],
          best_status: "not_analyzed",
        };
        groupMap.set(bow.property_id, group);
      }
      group.bows.push(bow);
    }
    // Compute best_status per property
    for (const group of groupMap.values()) {
      const statuses = group.bows.map((b) => getBowStatus(b, analysisMap));
      group.best_status = bestStatus(statuses);
    }
    return Array.from(groupMap.values());
  }, [poolBows, analysisMap]);

  // Auto-select on load
  const autoSelected = useRef(false);
  useEffect(() => {
    if (autoSelected.current || propertyGroups.length === 0) return;
    autoSelected.current = true;

    // URL param: find property containing that BOW
    if (initialBowId) {
      const pg = propertyGroups.find((g) => g.bows.some((b) => b.id === initialBowId));
      if (pg) {
        setShouldFlyTo(true);
        handlePropertySelect(pg.property_id);
        return;
      }
    }

    // Default: first commercial property, then first overall
    const sorted = [...propertyGroups].sort((a, b) => a.customer_name.localeCompare(b.customer_name));
    const first = sorted.find((g) => g.customer_type === "commercial") || sorted[0];
    if (first) selectPropertyQuiet(first.property_id);
  }, [propertyGroups, initialBowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedGroup = useMemo(() =>
    propertyGroups.find((g) => g.property_id === selectedPropertyId) || null,
    [propertyGroups, selectedPropertyId]
  );

  const toggleFilter = (f: StatusFilter) => {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  };

  const toggleType = (t: string) => {
    setTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const sortFn = useCallback((a: PropertyGroup, b: PropertyGroup) => {
    return a.customer_name.localeCompare(b.customer_name);
  }, []);

  const filteredGroups = useMemo(() => {
    return propertyGroups.filter((g) => {
      if (!typeFilter.has(g.customer_type)) return false;
      if (!statusFilters.has(g.best_status)) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return g.customer_name.toLowerCase().includes(q)
        || g.address.toLowerCase().includes(q)
        || g.city.toLowerCase().includes(q)
        || g.bows.some((b) => b.bow_name?.toLowerCase().includes(q));
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

  // Count helpers for section headers
  const countBows = (groups: PropertyGroup[]) => groups.reduce((sum, g) => sum + g.bows.length, 0);

  // Load images when property is selected (images are property-keyed)
  const loadImages = useCallback(async (propertyId: string) => {
    try {
      const imgs = await api.get<PropertyPhoto[]>(`/v1/photos/properties/${propertyId}`);
      setImages(imgs);
    } catch {
      setImages([]);
    }
  }, []);

  const loadPropertyDetail = useCallback(async (propertyId: string, bows: PoolBowWithCoords[]) => {
    setBowDetails(new Map());
    setPropDetail(null);
    setProfitData(null);
    setDimComparisons(new Map());
    setRateAllocation({});
    setChemicalCosts(new Map());
    setCostExpanded(false);

    const bowPromises = bows.map(async (b) => {
      const [bow, comparison] = await Promise.all([
        api.get<Record<string, unknown>>(`/v1/bodies-of-water/${b.id}`).catch(() => null),
        api.get<DimensionComparison>(`/v1/dimensions/bows/${b.id}/comparison`).catch(() => null),
      ]);
      return { bowId: b.id, bow, comparison };
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

    // Fetch chemical costs for each BOW in parallel
    const chemCostResults = await Promise.all(
      bows.map(async (b) => {
        const cc = await api.get<{ sanitizer_cost: number; acid_cost: number; cya_cost: number; salt_cost: number; cell_cost: number; insurance_cost: number; total_monthly: number; source: string }>(`/v1/chemical-costs/bows/${b.id}`).catch(() => null);
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
      if (r.bow) newBowDetails.set(r.bowId, r.bow);
      if (r.comparison) newDimComps.set(r.bowId, r.comparison);
    }
    setBowDetails(newBowDetails);
    setDimComparisons(newDimComps);

    // Reset perimeter states
    const newShapes = new Map<string, string>();
    for (const r of bowResults) {
      if (r.bow && (r.bow as { pool_shape?: string }).pool_shape) {
        newShapes.set(r.bowId, (r.bow as { pool_shape: string }).pool_shape);
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
      // Auto-activate BOW for single-pool properties (enables map click to place pin)
      setActiveBowId(group.bows.length === 1 ? group.bows[0].id : null);
      loadImages(propertyId);
      loadPropertyDetail(propertyId, group.bows);
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

  const handlePinPlace = useCallback((lat: number, lng: number) => {
    if (!canEdit || !selectedPropertyId) return;

    // Property move mode
    if (movingProperty) {
      setPropertyPinPosition({ lat, lng });
      return;
    }

    // Pool pin mode — auto-pick BOW: highlighted > active > first in group
    const group = propertyGroups.find((g) => g.property_id === selectedPropertyId);
    if (!group) return;
    const targetBow = highlightedBowId || activeBowId || group.bows[0]?.id;
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
        `/v1/satellite/bows/${activeBowId}/pin`,
        { pool_lat: pinPosition.lat, pool_lng: pinPosition.lng }
      );
      setAnalyses((prev) => {
        const idx = prev.findIndex((a) => a.body_of_water_id === activeBowId);
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
      // Update local state
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

  const saveMeasurements = async (bowId: string) => {
    const perimeterInput = perimeterInputs.get(bowId) || "";
    const perimeterShape = perimeterShapes.get(bowId) || "rectangle";
    const areaInput = areaInputs.get(bowId) || "";
    const volumeInput = volumeInputs.get(bowId) || "";
    const areaSqft = areaInput ? parseFloat(areaInput) : undefined;
    const volumeGal = volumeInput ? parseInt(volumeInput) : undefined;
    const ft = perimeterInput ? parseFloat(perimeterInput) : undefined;

    // Gather shape & structure fields
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
      // Save perimeter + area via dimension estimate (if perimeter provided)
      if (ft && ft > 0) {
        await api.post(`/v1/dimensions/bows/${bowId}/perimeter`, {
          perimeter_ft: ft,
          pool_shape: perimeterShape,
          ...(areaSqft && areaSqft > 0 ? { area_sqft: areaSqft } : {}),
        });
      } else if (areaSqft && areaSqft > 0) {
        // Area without perimeter — save directly to BOW
        await api.put(`/v1/bodies-of-water/${bowId}`, { pool_sqft: areaSqft, pool_shape: perimeterShape });
      }
      // Save volume directly to BOW
      if (volumeGal && volumeGal > 0) {
        await api.put(`/v1/bodies-of-water/${bowId}`, { pool_gallons: volumeGal });
      }
      // Save shape & structure fields + pool_shape to BOW
      if (hasShapeChanges || perimeterShape) {
        await api.put(`/v1/bodies-of-water/${bowId}`, { pool_shape: perimeterShape, ...shapeFields });
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
      // Refresh detail
      if (selectedGroup) {
        await loadPropertyDetail(selectedPropertyId!, selectedGroup.bows);
      }
    } catch {
      toast.error("Failed to save measurements");
    } finally {
      setSavingPerimeter(false);
    }
  };

  // Image operations
  const uploadPhoto = async (file: File) => {
    if (!selectedPropertyId) return;
    setCapturing(true);
    try {
      const resized = await resizeImage(file, 1600);
      const formData = new FormData();
      formData.append("photo", resized, file.name);
      if (activeBowId) formData.append("body_of_water_id", activeBowId);
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

  // Activate a BOW for pin placement
  const handleBowPinActivate = (bowId: string) => {
    if (activeBowId === bowId) {
      // Deactivate
      setActiveBowId(null);
      setPinPosition(null);
      setPinDirty(false);
    } else {
      setActiveBowId(bowId);
      setPinDirty(false);
      const bow = poolBows.find((b) => b.id === bowId);
      const analysis = analyses.find((a) => a.body_of_water_id === bowId);
      if (analysis?.pool_lat && analysis?.pool_lng) {
        setPinPosition({ lat: analysis.pool_lat, lng: analysis.pool_lng });
      } else if (bow?.pool_lat && bow?.pool_lng) {
        setPinPosition({ lat: bow.pool_lat, lng: bow.pool_lng });
      } else {
        setPinPosition(null);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const analyzedCount = analyses.filter((a) => a.pool_detected).length;
  const totalBowCount = poolBows.length;

  const renderSourceBadge = (source: string | null | undefined) => {
    if (!source) return null;
    const label = SOURCE_LABELS[source] || source;
    const colorClass = SOURCE_COLORS[source] || "bg-gray-100 text-gray-600";
    return (
      <Badge className={`${colorClass} text-[9px] px-1 py-0 leading-tight font-medium hover:${colorClass.split(" ")[0]}`}>
        {label}
      </Badge>
    );
  };

  // Render a single BOW tile in the detail panel
  const renderBowTile = (bow: PoolBowWithCoords, bowDetail: Record<string, unknown> | null, dimComparison: DimensionComparison | null) => {
    const analysis = analysisMap.get(bow.id) || null;
    const isBowActive = activeBowId === bow.id;
    const perimeterInput = perimeterInputs.get(bow.id) || "";
    const perimeterShape = perimeterShapes.get(bow.id) || "rectangle";
    const isMeasuring = measuringPerimeterBow === bow.id;

    return (
      <Card key={bow.id} id={`bow-tile-${bow.id}`} className={`shadow-sm border-l-4 cursor-pointer ${isBowActive ? "border-l-primary" : highlightedBowId === bow.id ? "border-l-amber-400" : "border-l-blue-500"}`} onClick={() => setHighlightedBowId(bow.id)}>
        <CardContent className="p-4 space-y-3">
          {/* Pool header */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-baseline gap-3">
                <div className="flex items-center gap-2">
                  {waterTypeIcon(bow.water_type, "h-3.5 w-3.5 text-blue-500")}
                  <span className="text-base font-semibold">{bow.bow_name || bow.water_type.replace("_", " ")}</span>
                </div>
                <span className="text-muted-foreground/30">·</span>
                {bowDetail && (
                  <span className="text-base font-bold">{(bowDetail as { estimated_service_minutes: number }).estimated_service_minutes}<span className="text-[10px] font-normal text-muted-foreground ml-0.5">min</span></span>
                )}
                {perms.canViewRates && (() => {
                  const alloc = rateAllocation[bow.id];
                  const bowRate = (bowDetail as { monthly_rate?: number })?.monthly_rate;
                  const rate = bowRate || alloc?.allocated_rate || null;
                  const margin = profitData ? (profitData as { cost_breakdown: { margin_pct: number } }).cost_breakdown?.margin_pct : null;
                  const ALLOC_LABELS: Record<string, string> = { gallons: "vol", sqft: "area", service_time: "time", type_weight: "type", sole: "" };
                  return (<>
                    <span className="text-muted-foreground/30">·</span>
                    <span className={`text-base font-bold ${
                      rate
                        ? margin !== null
                          ? margin >= 30 ? "text-emerald-600" : margin >= 0 ? "text-amber-600" : "text-red-600"
                          : "text-foreground"
                        : "text-muted-foreground/40"
                    }`}>
                      {rate ? `$${rate.toFixed(0)}` : "$\u2014"}<span className="text-[10px] font-normal text-muted-foreground ml-0.5">/mo</span>
                    </span>
                    {alloc && alloc.allocation_method !== "sole" && (
                      <span className="text-[9px] text-muted-foreground/50" title={`Allocated by ${alloc.allocation_method} (${(alloc.weight * 100).toFixed(0)}%)`}>
                        ({ALLOC_LABELS[alloc.allocation_method] || alloc.allocation_method})
                      </span>
                    )}
                  </>);
                })()}
              </div>
            </div>
          </div>

          {/* Pin dirty banner */}
          {isBowActive && canEdit && pinDirty && (
            <div className="rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-700 px-3 py-2 flex items-center justify-between">
              <span className="text-xs text-amber-700 dark:text-amber-400 font-medium">Pin moved — save to keep new location</span>
              <Button size="sm" className="h-7 px-3 text-xs" disabled={savingPin} onClick={savePin}>
                {savingPin ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Pin"}
              </Button>
            </div>
          )}

          {/* Discrepancy alert */}
          {dimComparison && dimComparison.discrepancy_level && dimComparison.discrepancy_level !== "ok" && !dismissedDiscrepancies.has(bow.id) && (() => {
            const e1 = dimComparison.estimates[0];
            const e2 = dimComparison.estimates[1];
            const desc = e1 && e2
              ? `${e1.estimated_sqft?.toLocaleString() ?? "?"} ft² (${SOURCE_LABELS[e1.source] || e1.source}) vs ${e2.estimated_sqft?.toLocaleString() ?? "?"} ft² (${SOURCE_LABELS[e2.source] || e2.source})`
              : "estimates";
            const isAlert = dimComparison.discrepancy_level === "alert";
            return (
              <div className={`rounded-md p-2.5 flex items-start gap-2 ${
                isAlert
                  ? "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800"
                  : "bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800"
              }`}>
                <AlertTriangle className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${isAlert ? "text-red-600" : "text-amber-600"}`} />
                <div className="flex-1 text-[11px]">
                  <span className={`font-medium ${isAlert ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"}`}>
                    {dimComparison.discrepancy_pct?.toFixed(0)}% discrepancy — {desc}
                  </span>
                </div>
                <button
                  onClick={() => setDismissedDiscrepancies((prev) => {
                    const next = new Set(prev).add(bow.id);
                    try { localStorage.setItem("qp_dismissed_discrepancies", JSON.stringify([...next])); } catch {}
                    return next;
                  })}
                  className={`shrink-0 ${isAlert ? "text-red-400 hover:text-red-600" : "text-amber-400 hover:text-amber-600"}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })()}

          {/* Measurements + Equipment */}
          {bowDetail && perms.canViewDimensions && (
            <div className="grid grid-cols-2 gap-2">
              {/* Measurements */}
              <div className={`bg-muted/50 rounded-md overflow-hidden ${isMeasuring ? "border-l-3 border-l-primary" : ""}`}>
                <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                  <Ruler className="h-3 w-3 text-muted-foreground" />
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Measurements</span>
                  {canEdit && (
                    <button
                      className={`ml-auto transition-colors ${isMeasuring ? "text-primary" : "text-muted-foreground/40 hover:text-muted-foreground"}`}
                      onClick={() => setMeasuringPerimeterBow(isMeasuring ? null : bow.id)}
                      title={isMeasuring ? "Close edit" : "Edit measurements"}
                    >
                      {isMeasuring ? <X className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                    </button>
                  )}
                </div>
                <div className="px-2.5 py-2 space-y-1">
                  {/* Area + source */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Area</span>
                    <div className="flex items-center gap-1.5">
                      {isMeasuring ? (
                        <div className="flex items-center gap-1">
                          <Input
                            type="number"
                            placeholder="ft²"
                            value={areaInputs.get(bow.id) ?? ((bowDetail as { pool_sqft?: number }).pool_sqft?.toString() || "")}
                            onChange={(e) => setAreaInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.value); return n; })}
                            className="h-6 w-20 text-[11px] px-1.5"
                            min={0}
                            step={1}
                          />
                          <span className="text-muted-foreground">ft²</span>
                        </div>
                      ) : (
                        <>
                          {(bowDetail as { pool_sqft?: number }).pool_sqft
                            ? <span className="font-semibold">{((bowDetail as { pool_sqft: number }).pool_sqft).toLocaleString()} ft²</span>
                            : <span className="text-muted-foreground/50 italic">—</span>}
                          {renderSourceBadge((bowDetail as { dimension_source?: string }).dimension_source)}
                        </>
                      )}
                    </div>
                  </div>
                  {/* Volume */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Volume</span>
                    {isMeasuring ? (
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          placeholder="gal"
                          value={volumeInputs.get(bow.id) ?? ((bowDetail as { pool_gallons?: number }).pool_gallons?.toString() || "")}
                          onChange={(e) => setVolumeInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.value); return n; })}
                          className="h-6 w-20 text-[11px] px-1.5"
                          min={0}
                          step={100}
                        />
                        <span className="text-muted-foreground">gal</span>
                      </div>
                    ) : (
                      (bowDetail as { pool_gallons?: number }).pool_gallons
                        ? <span className="font-medium">{((bowDetail as { pool_gallons: number }).pool_gallons).toLocaleString()} gal</span>
                        : <span className="text-muted-foreground/50 italic">—</span>
                    )}
                  </div>
                  {/* Perimeter */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Perimeter</span>
                    {isMeasuring ? (
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          placeholder="ft"
                          value={perimeterInput || ((bowDetail as { perimeter_ft?: number }).perimeter_ft?.toString() || "")}
                          onChange={(e) => setPerimeterInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.value); return n; })}
                          className="h-6 w-20 text-[11px] px-1.5"
                          min={0}
                          step={0.1}
                        />
                        <span className="text-muted-foreground">ft</span>
                      </div>
                    ) : (
                      (bowDetail as { perimeter_ft?: number }).perimeter_ft
                        ? <span className="font-medium">{(bowDetail as { perimeter_ft: number }).perimeter_ft} ft</span>
                        : <span className="text-muted-foreground/50 italic">—</span>
                    )}
                  </div>
                  {/* Shape & Structure */}
                  <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70 pt-1.5 mt-1.5 border-t border-border/50">Shape & Structure</p>
                  {/* Shape */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Shape</span>
                    {isMeasuring ? (
                      <select
                        value={perimeterShape}
                        onChange={(e) => setPerimeterShapes((prev) => { const n = new Map(prev); n.set(bow.id, e.target.value); return n; })}
                        className="h-6 text-[11px] rounded border border-input bg-background px-1.5"
                      >
                        {POOL_SHAPES.map((s) => (
                          <option key={s.value} value={s.value}>{s.label}</option>
                        ))}
                      </select>
                    ) : (
                      (bowDetail as { pool_shape?: string }).pool_shape
                        ? <span className="font-medium capitalize">{(bowDetail as { pool_shape: string }).pool_shape.replace(/_/g, " ")}</span>
                        : <span className="text-muted-foreground/50 italic">—</span>
                    )}
                  </div>
                  {/* Rounded corners — only for rectangle/irregular_rectangle */}
                  {(perimeterShape === "rectangle" || perimeterShape === "irregular_rectangle") && (
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="text-muted-foreground">Rounded corners</span>
                      {isMeasuring ? (
                        <input
                          type="checkbox"
                          checked={roundedCornersInputs.get(bow.id) ?? (bowDetail as { has_rounded_corners?: boolean }).has_rounded_corners ?? false}
                          onChange={(e) => setRoundedCornersInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.checked); return n; })}
                          className="h-3.5 w-3.5 accent-primary"
                        />
                      ) : (
                        <span className="font-medium">{(bowDetail as { has_rounded_corners?: boolean }).has_rounded_corners ? "Yes" : "No"}</span>
                      )}
                    </div>
                  )}
                  {/* Step entries */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Step entries</span>
                    {isMeasuring ? (
                      <Input
                        type="number"
                        placeholder="0"
                        value={stepEntryInputs.get(bow.id) ?? (bowDetail as { step_entry_count?: number }).step_entry_count ?? 0}
                        onChange={(e) => setStepEntryInputs((prev) => { const n = new Map(prev); n.set(bow.id, parseInt(e.target.value) || 0); return n; })}
                        className="h-6 w-14 text-[11px] px-1.5"
                        min={0}
                        max={4}
                        step={1}
                      />
                    ) : (
                      <span className="font-medium">{(bowDetail as { step_entry_count?: number }).step_entry_count || 0}</span>
                    )}
                  </div>
                  {/* Bench/sun shelf */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Bench/sun shelf</span>
                    {isMeasuring ? (
                      <input
                        type="checkbox"
                        checked={benchShelfInputs.get(bow.id) ?? (bowDetail as { has_bench_shelf?: boolean }).has_bench_shelf ?? false}
                        onChange={(e) => setBenchShelfInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.checked); return n; })}
                        className="h-3.5 w-3.5 accent-primary"
                      />
                    ) : (
                      <span className="font-medium">{(bowDetail as { has_bench_shelf?: boolean }).has_bench_shelf ? "Yes" : "No"}</span>
                    )}
                  </div>
                  {/* Shallow depth */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Shallow depth</span>
                    {isMeasuring ? (
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          placeholder="ft"
                          value={shallowDepthInputs.get(bow.id) ?? ((bowDetail as { pool_depth_shallow?: number }).pool_depth_shallow?.toString() || "")}
                          onChange={(e) => setShallowDepthInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.value); return n; })}
                          className="h-6 w-16 text-[11px] px-1.5"
                          min={0}
                          max={12}
                          step={0.5}
                        />
                        <span className="text-muted-foreground">ft</span>
                      </div>
                    ) : (
                      (bowDetail as { pool_depth_shallow?: number }).pool_depth_shallow
                        ? <span className="font-medium">{(bowDetail as { pool_depth_shallow: number }).pool_depth_shallow} ft</span>
                        : <span className="text-muted-foreground/50 italic">—</span>
                    )}
                  </div>
                  {/* Deep depth */}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-muted-foreground">Deep depth</span>
                    {isMeasuring ? (
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          placeholder="ft"
                          value={deepDepthInputs.get(bow.id) ?? ((bowDetail as { pool_depth_deep?: number }).pool_depth_deep?.toString() || "")}
                          onChange={(e) => setDeepDepthInputs((prev) => { const n = new Map(prev); n.set(bow.id, e.target.value); return n; })}
                          className="h-6 w-16 text-[11px] px-1.5"
                          min={0}
                          max={15}
                          step={0.5}
                        />
                        <span className="text-muted-foreground">ft</span>
                      </div>
                    ) : (
                      (bowDetail as { pool_depth_deep?: number }).pool_depth_deep
                        ? <span className="font-medium">{(bowDetail as { pool_depth_deep: number }).pool_depth_deep} ft</span>
                        : <span className="text-muted-foreground/50 italic">—</span>
                    )}
                  </div>
                  {/* Surface & Structure */}
                  <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70 pt-1.5 mt-1.5 border-t border-border/50">Surface & Structure</p>
                  {[
                    { label: "Surface", value: (bowDetail as { pool_surface?: string }).pool_surface?.replace(/_/g, " ") || null },
                    { label: "Cover", value: (bowDetail as { pool_cover_type?: string }).pool_cover_type?.replace(/_/g, " ") || null },
                    { label: "Skimmers", value: (bowDetail as { skimmer_count?: number }).skimmer_count != null ? String((bowDetail as { skimmer_count: number }).skimmer_count) : null },
                  ].map((d) => (
                    <div key={d.label} className="flex justify-between text-[11px]">
                      <span className="text-muted-foreground">{d.label}</span>
                      {d.value ? <span className="font-medium capitalize">{d.value}</span> : <span className="text-muted-foreground/50 italic">—</span>}
                    </div>
                  ))}
                  {/* Edit mode: Save + Google Maps link */}
                  {isMeasuring && canEdit && (
                    <div className="flex items-center justify-between pt-1.5 border-t border-border/50 mt-1.5">
                      {(bow.pool_lat || (bow.lat && bow.lng)) ? (
                        <a
                          href={`https://www.google.com/maps/@${(bow.pool_lat ?? bow.lat)},${(bow.pool_lng ?? bow.lng)},20z/data=!3m1!1e3`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                        >
                          <ExternalLink className="h-2.5 w-2.5" />
                          Measure in Google Maps
                        </a>
                      ) : <span />}
                      <Button
                        size="sm"
                        className="h-6 px-3 text-[11px]"
                        disabled={savingPerimeter || (!perimeterInput && !areaInputs.get(bow.id) && !volumeInputs.get(bow.id) && !roundedCornersInputs.has(bow.id) && !stepEntryInputs.has(bow.id) && !benchShelfInputs.has(bow.id) && !shallowDepthInputs.has(bow.id) && !deepDepthInputs.has(bow.id))}
                        onClick={() => saveMeasurements(bow.id)}
                      >
                        {savingPerimeter ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Pool & Equipment */}
              <div className="bg-muted/50 rounded-md overflow-hidden">
                <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2.5 py-1">
                  <Wrench className="h-3 w-3 text-muted-foreground" />
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Equipment & Plumbing</span>
                </div>
                <div className="px-2.5 py-2 space-y-3">
                  {/* Plumbing & Drains */}
                  <div className="space-y-1">
                    <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">Plumbing & Drains</p>
                    {[
                      { icon: Pipette, label: "Plumbing", value: (bowDetail as Record<string, unknown>).plumbing_size_inches != null ? `${(bowDetail as Record<string, unknown>).plumbing_size_inches} in` : undefined },
                      { icon: Droplets, label: "Fill", value: (bowDetail as Record<string, unknown>).fill_method as string | undefined },
                      { icon: CircleDot, label: "Drain type", value: (bowDetail as Record<string, unknown>).drain_type as string | undefined },
                      { icon: CircleDot, label: "Drain method", value: (bowDetail as Record<string, unknown>).drain_method as string | undefined },
                      { icon: CircleDot, label: "Drains", value: (bowDetail as Record<string, unknown>).drain_count != null ? String((bowDetail as Record<string, unknown>).drain_count) : undefined },
                      { icon: Clock, label: "Turnover", value: (bowDetail as Record<string, unknown>).turnover_hours != null ? `${(bowDetail as Record<string, unknown>).turnover_hours} hrs` : undefined },
                    ].map((e) => (
                      <div key={e.label} className="flex items-center gap-1.5 text-[11px]">
                        <e.icon className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground">{e.label}</span>
                        <span className="truncate ml-auto">
                          {e.value ? <span className="font-medium capitalize">{e.value.replace(/_/g, " ")}</span> : <span className="text-muted-foreground/50 italic">—</span>}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Drain Covers */}
                  {((bowDetail as Record<string, unknown>).drain_cover_compliant != null || (bowDetail as Record<string, unknown>).equalizer_cover_compliant != null) && (
                    <div className="space-y-1">
                      <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">Drain Covers</p>
                      {(bowDetail as Record<string, unknown>).drain_cover_compliant != null && (
                        <div className="text-[11px] space-y-0.5">
                          <div className="flex items-center gap-1.5">
                            <Shield className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                            <span className="text-muted-foreground">Drain covers</span>
                            <Badge className={`ml-auto text-[9px] px-1 py-0 ${(bowDetail as Record<string, unknown>).drain_cover_compliant ? "bg-green-100 text-green-800 hover:bg-green-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                              {(bowDetail as Record<string, unknown>).drain_cover_compliant ? "Compliant" : "Non-compliant"}
                            </Badge>
                          </div>
                          {!!((bowDetail as Record<string, unknown>).drain_cover_install_date || (bowDetail as Record<string, unknown>).drain_cover_expiry_date) && (
                            <p className="text-[10px] text-muted-foreground pl-4">
                              {!!(bowDetail as Record<string, unknown>).drain_cover_install_date && `Installed: ${new Date(String((bowDetail as Record<string, unknown>).drain_cover_install_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                              {!!(bowDetail as Record<string, unknown>).drain_cover_install_date && !!(bowDetail as Record<string, unknown>).drain_cover_expiry_date && " · "}
                              {!!(bowDetail as Record<string, unknown>).drain_cover_expiry_date && `Expires: ${new Date(String((bowDetail as Record<string, unknown>).drain_cover_expiry_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                            </p>
                          )}
                        </div>
                      )}
                      {(bowDetail as Record<string, unknown>).equalizer_cover_compliant != null && (
                        <div className="text-[11px] space-y-0.5">
                          <div className="flex items-center gap-1.5">
                            <Shield className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                            <span className="text-muted-foreground">Equalizer covers</span>
                            <Badge className={`ml-auto text-[9px] px-1 py-0 ${(bowDetail as Record<string, unknown>).equalizer_cover_compliant ? "bg-green-100 text-green-800 hover:bg-green-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                              {(bowDetail as Record<string, unknown>).equalizer_cover_compliant ? "Compliant" : "Non-compliant"}
                            </Badge>
                          </div>
                          {!!((bowDetail as Record<string, unknown>).equalizer_cover_install_date || (bowDetail as Record<string, unknown>).equalizer_cover_expiry_date) && (
                            <p className="text-[10px] text-muted-foreground pl-4">
                              {!!(bowDetail as Record<string, unknown>).equalizer_cover_install_date && `Installed: ${new Date(String((bowDetail as Record<string, unknown>).equalizer_cover_install_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                              {!!(bowDetail as Record<string, unknown>).equalizer_cover_install_date && !!(bowDetail as Record<string, unknown>).equalizer_cover_expiry_date && " · "}
                              {!!(bowDetail as Record<string, unknown>).equalizer_cover_expiry_date && `Expires: ${new Date(String((bowDetail as Record<string, unknown>).equalizer_cover_expiry_date)).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Equipment */}
                  <div className="space-y-1">
                    <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">Equipment</p>
                    {[
                      { icon: Gauge, label: "Pump", value: (bowDetail as Record<string, unknown>).pump_type as string | undefined },
                      { icon: FlaskConical, label: "Filter", value: (bowDetail as Record<string, unknown>).filter_type as string | undefined },
                      { icon: Thermometer, label: "Heater", value: (bowDetail as Record<string, unknown>).heater_type as string | undefined },
                      { icon: FlaskConical, label: "Chlor.", value: (bowDetail as Record<string, unknown>).chlorinator_type as string | undefined },
                      { icon: Zap, label: "Auto", value: (bowDetail as Record<string, unknown>).automation_system as string | undefined },
                      { icon: Calendar, label: "Year", value: (bowDetail as Record<string, unknown>).equipment_year != null ? String((bowDetail as Record<string, unknown>).equipment_year) : undefined },
                      { icon: MapPin, label: "Location", value: (bowDetail as Record<string, unknown>).equipment_pad_location as string | undefined },
                    ].map((e) => (
                      <div key={e.label} className="flex items-center gap-1.5 text-[11px]">
                        <e.icon className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground">{e.label}</span>
                        <span className="truncate ml-auto">
                          {e.value ? <span className="font-medium">{e.value}</span> : <span className="text-muted-foreground/50 italic">—</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Aerial analysis */}
          {analysis && !analysis.error_message && analysis.pool_detected && (
            <div className="rounded-md bg-muted/50 p-2.5 space-y-1.5">
              <div className="flex items-center gap-2 flex-wrap text-xs">
                <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100 text-[10px]">Aerial</Badge>
                <Badge className={`text-[10px] ${analysis.pool_confidence >= 0.7 ? "bg-green-100 text-green-800 hover:bg-green-100" : analysis.pool_confidence >= 0.4 ? "bg-yellow-100 text-yellow-800 hover:bg-yellow-100" : "bg-red-100 text-red-800 hover:bg-red-100"}`}>
                  {(analysis.pool_confidence * 100).toFixed(0)}%
                </Badge>
                <span className="text-[10px] text-muted-foreground ml-auto">
                  Veg {analysis.vegetation_pct}% · Canopy {analysis.canopy_overhang_pct}% · Shadow {analysis.shadow_pct}%
                </span>
              </div>
            </div>
          )}
          {analysis?.error_message && (
            <div className="rounded-md bg-destructive/5 p-2.5">
              <Badge variant="destructive" className="text-[10px]">Analysis Error</Badge>
              <p className="text-[11px] text-muted-foreground mt-1">{analysis.error_message}</p>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-3">
      {/* Mode switcher + actions bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
          {MAP_MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                mode === m.key
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <m.Icon className="h-3.5 w-3.5" />
              {m.label}
            </button>
          ))}
        </div>

        {mode === "pools" && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {analyzedCount}/{totalBowCount} analyzed
            </span>
          </div>
        )}
      </div>

      {/* 3-Column Layout: List | Map | Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" style={{ height: "calc(100vh - 140px)", minHeight: 500 }}>
        {/* Left Panel */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
        {mode === "pools" ? (<>
          {/* Search + type toggles */}
          <div className="flex items-center gap-1.5 mb-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-8 text-sm"
              />
            </div>
            <Button
              variant={typeFilter.has("commercial") ? "default" : "outline"}
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => toggleType("commercial")}
              title="Commercial"
            >
              <Building2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant={typeFilter.has("residential") ? "default" : "outline"}
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => toggleType("residential")}
              title="Residential"
            >
              <Home className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Property list — commercial first */}
          <div ref={listRef} className="flex-1 overflow-y-auto space-y-0 pr-1">
            {[
              { label: "Commercial", Icon: Building2, items: commercialGroups, show: typeFilter.has("commercial") },
              { label: "Residential", Icon: Home, items: residentialGroups, show: typeFilter.has("residential") },
            ].map((section) => section.show && section.items.length > 0 && (
              <div key={section.label}>
                <div className="flex items-center gap-2 px-1 pt-3 pb-1.5 mb-0.5 sticky top-0 z-10 bg-background border-b border-border">
                  <section.Icon className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{section.label}</span>
                  <span className="text-[11px] text-muted-foreground/50">
                    {section.items.length}
                    {countBows(section.items) !== section.items.length && (
                      <> ({countBows(section.items)} features)</>
                    )}
                  </span>
                  <div className="flex-1 border-t border-border ml-1" />
                </div>
                <div className="space-y-0.5 mb-2">
                  {section.items.map((g) => {
                    const isSelected = g.property_id === selectedPropertyId;
                    return (
                      <div key={g.property_id}>
                        <button
                          id={`prop-${g.property_id}`}
                          onClick={() => { handlePropertySelect(g.property_id); setHighlightedBowId(null); }}
                          className={`w-full text-left rounded-md px-3 py-2 text-sm transition-colors ${
                            isSelected
                              ? "bg-accent border-l-3 border-l-primary font-medium"
                              : "hover:bg-muted"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
                                g.best_status === "pinned"
                                  ? "bg-green-500"
                                  : g.best_status === "analyzed"
                                  ? "bg-yellow-500"
                                  : "bg-red-500"
                              }`}
                            />
                            <span className="font-medium truncate flex-1">
                              {g.customer_name}
                            </span>
                            {g.bows.length > 1 && (
                              <Badge variant="secondary" className="text-[9px] px-1.5 py-0 shrink-0">
                                {g.bows.length}
                              </Badge>
                            )}
                          </div>
                          <div className="text-xs truncate ml-4 text-muted-foreground">
                            {g.address}
                          </div>
                          {g.city && (
                            <div className="text-xs truncate ml-4 text-muted-foreground/70">
                              {g.city}
                            </div>
                          )}
                          {g.tech_name && (
                            <div className="text-xs truncate ml-4 text-muted-foreground flex items-center gap-1.5">
                              <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: g.tech_color || '#94a3b8' }} />
                              {g.tech_name}
                            </div>
                          )}
                        </button>
                        {/* Child BOW entries — show when selected and multi-BOW */}
                        {isSelected && g.bows.length > 1 && (
                          <div className="ml-6 border-l-2 border-border pl-2 py-1 space-y-0.5">
                            {g.bows.map((b) => (
                              <button
                                key={b.id}
                                onClick={() => {
                                  setHighlightedBowId(b.id);
                                  setTimeout(() => {
                                    document.getElementById(`bow-tile-${b.id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                                  }, 50);
                                }}
                                className={`w-full text-left rounded px-2 py-1 text-xs transition-colors ${
                                  highlightedBowId === b.id
                                    ? "bg-accent font-medium"
                                    : "hover:bg-muted text-muted-foreground"
                                }`}
                              >
                                <div className="flex items-center gap-1.5">
                                  {waterTypeIcon(b.water_type, "h-2.5 w-2.5 text-blue-500 shrink-0")}
                                  <span className="truncate">{b.bow_name || b.water_type.replace("_", " ")}</span>
                                </div>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
            {filteredGroups.length === 0 && (
              <div className="text-center py-6 text-sm text-muted-foreground">No matching properties</div>
            )}
          </div>
          <div className="text-[11px] text-muted-foreground pt-1 border-t mt-1">
            {filteredGroups.length} of {propertyGroups.length} properties shown
          </div>
        </>) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
            {mode === "routes" ? "Route list coming soon" : "Customer list coming soon"}
          </div>
        )}
        </div>

        {/* Center: Map */}
        <div className="lg:col-span-5 min-h-0 relative">
          <Card className="shadow-sm overflow-hidden h-full">
            <SatelliteMap
              propertyGroups={filteredGroups}
              selectedPropertyId={selectedPropertyId}
              pinPosition={movingProperty ? propertyPinPosition : pinPosition}
              flyTo={shouldFlyTo}
              actionsRef={mapActionsRef}
              onPropertySelect={handlePropertySelect}
              onPinPlace={handlePinPlace}
              onZoomChange={setMapZoom}
            />
          </Card>
          {/* Zoom overlay */}
          {selectedPropertyId && (
            <button
              onClick={() => {
                const zoom = mapActionsRef.current?.getZoom() ?? 12;
                if (zoom >= 17) {
                  mapActionsRef.current?.zoomOut();
                  if (!pinDirty) {
                    setPinPosition(null);
                  }
                } else {
                  mapActionsRef.current?.zoomIn();
                }
              }}
              className="absolute top-3 right-3 z-[400] flex items-center gap-1.5 bg-background/90 backdrop-blur-sm rounded-md px-2.5 py-1.5 shadow-md border text-xs font-medium text-foreground hover:bg-background transition-colors"
            >
              {mapZoom >= 17 ? <ZoomOut className="h-3.5 w-3.5" /> : <ZoomIn className="h-3.5 w-3.5" />}
              {mapZoom >= 17 ? "Zoom Out" : "Zoom In"}
            </button>
          )}

          {/* Status filter overlay */}
          <div className="absolute bottom-3 left-3 z-[400] flex items-center gap-1 bg-background/90 backdrop-blur-sm rounded-md px-2 py-1.5 shadow-md border">
            {([
              { value: "analyzed" as StatusFilter, label: "Analyzed", color: "bg-yellow-500" },
              { value: "pinned" as StatusFilter, label: "Pinned", color: "bg-green-500" },
              { value: "not_analyzed" as StatusFilter, label: "Pending", color: "bg-red-500" },
            ]).map((f) => (
              <button
                key={f.value}
                onClick={() => toggleFilter(f.value)}
                className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors select-none ${
                  statusFilters.has(f.value)
                    ? "font-medium text-foreground"
                    : "text-muted-foreground/50 line-through"
                }`}
              >
                <span className={`inline-block w-2 h-2 rounded-full ${f.color} ${!statusFilters.has(f.value) ? "opacity-30" : ""}`} />
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Details Panel */}
        <div className="lg:col-span-4 min-h-0 overflow-y-auto">
          {mode !== "pools" ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              {mode === "routes" ? "Route details coming soon" : "Profitability details coming soon"}
            </div>
          ) : selectedGroup ? (
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
                        {selectedGroup.bows.length > 1 && (
                          <Badge variant="secondary" className="text-[9px] px-1 py-0">{selectedGroup.bows.length} features</Badge>
                        )}
                      </div>
                      {canEdit && (
                        <button
                          onClick={() => { setMovingProperty(!movingProperty); setPropertyPinPosition(null); setPinPosition(null); setPinDirty(false); }}
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
                                <Button size="sm" className="h-5 px-2 text-[10px]" disabled={savingPropertyPin} onClick={savePropertyLocation}>
                                  {savingPropertyPin ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                                </Button>
                                <Button size="sm" variant="ghost" className="h-5 px-2 text-[10px]" onClick={() => { setMovingProperty(false); setPropertyPinPosition(null); }}>
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

                        const compare = (val: number | null, med: number | null | undefined, higherIsGood: boolean) => {
                          if (val == null || med == null || med === 0) return null;
                          const pct = ((val - med) / med) * 100;
                          if (Math.abs(pct) < 5) return { arrow: "~", color: "text-muted-foreground", tip: `median ${med.toFixed(1)}` };
                          const above = pct > 0;
                          const good = higherIsGood ? above : !above;
                          return {
                            arrow: above ? "↑" : "↓",
                            color: good ? "text-emerald-600" : "text-red-500",
                            tip: `${above ? "+" : ""}${pct.toFixed(0)}% vs median`,
                          };
                        };

                        const metrics = [
                          { label: "Rate/gal", value: rpg ? `${(rpg * 100).toFixed(1)}¢` : null, medianLabel: m?.rate_per_gallon ? `${(m.rate_per_gallon * 100).toFixed(1)}¢` : null, color: "text-foreground", cmp: compare(rpg ? rpg * 100 : null, m?.rate_per_gallon ? m.rate_per_gallon * 100 : null, true), editable: false, expandable: false },
                          { label: "Est. Cost", value: `$${cost.total_cost.toFixed(0)}`, medianLabel: m ? `$${m.cost.toFixed(0)}` : null, color: "text-muted-foreground", cmp: compare(cost.total_cost, m?.cost, false), editable: false, expandable: true },
                          { label: "Margin", value: `${cost.margin_pct.toFixed(1)}%`, medianLabel: m ? `${m.margin_pct.toFixed(1)}%` : null, color: cost.margin_pct >= 30 ? "text-emerald-600" : cost.margin_pct >= 0 ? "text-amber-600" : "text-red-600", cmp: compare(cost.margin_pct, m?.margin_pct, true), editable: false, expandable: false },
                          { label: "Diff", value: `${diff.toFixed(1)}`, medianLabel: m ? `${m.difficulty.toFixed(1)}` : null, color: diff > 3.5 ? "text-red-600" : diff > 2.5 ? "text-amber-600" : "text-muted-foreground", cmp: compare(diff, m?.difficulty, false), editable: true, expandable: false },
                        ];

                        // Sum chemical costs across all BOWs
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
                                  onClick={mt.expandable ? () => setCostExpanded(!costExpanded) : undefined}
                                >
                                  <div className="flex items-center justify-between">
                                    <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{mt.label}</p>
                                    {mt.expandable && (
                                      costExpanded
                                        ? <ChevronUp className="h-2.5 w-2.5 text-muted-foreground" />
                                        : <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" />
                                    )}
                                    {mt.editable && canEdit && selectedPropertyId && (
                                      <button className="text-muted-foreground hover:text-foreground" onClick={(e) => { e.stopPropagation(); setDiffModalOpen(true); }}>
                                        <Pencil className="h-2.5 w-2.5" />
                                      </button>
                                    )}
                                  </div>
                                  <div className="flex items-baseline gap-1">
                                    {mt.cmp ? (
                                      <>
                                        <p className={`text-sm font-bold leading-tight ${mt.cmp.color}`}>{mt.value ?? "—"}</p>
                                        <span className={`text-[10px] font-bold ${mt.cmp.color}`}>
                                          {mt.cmp.arrow === "~" ? "·" : mt.cmp.arrow === "↑" ? "▲" : "▼"}
                                        </span>
                                        {mt.medianLabel && (
                                          <span className="text-[9px] text-muted-foreground/50">/ {mt.medianLabel}</span>
                                        )}
                                      </>
                                    ) : (
                                      <p className={`text-sm font-bold leading-tight ${mt.color}`}>{mt.value ?? "—"}</p>
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

              {/* BOW tiles — one per pool at this property */}
              {selectedGroup.bows.map((bow) =>
                renderBowTile(bow, bowDetails.get(bow.id) || null, dimComparisons.get(bow.id) || null)
              )}

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
                            if (file) uploadPhoto(file);
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
                              <Button variant="secondary" size="icon" className="h-5 w-5 bg-white/90 hover:bg-white shadow-sm" onClick={() => setHero(img.id)} title="Set as hero">
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
                                  <AlertDialogAction onClick={() => deleteImage(img.id)}>Delete</AlertDialogAction>
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
          bowDetail={selectedGroup?.bows[0] ? (bowDetails.get(selectedGroup.bows[0].id) || null) : null}
          onSaved={() => {
            if (selectedPropertyId && selectedGroup) {
              loadPropertyDetail(selectedPropertyId, selectedGroup.bows);
            }
          }}
        />
      )}
    </div>
  );
}
