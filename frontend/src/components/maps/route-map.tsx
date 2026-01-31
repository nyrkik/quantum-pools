"use client";

import dynamic from "next/dynamic";
import type { OptimizationRoute, Route, PolylineResponse } from "@/types/route";

export interface RouteMapProps {
  routes: (OptimizationRoute | Route)[];
  polylines?: Record<string, PolylineResponse>;
  selectedTechId?: string | null;
  onStopClick?: (propertyId: string) => void;
}

const RouteMapInner = dynamic(
  () => import("./route-map-inner"),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-muted-foreground">Loading map...</div> }
);

export default function RouteMap(props: RouteMapProps) {
  return <RouteMapInner {...props} />;
}
