"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import RouteMap from "@/components/maps/route-map";
import OptimizationControls from "@/components/routes/optimization-controls";
import RouteEditor from "@/components/routes/route-editor";
import type {
  OptimizationRequest,
  OptimizationResponse,
  OptimizationRoute,
  OptimizationSummary,
  PolylineResponse,
  Route,
} from "@/types/route";

const DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
] as const;

function todayDay(): string {
  const idx = new Date().getDay(); // 0=Sun
  const map = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
  const d = map[idx];
  return DAYS.includes(d as (typeof DAYS)[number]) ? d : "monday";
}

export default function RoutesPage() {
  const [selectedDay, setSelectedDay] = useState(todayDay);
  const [savedRoutes, setSavedRoutes] = useState<Route[]>([]);
  const [optimizationRoutes, setOptimizationRoutes] = useState<OptimizationRoute[]>([]);
  const [summary, setSummary] = useState<OptimizationSummary | null>(null);
  const [polylines, setPolylines] = useState<Record<string, PolylineResponse>>({});
  const [optimizing, setOptimizing] = useState(false);
  const [saving, setSaving] = useState(false);

  // Are we showing optimization preview or saved routes?
  const displayRoutes: OptimizationRoute[] =
    optimizationRoutes.length > 0
      ? optimizationRoutes
      : savedRoutes.map((r) => ({
          tech_id: r.tech_id,
          tech_name: r.tech_name || "",
          tech_color: r.tech_color || "#3B82F6",
          service_day: r.service_day,
          stops: r.stops.map((s) => ({
            property_id: s.property_id,
            property_address: s.property_address || "",
            customer_name: s.customer_name || "",
            lat: s.lat || 0,
            lng: s.lng || 0,
            sequence: s.sequence,
            estimated_service_duration: s.estimated_service_duration,
            estimated_drive_time_from_previous: s.estimated_drive_time_from_previous,
            estimated_distance_from_previous: s.estimated_distance_from_previous,
          })),
          total_stops: r.total_stops,
          total_distance_miles: r.total_distance_miles,
          total_duration_minutes: r.total_duration_minutes,
        }));

  // Load saved routes for the selected day
  const loadRoutes = useCallback(async () => {
    try {
      const data = await api.get<Route[]>(`/v1/routes/day/${selectedDay}`);
      setSavedRoutes(data);
    } catch {
      // silently fail — may not have routes yet
    }
  }, [selectedDay]);

  useEffect(() => {
    setOptimizationRoutes([]);
    setSummary(null);
    setPolylines({});
    loadRoutes();
  }, [selectedDay, loadRoutes]);

  // Fetch polylines for displayed routes
  const fetchPolylines = useCallback(async (routes: (OptimizationRoute | Route)[]) => {
    const newPolylines: Record<string, PolylineResponse> = {};
    for (const route of routes) {
      const key = `${route.service_day}:${route.tech_id}`;
      if (route.stops?.length > 0) {
        try {
          const pl = await api.get<PolylineResponse>(
            `/v1/routes/day/${route.service_day}/tech/${route.tech_id}/polyline`
          );
          newPolylines[key] = pl;
        } catch {
          // polyline fetch is best-effort
        }
      }
    }
    setPolylines(newPolylines);
  }, []);

  // Fetch polylines when saved routes load
  useEffect(() => {
    if (savedRoutes.length > 0 && optimizationRoutes.length === 0) {
      fetchPolylines(savedRoutes);
    }
  }, [savedRoutes, optimizationRoutes, fetchPolylines]);

  const handleOptimize = async (req: OptimizationRequest) => {
    setOptimizing(true);
    try {
      const data = await api.post<OptimizationResponse>("/v1/routes/optimize", req);
      setOptimizationRoutes(data.routes);
      setSummary(data.summary);
      toast.success(`Optimized ${data.summary.total_stops} stops across ${data.summary.total_routes} routes`);
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err ? (err as { message: string }).message : "Optimization failed";
      toast.error(msg);
    } finally {
      setOptimizing(false);
    }
  };

  const handleSave = async () => {
    if (optimizationRoutes.length === 0) return;
    setSaving(true);
    try {
      await api.post<Route[]>("/v1/routes/save", optimizationRoutes);
      toast.success("Routes saved");
      setOptimizationRoutes([]);
      setSummary(null);
      await loadRoutes();
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err ? (err as { message: string }).message : "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleReorder = (techId: string, oldIndex: number, newIndex: number) => {
    setOptimizationRoutes((prev) => {
      const next = prev.map((r) => {
        if (r.tech_id !== techId) return r;
        const stops = [...r.stops];
        const [moved] = stops.splice(oldIndex, 1);
        stops.splice(newIndex, 0, moved);
        return {
          ...r,
          stops: stops.map((s, i) => ({ ...s, sequence: i + 1 })),
        };
      });
      return next;
    });
  };

  const handleReassign = () => {
    // Reassignment between techs handled via API after save
  };

  const dayIndex = DAYS.indexOf(selectedDay as (typeof DAYS)[number]);
  const prevDay = () => {
    const idx = dayIndex <= 0 ? DAYS.length - 1 : dayIndex - 1;
    setSelectedDay(DAYS[idx]);
  };
  const nextDay = () => {
    const idx = dayIndex >= DAYS.length - 1 ? 0 : dayIndex + 1;
    setSelectedDay(DAYS[idx]);
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-4 p-4">
      {/* Left sidebar */}
      <div className="flex w-[400px] flex-shrink-0 flex-col gap-4">
        {/* Day nav */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="icon" onClick={prevDay}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <h2 className="text-lg font-semibold capitalize">{selectedDay}</h2>
          <Button variant="ghost" size="icon" onClick={nextDay}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {/* Controls */}
        <OptimizationControls
          onOptimize={handleOptimize}
          onSave={handleSave}
          optimizing={optimizing}
          saving={saving}
          hasResults={optimizationRoutes.length > 0}
          summary={summary}
          selectedDay={selectedDay}
          onDayChange={setSelectedDay}
        />

        {/* Route editor */}
        <ScrollArea className="flex-1">
          <RouteEditor
            routes={displayRoutes}
            onReorder={handleReorder}
            onReassign={handleReassign}
          />
        </ScrollArea>
      </div>

      {/* Map */}
      <div className="flex-1 rounded-md border">
        <RouteMap routes={displayRoutes} polylines={polylines} />
      </div>
    </div>
  );
}
