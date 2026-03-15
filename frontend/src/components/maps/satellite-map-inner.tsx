"use client";

import { useEffect, useMemo, useRef, useCallback } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import type { SatelliteMapProps, PropertyGroup } from "./satellite-map";

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

// Saved pool pin — small blue diamond, visible when zoomed in on selected property
function createPoolPin(label?: string): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      position:relative;
      width:14px;height:14px;
      background:#3B82F6;
      border:2px solid white;
      border-radius:3px;
      transform:rotate(45deg);
      box-shadow:0 1px 4px rgba(0,0,0,.4);
    ">${label ? `<span style="
      position:absolute;
      top:50%;left:50%;
      transform:translate(-50%,-50%) rotate(-45deg);
      font-size:8px;
      font-weight:700;
      color:white;
      line-height:1;
    ">${label}</span>` : ""}</div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

// Active placement pin — red crosshair
const pinIcon = L.divIcon({
  className: "",
  html: `<div style="
    width:20px;height:20px;
    border:3px solid #ef4444;
    border-radius:50%;
    background:rgba(239,68,68,0.2);
    box-shadow:0 0 0 2px white, 0 2px 8px rgba(0,0,0,.4);
  "><div style="
    width:4px;height:4px;
    background:#ef4444;
    border-radius:50%;
    position:absolute;
    top:50%;left:50%;
    transform:translate(-50%,-50%);
  "></div></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

function getPropertyIcon(pg: PropertyGroup, isSelected: boolean) {
  if (isSelected) return dotSelected;
  if (pg.best_status === "pinned") return dotGreen;
  if (pg.best_status === "analyzed") return dotYellow;
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

function PanToSelected({ lat, lng, propertyId }: { lat: number; lng: number; propertyId: string }) {
  const map = useMap();
  const prevRef = useRef<string>("");
  useEffect(() => {
    if (propertyId === prevRef.current) return;
    prevRef.current = propertyId;
    map.panTo([lat, lng], { animate: true, duration: 0.6 });
  }, [lat, lng, propertyId, map]);
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
            map.flyTo(savedCenter.current!, savedZoom.current, { duration: 0.6 });
            savedZoom.current = null;
            savedCenter.current = null;
          } else {
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
  propertyGroups,
  selectedPropertyId,
  pinPosition,
  flyTo,
  actionsRef,
  onPropertySelect,
  onPinPlace,
}: SatelliteMapProps) {
  const bounds = useMemo(
    () => propertyGroups.filter((pg) => pg.lat && pg.lng).map((pg) => [pg.lat!, pg.lng!] as [number, number]),
    [propertyGroups]
  );

  const selectedGroup = selectedPropertyId
    ? propertyGroups.find((pg) => pg.property_id === selectedPropertyId)
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
      <MapClickHandler onPinPlace={onPinPlace} enabled={!!selectedPropertyId} />
      <MapActionsProvider
        actionsRef={actionsRef}
        selectedLat={selectedGroup?.lat ?? null}
        selectedLng={selectedGroup?.lng ?? null}
        onZoomChange={() => { /* parent reads ref.current.isZoomedIn */ }}
      />

      {flyTo && selectedGroup && selectedPropertyId && selectedGroup.lat && selectedGroup.lng && (
        <PanToSelected
          lat={selectedGroup.lat}
          lng={selectedGroup.lng}
          propertyId={selectedPropertyId}
        />
      )}

      {/* Saved pool pins for selected property */}
      {selectedGroup && selectedGroup.bows.map((bow, idx) => {
        if (!bow.pool_lat || !bow.pool_lng) return null;
        const label = selectedGroup.bows.length > 1 ? String(idx + 1) : undefined;
        return (
          <Marker
            key={`pin-${bow.id}`}
            position={[bow.pool_lat, bow.pool_lng]}
            icon={createPoolPin(label)}
            zIndexOffset={1500}
          >
            <Popup>
              <div className="text-xs font-medium">{bow.bow_name || bow.water_type}</div>
            </Popup>
          </Marker>
        );
      })}

      {/* Active placement pin — red crosshair */}
      {pinPosition && (
        <Marker
          position={[pinPosition.lat, pinPosition.lng]}
          icon={pinIcon}
          zIndexOffset={2000}
        />
      )}

      {propertyGroups.map((pg) => {
        if (!pg.lat || !pg.lng) return null;
        const isSelected = pg.property_id === selectedPropertyId;
        return (
          <Marker
            key={pg.property_id}
            position={[pg.lat, pg.lng]}
            icon={getPropertyIcon(pg, isSelected)}
            eventHandlers={{ click: () => onPropertySelect(pg.property_id) }}
            zIndexOffset={isSelected ? 1000 : 0}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-medium">{pg.customer_name}</div>
                <div className="text-muted-foreground">{pg.address}</div>
                {pg.bows.length > 1 && (
                  <div className="text-xs text-muted-foreground">{pg.bows.length} pools</div>
                )}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
