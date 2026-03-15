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
  TreePine,
  Droplets,
  RefreshCw,
  AlertCircle,
  MapPin,
  Crosshair,
  Search,
  Camera,
  Star,
  Trash2,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  Building2,
  Home,
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
import type { SatelliteAnalysis, PoolBowWithCoords, BulkAnalysisResponse, SatelliteImageData } from "@/types/satellite";
import SatelliteMap from "@/components/maps/satellite-map";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://100.121.52.15:7061";

type SortKey = "name" | "address" | "sqft" | "status";
type SortDir = "asc" | "desc";
type StatusFilter = "analyzed" | "pinned" | "not_analyzed";

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 ml-0.5 text-muted-foreground/40" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 ml-0.5" />
    : <ArrowDown className="h-3 w-3 ml-0.5" />;
}

export default function SatellitePage() {
  const searchParams = useSearchParams();
  const initialBowId = searchParams.get("bow");
  const [poolBows, setPoolBows] = useState<PoolBowWithCoords[]>([]);
  const [analyses, setAnalyses] = useState<SatelliteAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedBowId, setSelectedBowId] = useState<string | null>(null);
  const [pinPosition, setPinPosition] = useState<{ lat: number; lng: number } | null>(null);
  const [savingPin, setSavingPin] = useState(false);
  const [analyzingOne, setAnalyzingOne] = useState(false);
  const [search, setSearch] = useState("");
  const [images, setImages] = useState<SatelliteImageData[]>([]);
  const [capturing, setCapturing] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [statusFilters, setStatusFilters] = useState<Set<StatusFilter>>(new Set(["analyzed", "pinned", "not_analyzed"]));
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

  // Auto-select BOW from URL param after data loads
  const autoSelected = useRef(false);
  useEffect(() => {
    if (autoSelected.current || !initialBowId || poolBows.length === 0) return;
    if (poolBows.find((b) => b.id === initialBowId)) {
      autoSelected.current = true;
      handleBowSelect(initialBowId);
    }
  }, [poolBows, initialBowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const analysisMap = useMemo(() => new Map(analyses.map((a) => [a.body_of_water_id, a])), [analyses]);
  const selectedBow = poolBows.find((b) => b.id === selectedBowId) || null;
  const selectedAnalysis = selectedBowId ? analysisMap.get(selectedBowId) || null : null;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

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
    const dir = sortDir === "asc" ? 1 : -1;
    const aAnalysis = analysisMap.get(a.id);
    const bAnalysis = analysisMap.get(b.id);
    switch (sortKey) {
      case "name":
        return dir * a.customer_name.localeCompare(b.customer_name);
      case "address":
        return dir * a.address.localeCompare(b.address);
      case "sqft":
        return dir * ((aAnalysis?.estimated_pool_sqft ?? 0) - (bAnalysis?.estimated_pool_sqft ?? 0));
      case "status": {
        const order: Record<StatusFilter, number> = { pinned: 0, analyzed: 1, not_analyzed: 2 };
        return dir * (order[getStatus(a)] - order[getStatus(b)]);
      }
      default:
        return 0;
    }
  }, [sortKey, sortDir, analysisMap]);

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
      const imgs = await api.get<SatelliteImageData[]>(`/v1/satellite/properties/${propertyId}/images`);
      setImages(imgs);
    } catch {
      setImages([]);
    }
  }, []);

  const handleBowSelect = useCallback((bowId: string) => {
    setSelectedBowId(bowId);
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
    setTimeout(() => {
      const el = document.getElementById(`bow-${bowId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 50);
  }, [poolBows, analyses, loadImages]);

  const handlePinPlace = useCallback((lat: number, lng: number) => {
    setPinPosition({ lat, lng });
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

  const captureImage = async (zoom: number) => {
    if (!selectedPropertyId || !pinPosition) return;
    setCapturing(true);
    try {
      const img = await api.post<SatelliteImageData>(
        `/v1/satellite/properties/${selectedPropertyId}/images/capture`,
        { center_lat: pinPosition.lat, center_lng: pinPosition.lng, zoom }
      );
      setImages((prev) => [img, ...prev]);
      toast.success("Image captured");
    } catch {
      toast.error("Capture failed");
    } finally {
      setCapturing(false);
    }
  };

  const setHero = async (imageId: string) => {
    if (!selectedPropertyId) return;
    try {
      const updated = await api.put<SatelliteImageData>(
        `/v1/satellite/properties/${selectedPropertyId}/images/${imageId}/hero`
      );
      setImages((prev) =>
        prev.map((img) => ({ ...img, is_hero: img.id === updated.id }))
      );
      toast.success("Hero image set");
    } catch {
      toast.error("Failed to set hero");
    }
  };

  const deleteImage = async (imageId: string) => {
    if (!selectedPropertyId) return;
    try {
      await api.delete(`/v1/satellite/properties/${selectedPropertyId}/images/${imageId}`);
      setImages((prev) => prev.filter((img) => img.id !== imageId));
      toast.success("Image deleted");
    } catch {
      toast.error("Failed to delete image");
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
  const pinnedCount = poolBows.filter((b) => b.pool_lat != null).length;
  const highCanopy = analyses.filter((a) => a.canopy_overhang_pct > 30).length;
  const avgVeg = analyses.length > 0
    ? (analyses.reduce((sum, a) => sum + a.vegetation_pct, 0) / analyses.length).toFixed(1)
    : "0";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Satellite Analysis</h1>
          <p className="text-muted-foreground text-sm">
            {analyzedCount}/{totalCount} analyzed &middot; {pinnedCount} pinned
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => runBulkAnalysis(false)}
            disabled={analyzing}
          >
            {analyzing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Satellite className="mr-2 h-4 w-4" />
            )}
            Analyze New
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => runBulkAnalysis(true)}
            disabled={analyzing}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Re-analyze All
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-medium">Pools Detected</CardTitle>
            <Droplets className="h-3.5 w-3.5 text-blue-500" />
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="text-xl font-bold">{analyzedCount}</div>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-medium">Avg Vegetation</CardTitle>
            <TreePine className="h-3.5 w-3.5 text-green-600" />
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="text-xl font-bold">{avgVeg}%</div>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-medium">High Canopy</CardTitle>
            <TreePine className="h-3.5 w-3.5 text-yellow-600" />
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="text-xl font-bold text-yellow-600">{highCanopy}</div>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-medium">Not Analyzed</CardTitle>
            <AlertCircle className="h-3.5 w-3.5 text-red-500" />
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="text-xl font-bold text-red-500">{totalCount - analyses.length}</div>
          </CardContent>
        </Card>
      </div>

      {/* 3-Column Layout: List | Map | Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" style={{ height: "calc(100vh - 300px)", minHeight: 500 }}>
        {/* Left: Pool BOW List */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
          {/* Search */}
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search pools..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-sm"
            />
          </div>

          {/* Type + status filters */}
          <div className="flex items-center gap-1 mb-2 flex-wrap">
            {[
              { value: "commercial", label: "Commercial", Icon: Building2 },
              { value: "residential", label: "Residential", Icon: Home },
            ].map((t) => (
              <Button
                key={t.value}
                variant={typeFilter.has(t.value) ? "default" : "outline"}
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => toggleType(t.value)}
              >
                <t.Icon className="h-3 w-3 mr-1" />
                {t.label}
              </Button>
            ))}
            <span className="w-px h-4 bg-border mx-0.5" />
            {([
              { value: "analyzed" as StatusFilter, label: "Analyzed", color: "bg-yellow-500" },
              { value: "pinned" as StatusFilter, label: "Pinned", color: "bg-green-500" },
              { value: "not_analyzed" as StatusFilter, label: "Pending", color: "bg-red-500" },
            ]).map((f) => (
              <Button
                key={f.value}
                variant={statusFilters.has(f.value) ? "default" : "outline"}
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => toggleFilter(f.value)}
              >
                <span className={`inline-block w-1.5 h-1.5 rounded-full ${f.color} mr-1`} />
                {f.label}
              </Button>
            ))}
          </div>

          {/* Sort buttons */}
          <div className="flex items-center gap-1 mb-2 text-[11px]">
            {([
              { key: "name" as SortKey, label: "Name" },
              { key: "address" as SortKey, label: "Address" },
              { key: "sqft" as SortKey, label: "Sqft" },
              { key: "status" as SortKey, label: "Status" },
            ]).map((s) => (
              <button
                key={s.key}
                onClick={() => toggleSort(s.key)}
                className={`flex items-center px-1.5 py-0.5 rounded cursor-pointer select-none transition-colors ${
                  sortKey === s.key ? "bg-muted font-medium" : "hover:bg-muted/50 text-muted-foreground"
                }`}
              >
                {s.label}
                <SortIcon active={sortKey === s.key} dir={sortDir} />
              </button>
            ))}
          </div>

          {/* BOW list — commercial first */}
          <div ref={listRef} className="flex-1 overflow-y-auto space-y-0 pr-1">
            {[
              { label: "Commercial", Icon: Building2, items: commercialBows, show: typeFilter.has("commercial") },
              { label: "Residential", Icon: Home, items: residentialBows, show: typeFilter.has("residential") },
            ].map((section) => section.show && section.items.length > 0 && (
              <div key={section.label}>
                <div className="flex items-center gap-2 bg-primary text-primary-foreground px-3 py-1.5 rounded-md mb-1 sticky top-0 z-10">
                  <section.Icon className="h-3.5 w-3.5 opacity-70" />
                  <span className="text-xs font-medium uppercase tracking-wide">{section.label}</span>
                  <span className="text-xs opacity-70 ml-auto">{section.items.length}</span>
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
                            ? "bg-primary text-primary-foreground"
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
                        <div className={`text-xs truncate ml-4 ${isSelected ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                          {b.address}
                        </div>
                        {b.bow_name && (
                          <div className={`text-xs truncate ml-4 ${isSelected ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                            {b.bow_name}
                          </div>
                        )}
                        {a?.estimated_pool_sqft && (
                          <div className={`text-xs ml-4 ${isSelected ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                            {a.estimated_pool_sqft.toLocaleString()} ft²
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
        </div>

        {/* Center: Map */}
        <div className="lg:col-span-5 min-h-0">
          <Card className="shadow-sm overflow-hidden h-full">
            <SatelliteMap
              poolBows={poolBows}
              selectedBowId={selectedBowId}
              pinPosition={pinPosition}
              onBowSelect={handleBowSelect}
              onPinPlace={handlePinPlace}
            />
          </Card>
        </div>

        {/* Right: Details Panel */}
        <div className="lg:col-span-4 min-h-0 overflow-y-auto">
          {selectedBow ? (
            <Card className="shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{selectedBow.customer_name}</CardTitle>
                <p className="text-sm text-muted-foreground">{selectedBow.address}</p>
                {selectedBow.bow_name && (
                  <p className="text-sm font-medium">{selectedBow.bow_name}</p>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Pin Status + Actions */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm">
                    <MapPin className="h-3.5 w-3.5 flex-shrink-0" />
                    {pinPosition ? (
                      <span className="text-green-600 font-medium text-xs">
                        {pinPosition.lat.toFixed(6)}, {pinPosition.lng.toFixed(6)}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Click map to place marker</span>
                    )}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!pinPosition || savingPin}
                      onClick={savePin}
                    >
                      {savingPin ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Crosshair className="mr-1 h-3.5 w-3.5" />
                      )}
                      Save Pin
                    </Button>
                    <Button
                      size="sm"
                      disabled={analyzingOne}
                      onClick={analyzeOne}
                    >
                      {analyzingOne ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Satellite className="mr-1 h-3.5 w-3.5" />
                      )}
                      Analyze
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!pinPosition || capturing || images.length >= 4}
                      onClick={() => captureImage(20)}
                    >
                      {capturing ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Camera className="mr-1 h-3.5 w-3.5" />
                      )}
                      Capture
                    </Button>
                  </div>
                </div>

                {/* Analysis Results */}
                {selectedAnalysis && !selectedAnalysis.error_message && selectedAnalysis.pool_detected && (
                  <div className="space-y-3 border-t pt-3">
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
                      <span className="text-xs text-muted-foreground ml-auto">
                        v{selectedAnalysis.analysis_version}
                      </span>
                    </div>

                    {selectedAnalysis.estimated_pool_sqft && (
                      <div className="text-sm">
                        <span className="text-muted-foreground">Pool Size: </span>
                        <span className="font-medium">
                          {selectedAnalysis.estimated_pool_sqft.toLocaleString()} ft²
                        </span>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Vegetation: </span>
                        <span className="font-medium">{selectedAnalysis.vegetation_pct}%</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Canopy: </span>
                        <span className={`font-medium ${selectedAnalysis.canopy_overhang_pct > 30 ? "text-yellow-600" : ""}`}>
                          {selectedAnalysis.canopy_overhang_pct}%
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Hardscape: </span>
                        <span className="font-medium">{selectedAnalysis.hardscape_pct}%</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Shadow: </span>
                        <span className="font-medium">{selectedAnalysis.shadow_pct}%</span>
                      </div>
                    </div>
                  </div>
                )}

                {selectedAnalysis && !selectedAnalysis.error_message && !selectedAnalysis.pool_detected && (
                  <div className="border-t pt-3">
                    <Badge variant="secondary">No Pool Detected</Badge>
                    <p className="text-sm text-muted-foreground mt-1">
                      Try placing the marker directly on the pool and re-analyzing.
                    </p>
                  </div>
                )}

                {selectedAnalysis?.error_message && (
                  <div className="border-t pt-3">
                    <Badge variant="destructive">Error</Badge>
                    <p className="text-sm text-muted-foreground mt-1">{selectedAnalysis.error_message}</p>
                  </div>
                )}

                {!selectedAnalysis && (
                  <div className="border-t pt-3 text-sm text-muted-foreground">
                    Not yet analyzed. Place the marker on the pool and click Analyze.
                  </div>
                )}

                {/* Saved Images */}
                {images.length > 0 && (
                  <div className="border-t pt-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">Satellite Images</p>
                      <p className="text-xs text-muted-foreground">{images.length}/4</p>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {images.map((img) => (
                        <div key={img.id} className="relative group">
                          <img
                            src={`${API_BASE}${img.url}`}
                            alt="Satellite"
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
                                  title="Delete image"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </Button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>Delete satellite image?</AlertDialogTitle>
                                  <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                                  <AlertDialogAction onClick={() => deleteImage(img.id)}>Delete</AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          </div>
                          <div className="absolute bottom-1 right-1 bg-black/60 text-white text-[10px] px-1 rounded">
                            z{img.zoom}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a pool from the list or map
            </div>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500 border border-white" /> Analyzed + Pinned
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-yellow-500 border border-white" /> Analyzed
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500 border border-white" /> Not Analyzed
        </span>
      </div>
    </div>
  );
}
