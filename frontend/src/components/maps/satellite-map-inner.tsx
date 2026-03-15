"use client";

import { useEffect, useMemo, useRef, useCallback } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import type { SatelliteMapProps } from "./satellite-map";

// Fix default marker icon paths
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function createDot(color: string, size = 12): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      background:${color};
      width:${size}px;height:${size}px;
      border-radius:50%;
      border:2px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.4);
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const dotGreen = createDot("#22c55e");
const dotYellow = createDot("#eab308");
const dotRed = createDot("#ef4444");
const dotSelected = createDot("#3B82F6", 16);

function getBowIcon(bow: { has_analysis: boolean; pool_lat: number | null }, isSelected: boolean) {
  if (isSelected) return dotSelected;
  if (bow.has_analysis && bow.pool_lat) return dotGreen;
  if (bow.has_analysis) return dotYellow;
  return dotRed;
}

function FitBounds({ markers }: { markers: [number, number][] }) {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || markers.length === 0) return;
    const bounds = L.latLngBounds(markers.map(([lat, lng]) => [lat, lng]));
    map.fitBounds(bounds, { padding: [40, 40] });
    fitted.current = true;
  }, [markers, map]);
  return null;
}

function PanToSelected({ lat, lng, bowId }: { lat: number; lng: number; bowId: string }) {
  const map = useMap();
  const prevRef = useRef<string>("");
  useEffect(() => {
    if (bowId === prevRef.current) return;
    prevRef.current = bowId;
    map.panTo([lat, lng], { animate: true, duration: 0.6 });
  }, [lat, lng, bowId, map]);
  return null;
}

function MapActionsProvider({ actionsRef, selectedLat, selectedLng, onZoomChange }: {
  actionsRef?: React.MutableRefObject<{ toggleZoom: () => void; isZoomedIn: boolean } | null>;
  selectedLat: number | null;
  selectedLng: number | null;
  onZoomChange: () => void;
}) {
  const map = useMap();
  const savedZoom = useRef<number | null>(null);
  const savedCenter = useRef<L.LatLng | null>(null);

  useEffect(() => {
    if (!actionsRef) return;
    const update = () => {
      actionsRef.current = {
        isZoomedIn: savedZoom.current !== null,
        toggleZoom: () => {
          if (savedZoom.current !== null) {
            // Zoom out — restore previous view
            map.flyTo(savedCenter.current!, savedZoom.current, { duration: 0.6 });
            savedZoom.current = null;
            savedCenter.current = null;
          } else {
            // Zoom in — save current view then zoom
            savedZoom.current = map.getZoom();
            savedCenter.current = map.getCenter();
            const lat = selectedLat ?? map.getCenter().lat;
            const lng = selectedLng ?? map.getCenter().lng;
            map.flyTo([lat, lng], 18, { duration: 0.6 });
          }
          onZoomChange();
        },
      };
    };
    update();
    map.on("zoomend", update);
    return () => { map.off("zoomend", update); };
  }, [map, actionsRef, selectedLat, selectedLng, onZoomChange]);
  return null;
}

function MapClickHandler({ onPinPlace, enabled }: { onPinPlace: (lat: number, lng: number) => void; enabled: boolean }) {
  useMapEvents({
    click(e) {
      if (enabled) {
        onPinPlace(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

export default function SatelliteMapInner({
  poolBows,
  selectedBowId,
  pinPosition,
  flyTo,
  actionsRef,
  onBowSelect,
  onPinPlace,
}: SatelliteMapProps) {
  const bounds = useMemo(
    () => poolBows.filter((b) => b.lat && b.lng).map((b) => [b.lat!, b.lng!] as [number, number]),
    [poolBows]
  );

  const selectedBow = selectedBowId
    ? poolBows.find((b) => b.id === selectedBowId)
    : null;

  if (bounds.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        No geocoded properties to display.
      </div>
    );
  }

  return (
    <MapContainer
      center={[bounds[0][0], bounds[0][1]]}
      zoom={12}
      className="h-full w-full rounded-md"
      style={{ minHeight: 400 }}
    >
      <TileLayer
        attribution="Tiles &copy; Esri"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      />
      <FitBounds markers={bounds} />
      <MapClickHandler onPinPlace={onPinPlace} enabled={!!selectedBowId} />
      <MapActionsProvider
        actionsRef={actionsRef}
        selectedLat={selectedBow ? (selectedBow.pool_lat ?? selectedBow.lat) : null}
        selectedLng={selectedBow ? (selectedBow.pool_lng ?? selectedBow.lng) : null}
        onZoomChange={() => { /* parent reads ref.current.isZoomedIn */ }}
      />

      {flyTo && selectedBow && selectedBowId && selectedBow.lat && selectedBow.lng && (
        <PanToSelected
          lat={selectedBow.pool_lat ?? selectedBow.lat}
          lng={selectedBow.pool_lng ?? selectedBow.lng}
          bowId={selectedBowId}
        />
      )}

      {poolBows.map((b) => {
        if (!b.lat || !b.lng) return null;
        const isSelected = b.id === selectedBowId;
        const markerLat = isSelected && pinPosition ? pinPosition.lat : (b.pool_lat ?? b.lat);
        const markerLng = isSelected && pinPosition ? pinPosition.lng : (b.pool_lng ?? b.lng);
        return (
          <Marker
            key={b.id}
            position={[markerLat, markerLng]}
            icon={getBowIcon(b, isSelected)}
            eventHandlers={{ click: () => onBowSelect(b.id) }}
            zIndexOffset={isSelected ? 1000 : 0}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-medium">{b.customer_name}</div>
                <div className="text-muted-foreground">{b.address}</div>
                {b.bow_name && <div className="text-xs text-muted-foreground">{b.bow_name}</div>}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
