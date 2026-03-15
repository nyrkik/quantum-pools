"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
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
  RefreshCw,
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
} from "lucide-react";
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
import type { SatelliteAnalysis, PoolBowWithCoords, BulkAnalysisResponse } from "@/types/satellite";
import type { PropertyPhoto } from "@/types/photo";
import { resizeImage } from "@/lib/image-utils";
import SatelliteMap from "@/components/maps/satellite-map";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://100.121.52.15:7061";

type StatusFilter = "analyzed" | "pinned" | "not_analyzed";
type MapMode = "pools" | "routes" | "profitability";

const MAP_MODES = [
  { key: "pools" as MapMode, label: "Pools", Icon: Droplets },
  { key: "routes" as MapMode, label: "Routes", Icon: Route },
  { key: "profitability" as MapMode, label: "Profitability", Icon: TrendingUp },
];

export default function MapPage() {
  const searchParams = useSearchParams();
  const initialBowId = searchParams.get("bow");
  const [mode, setMode] = useState<MapMode>("pools");
  const [poolBows, setPoolBows] = useState<PoolBowWithCoords[]>([]);
  const [analyses, setAnalyses] = useState<SatelliteAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedBowId, setSelectedBowId] = useState<string | null>(null);
  const [pinPosition, setPinPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [savingPin, setSavingPin] = useState(false);
  const [analyzingOne, setAnalyzingOne] = useState(false);
  const [search, setSearch] = useState("");
  const [images, setImages] = useState<PropertyPhoto[]>([]);
  const [capturing, setCapturing] = useState(false);
  const [statusFilters, setStatusFilters] = useState<Set<StatusFilter>>(new Set(["analyzed", "pinned", "not_analyzed"]));
  const [shouldFlyTo, setShouldFlyTo] = useState(false);
  const [pinDirty, setPinDirty] = useState(false);
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set(["commercial", "residential"]));
  const listRef = useRef<HTMLDivElement>(null);

  const loadData = useCallback(async () => {
    try {
      const [bows, allAnalyses] = await Promise.all([
        api.get<PoolBowWithCoords[]>("/v1/satellite/pool-bows"),
        api.get<SatelliteAnalysis[]>("/v1/satellite/all"),
      ]);
      setPoolBows(bows);
      setAnalyses(allAnalyses);
    } catch {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-select: URL param → first commercial → first pool
  const autoSelected = useRef(false);
  useEffect(() => {
    if (autoSelected.current || poolBows.length === 0) return;
    autoSelected.current = true;

    // URL param gets fly-to
    if (initialBowId && poolBows.find((b) => b.id === initialBowId)) {
      setShouldFlyTo(true);
      handleBowSelect(initialBowId);
      return;
    }

    // Default: select first pool quietly (no fly)
    const sorted = [...poolBows].sort((a, b) => a.customer_name.localeCompare(b.customer_name));
    const first = sorted.find(b => b.customer_type === "commercial") || sorted[0];
    if (first) selectBowQuiet(first.id);
  }, [poolBows, initialBowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const analysisMap = useMemo(() => new Map(analyses.map((a) => [a.body_of_water_id, a])), [analyses]);
  const selectedBow = poolBows.find((b) => b.id === selectedBowId) || null;
  const selectedAnalysis = selectedBowId ? analysisMap.get(selectedBowId) || null : null;

  const toggleFilter = (f: StatusFilter) => {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  };

  const getStatus = (b: PoolBowWithCoords): StatusFilter => {
    const a = analysisMap.get(b.id);
    if (a?.pool_detected && b.pool_lat) return "pinned";
    if (a?.pool_detected) return "analyzed";
    return "not_analyzed";
  };

  const toggleType = (t: string) => {
    setTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const sortFn = useCallback((a: PoolBowWithCoords, b: PoolBowWithCoords) => {
    return a.customer_name.localeCompare(b.customer_name);
  }, []);

  const filteredBows = useMemo(() => {
    return poolBows.filter((b) => {
      if (!typeFilter.has(b.customer_type)) return false;
      if (!statusFilters.has(getStatus(b))) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return b.customer_name.toLowerCase().includes(q)
        || b.address.toLowerCase().includes(q)
        || (b.bow_name?.toLowerCase().includes(q) ?? false);
    });
  }, [poolBows, search, statusFilters, typeFilter, analysisMap]);

  const commercialBows = useMemo(() =>
    filteredBows.filter(b => b.customer_type === "commercial").sort(sortFn),
    [filteredBows, sortFn]
  );
  const residentialBows = useMemo(() =>
    filteredBows.filter(b => b.customer_type !== "commercial").sort(sortFn),
    [filteredBows, sortFn]
  );

  // Load images when BOW is selected (images are property-keyed)
  const loadImages = useCallback(async (propertyId: string) => {
    try {
      const imgs = await api.get<PropertyPhoto[]>(`/v1/photos/properties/${propertyId}`);
      setImages(imgs);
    } catch {
      setImages([]);
    }
  }, []);

  const selectBowQuiet = useCallback((bowId: string) => {
    setSelectedBowId(bowId);
    setPinDirty(false);
    const analysis = analyses.find((a) => a.body_of_water_id === bowId);
    const bow = poolBows.find((b) => b.id === bowId);
    if (analysis?.pool_lat && analysis?.pool_lng) {
      setPinPosition({ lat: analysis.pool_lat, lng: analysis.pool_lng });
    } else if (bow?.pool_lat && bow?.pool_lng) {
      setPinPosition({ lat: bow.pool_lat, lng: bow.pool_lng });
    } else {
      setPinPosition(null);
    }
    if (bow) loadImages(bow.property_id);
  }, [poolBows, analyses, loadImages]);

  const handleBowSelect = useCallback((bowId: string) => {
    setShouldFlyTo(true);
    selectBowQuiet(bowId);
    setTimeout(() => {
      const el = document.getElementById(`bow-${bowId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 50);
  }, [selectBowQuiet]);

  const handlePinPlace = useCallback((lat: number, lng: number) => {
    setPinPosition({ lat, lng });
    setPinDirty(true);
  }, []);

  const savePin = async () => {
    if (!selectedBowId || !pinPosition) return;
    setSavingPin(true);
    try {
      const result = await api.put<SatelliteAnalysis>(
        `/v1/satellite/bows/${selectedBowId}/pin`,
        { pool_lat: pinPosition.lat, pool_lng: pinPosition.lng }
      );
      setAnalyses((prev) => {
        const idx = prev.findIndex((a) => a.body_of_water_id === selectedBowId);
        if (idx >= 0) return [...prev.slice(0, idx), result, ...prev.slice(idx + 1)];
        return [...prev, result];
      });
      setPoolBows((prev) =>
        prev.map((b) =>
          b.id === selectedBowId
            ? { ...b, pool_lat: pinPosition.lat, pool_lng: pinPosition.lng }
            : b
        )
      );
      setPinDirty(false);
      toast.success("Pin saved");
    } catch {
      toast.error("Failed to save pin");
    } finally {
      setSavingPin(false);
    }
  };

  const analyzeOne = async () => {
    if (!selectedBowId) return;
    setAnalyzingOne(true);
    try {
      const body: Record<string, unknown> = { force: true };
      if (pinPosition) {
        body.pool_lat = pinPosition.lat;
        body.pool_lng = pinPosition.lng;
      }
      const result = await api.post<SatelliteAnalysis>(
        `/v1/satellite/bows/${selectedBowId}/analyze`,
        body
      );
      setAnalyses((prev) => {
        const idx = prev.findIndex((a) => a.body_of_water_id === selectedBowId);
        if (idx >= 0) return [...prev.slice(0, idx), result, ...prev.slice(idx + 1)];
        return [...prev, result];
      });
      if (result.pool_detected) {
        setPoolBows((prev) =>
          prev.map((b) =>
            b.id === selectedBowId ? { ...b, has_analysis: true } : b
          )
        );
      }
      toast.success(result.pool_detected ? "Pool analyzed successfully" : "Analysis complete — pool not detected");
    } catch {
      toast.error("Analysis failed");
    } finally {
      setAnalyzingOne(false);
    }
  };

  // Image operations use property_id from the selected BOW
  const selectedPropertyId = selectedBow?.property_id || null;

  const uploadPhoto = async (file: File) => {
    if (!selectedPropertyId) return;
    setCapturing(true);
    try {
      // Client-side resize
      const resized = await resizeImage(file, 1600);
      const formData = new FormData();
      formData.append("photo", resized, file.name);
      if (selectedBowId) formData.append("body_of_water_id", selectedBowId);
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

  const runBulkAnalysis = async (force = false) => {
    setAnalyzing(true);
    try {
      const result = await api.post<BulkAnalysisResponse>("/v1/satellite/bulk-analyze", {
        force_reanalyze: force,
      });
      toast.success(
        `Analyzed ${result.analyzed} pools. ${result.skipped} skipped, ${result.failed} failed.`
      );
      await loadData();
    } catch {
      toast.error("Bulk analysis failed");
    } finally {
      setAnalyzing(false);
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
  const totalCount = poolBows.length;

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

        {/* Mode-specific actions */}
        {mode === "pools" && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {analyzedCount}/{totalCount} analyzed
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => runBulkAnalysis(false)}
              disabled={analyzing}
            >
              {analyzing ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Satellite className="mr-1 h-3 w-3" />}
              Analyze New
            </Button>
          </div>
        )}
      </div>

      {/* 3-Column Layout: List | Map | Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" style={{ height: "calc(100vh - 140px)", minHeight: 500 }}>
        {/* Left Panel */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
        {mode === "pools" ? (<>
        {/* Pool BOW List */}
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

          {/* BOW list — commercial first */}
          <div ref={listRef} className="flex-1 overflow-y-auto space-y-0 pr-1">
            {[
              { label: "Commercial", Icon: Building2, items: commercialBows, show: typeFilter.has("commercial") },
              { label: "Residential", Icon: Home, items: residentialBows, show: typeFilter.has("residential") },
            ].map((section) => section.show && section.items.length > 0 && (
              <div key={section.label}>
                <div className="flex items-center gap-2 px-1 pt-3 pb-1.5 mb-0.5 sticky top-0 z-10 bg-background border-b border-border">
                  <section.Icon className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{section.label}</span>
                  <span className="text-[11px] text-muted-foreground/50">{section.items.length}</span>
                  <div className="flex-1 border-t border-border ml-1" />
                </div>
                <div className="space-y-0.5 mb-2">
                  {section.items.map((b) => {
                    const a = analysisMap.get(b.id);
                    const isSelected = b.id === selectedBowId;
                    const status = getStatus(b);
                    return (
                      <button
                        key={b.id}
                        id={`bow-${b.id}`}
                        onClick={() => handleBowSelect(b.id)}
                        className={`w-full text-left rounded-md px-3 py-2 text-sm transition-colors ${
                          isSelected
                            ? "bg-accent border-l-3 border-l-primary font-medium"
                            : "hover:bg-muted"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
                              status === "pinned"
                                ? "bg-green-500"
                                : status === "analyzed"
                                ? "bg-yellow-500"
                                : "bg-red-500"
                            }`}
                          />
                          <span className="font-medium truncate">
                            {b.customer_name}
                          </span>
                        </div>
                        <div className="text-xs truncate ml-4 text-muted-foreground">
                          {b.address}
                        </div>
                        {b.bow_name && (
                          <div className="text-xs truncate ml-4 text-muted-foreground">
                            {b.bow_name}
                          </div>
                        )}
                        {b.tech_name && (
                          <div className="text-xs truncate ml-4 text-muted-foreground flex items-center gap-1.5">
                            <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.tech_color || '#94a3b8' }} />
                            {b.tech_name}
                          </div>
                        )}
                        {b.pool_sqft && (
                          <div className="text-xs ml-4 text-muted-foreground">
                            {b.pool_sqft.toLocaleString()} ft²
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
            {filteredBows.length === 0 && (
              <div className="text-center py-6 text-sm text-muted-foreground">No matching pools</div>
            )}
          </div>
          <div className="text-[11px] text-muted-foreground pt-1 border-t mt-1">
            {filteredBows.length} of {totalCount} shown
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
              poolBows={poolBows}
              selectedBowId={selectedBowId}
              pinPosition={pinPosition}
              flyTo={shouldFlyTo}
              onBowSelect={handleBowSelect}
              onPinPlace={handlePinPlace}
            />
          </Card>
          {/* Status filter overlay — bottom-left of map */}
          <div className="absolute bottom-3 left-3 z-[1000] flex items-center gap-1 bg-background/90 backdrop-blur-sm rounded-md px-2 py-1.5 shadow-md border">
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
          ) : selectedBow ? (
            <div className="space-y-3">
              {/* Property header */}
              <Card className="shadow-sm">
                <CardContent className="p-4">
                  <h3 className="text-base font-semibold">{selectedBow.customer_name}</h3>
                  <p className="text-sm text-muted-foreground">{selectedBow.address}</p>
                  {selectedBow.tech_name && (
                    <div className="flex items-center gap-1.5 mt-1.5 text-xs text-muted-foreground">
                      <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: selectedBow.tech_color || '#94a3b8' }} />
                      <span className="font-medium">{selectedBow.tech_name}</span>
                    </div>
                  )}
                  {selectedBow.lat && selectedBow.lng && (
                    <p className="text-xs text-muted-foreground mt-1">
                      <MapPin className="h-3 w-3 inline mr-1" />
                      {selectedBow.lat.toFixed(6)}, {selectedBow.lng.toFixed(6)}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Pool BOW tile */}
              <Card className="shadow-sm border-l-4 border-l-blue-500">
                <CardContent className="p-4 space-y-3">
                  {/* Pool header + actions */}
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <Droplets className="h-3.5 w-3.5 text-blue-500" />
                        <span className="text-sm font-semibold">{selectedBow.bow_name || "Pool"}</span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
                        <Crosshair className="h-3 w-3" />
                        {pinPosition ? (
                          <span className="text-green-600 font-medium">
                            {pinPosition.lat.toFixed(6)}, {pinPosition.lng.toFixed(6)}
                          </span>
                        ) : (
                          <span>Click map to place pin</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1.5">
                      {pinDirty && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-2 text-xs"
                          disabled={savingPin}
                          onClick={savePin}
                        >
                          {savingPin ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Pin"}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        className="h-7 px-2 text-xs"
                        disabled={analyzingOne}
                        onClick={analyzeOne}
                      >
                        {analyzingOne ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <>
                            {selectedAnalysis?.pool_detected ? <RefreshCw className="mr-1 h-3 w-3" /> : <Satellite className="mr-1 h-3 w-3" />}
                            {selectedAnalysis?.pool_detected ? "Re-analyze" : "Analyze"}
                          </>
                        )}
                      </Button>
                    </div>
                  </div>

                  {/* Analysis results */}
                  {selectedAnalysis && !selectedAnalysis.error_message && selectedAnalysis.pool_detected && (
                    <div className="rounded-md bg-muted/50 p-3 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">Pool Found</Badge>
                        <Badge
                          className={
                            selectedAnalysis.pool_confidence >= 0.7
                              ? "bg-green-100 text-green-800 hover:bg-green-100"
                              : selectedAnalysis.pool_confidence >= 0.4
                              ? "bg-yellow-100 text-yellow-800 hover:bg-yellow-100"
                              : "bg-red-100 text-red-800 hover:bg-red-100"
                          }
                        >
                          {(selectedAnalysis.pool_confidence * 100).toFixed(0)}%
                        </Badge>
                        {selectedBow?.pool_sqft && (
                          <span className="text-sm font-semibold ml-auto">
                            {selectedBow.pool_sqft.toLocaleString()} ft²
                          </span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Vegetation</span>
                          <span className="font-medium">{selectedAnalysis.vegetation_pct}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Canopy</span>
                          <span className={`font-medium ${selectedAnalysis.canopy_overhang_pct > 30 ? "text-yellow-600" : ""}`}>
                            {selectedAnalysis.canopy_overhang_pct}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Hardscape</span>
                          <span className="font-medium">{selectedAnalysis.hardscape_pct}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Shadow</span>
                          <span className="font-medium">{selectedAnalysis.shadow_pct}%</span>
                        </div>
                      </div>
                      <div className="text-[10px] text-muted-foreground text-right">v{selectedAnalysis.analysis_version}</div>
                    </div>
                  )}

                  {selectedAnalysis && !selectedAnalysis.error_message && !selectedAnalysis.pool_detected && (
                    <div className="rounded-md bg-muted/50 p-3">
                      <Badge variant="secondary">No Pool Detected</Badge>
                      <p className="text-xs text-muted-foreground mt-1">
                        Place the marker directly on the pool and re-analyze.
                      </p>
                    </div>
                  )}

                  {selectedAnalysis?.error_message && (
                    <div className="rounded-md bg-destructive/5 p-3">
                      <Badge variant="destructive">Error</Badge>
                      <p className="text-xs text-muted-foreground mt-1">{selectedAnalysis.error_message}</p>
                    </div>
                  )}

                  {!selectedAnalysis && (
                    <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                      Not yet analyzed. Place the marker on the pool and click Analyze.
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Property photos */}
              <Card className="shadow-sm">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Photos</p>
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-muted-foreground">{images.length}/8</p>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 px-2 text-xs"
                        disabled={capturing || images.length >= 8}
                        onClick={() => document.getElementById("photo-upload")?.click()}
                      >
                        {capturing ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <Camera className="mr-1 h-3 w-3" />
                        )}
                        Upload
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
                    </div>
                  </div>
                  {images.length > 0 ? (
                    <div className="grid grid-cols-2 gap-2">
                      {images.map((img) => (
                        <div key={img.id} className="relative group">
                          <img
                            src={`${API_BASE}${img.url}`}
                            alt={img.caption || "Property photo"}
                            className={`w-full aspect-square object-cover rounded-md border-2 ${
                              img.is_hero ? "border-amber-400" : "border-transparent"
                            }`}
                          />
                          {img.is_hero && (
                            <div className="absolute top-1 left-1">
                              <Star className="h-4 w-4 fill-amber-400 text-amber-400 drop-shadow" />
                            </div>
                          )}
                          <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5">
                            {!img.is_hero && (
                              <Button
                                variant="secondary"
                                size="icon"
                                className="h-6 w-6 bg-white/90 hover:bg-white shadow-sm"
                                onClick={() => setHero(img.id)}
                                title="Set as hero image"
                              >
                                <Star className="h-3 w-3" />
                              </Button>
                            )}
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <Button
                                  variant="secondary"
                                  size="icon"
                                  className="h-6 w-6 bg-white/90 hover:bg-white shadow-sm text-destructive"
                                  title="Delete photo"
                                >
                                  <Trash2 className="h-3 w-3" />
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
                          {img.caption && (
                            <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[10px] px-1.5 py-0.5 rounded-b-md truncate">
                              {img.caption}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No photos yet. Upload from the field.</p>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a pool from the list or map
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
