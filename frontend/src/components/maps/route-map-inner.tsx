"use client";

import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import type { RouteMapProps } from "./route-map";

// Fix default marker icon paths (Leaflet + webpack issue)
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function createColoredIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      background:${color};
      width:14px;height:14px;
      border-radius:50%;
      border:2px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.4);
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function FitBounds({ markers }: { markers: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (markers.length === 0) return;
    const bounds = L.latLngBounds(markers.map(([lat, lng]) => [lat, lng]));
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [markers, map]);
  return null;
}

export default function RouteMapInner({
  routes,
  polylines = {},
  selectedTechId,
  onStopClick,
}: RouteMapProps) {
  const allMarkers = useMemo(() => {
    const markers: { lat: number; lng: number; color: string; label: string; propertyId: string; seq: number }[] = [];
    for (const route of routes) {
      if (selectedTechId && route.tech_id !== selectedTechId) continue;
      const color = route.tech_color || "#3B82F6";
      for (const stop of route.stops) {
        const lat = "lat" in stop ? stop.lat : undefined;
        const lng = "lng" in stop ? stop.lng : undefined;
        if (lat && lng) {
          markers.push({
            lat,
            lng,
            color,
            label: `${stop.sequence}. ${"customer_name" in stop ? stop.customer_name : ""} — ${"property_address" in stop ? stop.property_address : ""}`,
            propertyId: stop.property_id,
            seq: stop.sequence,
          });
        }
      }
    }
    return markers;
  }, [routes, selectedTechId]);

  const bounds = useMemo(
    () => allMarkers.map((m) => [m.lat, m.lng] as [number, number]),
    [allMarkers]
  );

  const polylineEntries = useMemo(() => {
    const entries: { color: string; positions: [number, number][] }[] = [];
    for (const route of routes) {
      if (selectedTechId && route.tech_id !== selectedTechId) continue;
      const key = `${route.service_day}:${route.tech_id}`;
      const pl = polylines[key];
      if (pl?.polyline?.length) {
        entries.push({
          color: route.tech_color || "#3B82F6",
          positions: pl.polyline,
        });
      }
    }
    return entries;
  }, [routes, polylines, selectedTechId]);

  if (allMarkers.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        No stops to display. Run optimization first.
      </div>
    );
  }

  return (
    <MapContainer
      center={[allMarkers[0].lat, allMarkers[0].lng]}
      zoom={12}
      className="h-full w-full rounded-md"
      style={{ minHeight: 400 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds markers={bounds} />

      {allMarkers.map((m) => (
        <Marker
          key={`${m.propertyId}-${m.seq}`}
          position={[m.lat, m.lng]}
          icon={createColoredIcon(m.color)}
          eventHandlers={
            onStopClick
              ? { click: () => onStopClick(m.propertyId) }
              : undefined
          }
        >
          <Popup>
            <span className="text-sm">{m.label}</span>
          </Popup>
        </Marker>
      ))}

      {polylineEntries.map((pl, i) => (
        <Polyline
          key={i}
          positions={pl.positions}
          pathOptions={{ color: pl.color, weight: 3, opacity: 0.7 }}
        />
      ))}
    </MapContainer>
  );
}
