"use client";

import { type MutableRefObject } from "react";
import dynamic from "next/dynamic";
import type { PoolBowWithCoords } from "@/types/satellite";

export interface MapActions {
  toggleZoom: () => void;
  isZoomedIn: boolean;
}

export interface SatelliteMapProps {
  poolBows: PoolBowWithCoords[];
  selectedBowId: string | null;
  pinPosition: { lat: number; lng: number } | null;
  flyTo: boolean;
  actionsRef?: MutableRefObject<MapActions | null>;
  onBowSelect: (bowId: string) => void;
  onPinPlace: (lat: number, lng: number) => void;
}

const SatelliteMapInner = dynamic(
  () => import("./satellite-map-inner"),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-muted-foreground">Loading map...</div> }
);

export default function SatelliteMap(props: SatelliteMapProps) {
  return <SatelliteMapInner {...props} />;
}
