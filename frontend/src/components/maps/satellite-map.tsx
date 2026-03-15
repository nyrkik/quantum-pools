"use client";

import { type MutableRefObject } from "react";
import dynamic from "next/dynamic";
import type { PoolBowWithCoords } from "@/types/satellite";

export interface MapActions {
  toggleZoom: () => void;
  isZoomedIn: boolean;
}

export interface PropertyGroup {
  property_id: string;
  customer_id: string;
  customer_name: string;
  customer_type: string;
  address: string;
  city: string;
  lat: number | null;
  lng: number | null;
  tech_name: string | null;
  tech_color: string | null;
  bows: PoolBowWithCoords[];
  best_status: "analyzed" | "pinned" | "not_analyzed";
}

export interface SatelliteMapProps {
  propertyGroups: PropertyGroup[];
  selectedPropertyId: string | null;
  pinPosition: { lat: number; lng: number } | null;
  flyTo: boolean;
  actionsRef?: MutableRefObject<MapActions | null>;
  onPropertySelect: (propertyId: string) => void;
  onPinPlace: (lat: number, lng: number) => void;
}

const SatelliteMapInner = dynamic(
  () => import("./satellite-map-inner"),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-muted-foreground">Loading map...</div> }
);

export default function SatelliteMap(props: SatelliteMapProps) {
  return <SatelliteMapInner {...props} />;
}
