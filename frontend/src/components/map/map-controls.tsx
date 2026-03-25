"use client";

import { RefObject } from "react";
import { Card } from "@/components/ui/card";
import {
  Droplets,
  Route,
  TrendingUp,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import SatelliteMap from "@/components/maps/satellite-map";
import type { MapActions, PropertyGroup } from "@/components/maps/satellite-map";
import { type StatusFilter, type MapMode, MAP_MODES } from "./map-types";

const MODE_ICONS = {
  pools: Droplets,
  routes: Route,
  profitability: TrendingUp,
} as const;

interface ModeSwitcherProps {
  mode: MapMode;
  onModeChange: (mode: MapMode) => void;
  analyzedCount: number;
  totalBowCount: number;
}

export function ModeSwitcher({ mode, onModeChange, analyzedCount, totalBowCount }: ModeSwitcherProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
        {MAP_MODES.map((m) => {
          const Icon = MODE_ICONS[m.key];
          return (
            <button
              key={m.key}
              onClick={() => onModeChange(m.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                mode === m.key
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {m.label}
            </button>
          );
        })}
      </div>

      {mode === "pools" && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {analyzedCount}/{totalBowCount} analyzed
          </span>
        </div>
      )}
    </div>
  );
}

interface MapPanelProps {
  filteredGroups: PropertyGroup[];
  selectedPropertyId: string | null;
  pinPosition: { lat: number; lng: number } | null;
  shouldFlyTo: boolean;
  mapActionsRef: RefObject<MapActions | null>;
  onPropertySelect: (propertyId: string) => void;
  onPinPlace: (lat: number, lng: number) => void;
  onZoomChange: (zoom: number) => void;
  mapZoom: number;
  pinDirty: boolean;
  onResetPin: () => void;
  statusFilters: Set<StatusFilter>;
  onToggleFilter: (filter: StatusFilter) => void;
}

export function MapPanel({
  filteredGroups,
  selectedPropertyId,
  pinPosition,
  shouldFlyTo,
  mapActionsRef,
  onPropertySelect,
  onPinPlace,
  onZoomChange,
  mapZoom,
  pinDirty,
  onResetPin,
  statusFilters,
  onToggleFilter,
}: MapPanelProps) {
  return (
    <div className="lg:col-span-5 min-h-0 relative">
      <Card className="shadow-sm overflow-hidden h-full">
        <SatelliteMap
          propertyGroups={filteredGroups}
          selectedPropertyId={selectedPropertyId}
          pinPosition={pinPosition}
          flyTo={shouldFlyTo}
          actionsRef={mapActionsRef}
          onPropertySelect={onPropertySelect}
          onPinPlace={onPinPlace}
          onZoomChange={onZoomChange}
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
                onResetPin();
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
            onClick={() => onToggleFilter(f.value)}
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
  );
}
