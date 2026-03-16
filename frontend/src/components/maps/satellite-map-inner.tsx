"use client";

import { useEffect, useMemo, useRef, useCallback, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { SatelliteMapProps, PropertyGroup } from "./satellite-map";

// Fix default marker icon paths
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// Property marker — dot with optional red selection ring and label
function createPropertyIcon(color: string, size: number, selected: boolean, label?: string): L.DivIcon {
  const ring = selected ? `border:3px solid #ef4444; box-shadow:0 0 0 2px white, 0 2px 6px rgba(0,0,0,.5);` : `border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,.4);`;
  const totalSize = selected ? size + 6 : size;
  const labelHtml = label ? `<div style="
    position:absolute;
    top:${totalSize + 2}px;left:50%;
    transform:translateX(-50%);
    white-space:nowrap;
    font-size:10px;
    font-weight:600;
    color:white;
    text-shadow:0 1px 3px rgba(0,0,0,.8), 0 0 2px rgba(0,0,0,.6);
    pointer-events:none;
  ">${label}</div>` : "";
  return L.divIcon({
    className: "",
    html: `<div style="position:relative;">
      <div style="
        background:${color};
        width:${size}px;height:${size}px;
        border-radius:50%;
        ${ring}
      "></div>${labelHtml}</div>`,
    iconSize: [totalSize, totalSize],
    iconAnchor: [totalSize / 2, totalSize / 2],
  });
}

// Pool pin — small diamond with name label below
function createPoolPin(name?: string): L.DivIcon {
  const nameHtml = name ? `<div style="
    position:absolute;
    top:12px;left:50%;
    transform:translateX(-50%);
    white-space:nowrap;
    font-size:9px;
    font-weight:600;
    color:white;
    text-shadow:0 1px 3px rgba(0,0,0,.8), 0 0 2px rgba(0,0,0,.6);
    pointer-events:none;
  ">${name}</div>` : "";
  return L.divIcon({
    className: "",
    html: `<div style="position:relative;">
      <div style="
        width:10px;height:10px;
        background:#3B82F6;
        border:2px solid white;
        border-radius:2px;
        transform:rotate(45deg);
        box-shadow:0 1px 3px rgba(0,0,0,.4);
      "></div>${nameHtml}</div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
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

function getPropertyIcon(pg: PropertyGroup, isSelected: boolean, zoom: number) {
  const color = pg.best_status === "pinned" ? "#22c55e" : pg.best_status === "analyzed" ? "#eab308" : "#ef4444";
  const showRing = isSelected && zoom < 17;
  const size = isSelected ? 16 : 14;
  const label = isSelected ? pg.customer_name : undefined;
  return createPropertyIcon(color, size, showRing, label);
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

function MapActionsProvider({ actionsRef, selectedLat, selectedLng, bounds }: {
  actionsRef?: React.MutableRefObject<{ zoomIn: () => void; zoomOut: () => void; getZoom: () => number } | null>;
  selectedLat: number | null;
  selectedLng: number | null;
  bounds: [number, number][];
}) {
  const map = useMap();

  useEffect(() => {
    if (!actionsRef) return;
    actionsRef.current = {
      getZoom: () => map.getZoom(),
      zoomIn: () => {
        const lat = selectedLat ?? map.getCenter().lat;
        const lng = selectedLng ?? map.getCenter().lng;
        map.flyTo([lat, lng], 18, { duration: 0.6 });
      },
      zoomOut: () => {
        if (bounds.length > 0) {
          map.flyToBounds(L.latLngBounds(bounds.map(([a, b]) => [a, b])), { padding: [40, 40], duration: 0.6 });
        }
      },
    };
  }, [map, actionsRef, selectedLat, selectedLng, bounds]);
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

function PropertyMarkers({ propertyGroups, selectedPropertyId, zoomLevel, onPropertySelect }: {
  propertyGroups: PropertyGroup[];
  selectedPropertyId: string | null;
  zoomLevel: number;
  onPropertySelect: (id: string) => void;
}) {
  const map = useMap();
  return (
    <>
      {propertyGroups.map((pg) => {
        if (!pg.lat || !pg.lng) return null;
        const isSelected = pg.property_id === selectedPropertyId;
        const pinned = pg.bows.find((b) => b.pool_lat && b.pool_lng);
        return (
          <Marker
            key={pg.property_id}
            position={[pg.lat, pg.lng]}
            icon={getPropertyIcon(pg, isSelected, zoomLevel)}
            eventHandlers={{
              click: () => {
                onPropertySelect(pg.property_id);
                const targetLat = pinned?.pool_lat ?? pg.lat;
                const targetLng = pinned?.pool_lng ?? pg.lng;
                if (targetLat && targetLng) {
                  map.flyTo([targetLat, targetLng], 18, { duration: 0.8 });
                }
              },
            }}
            zIndexOffset={isSelected ? 1000 : 0}
          >
            <Tooltip direction="top" offset={[0, -10]} className="property-tooltip">
              {pg.customer_name}
            </Tooltip>
          </Marker>
        );
      })}
    </>
  );
}

function ZoomTracker({ onZoomLevel }: { onZoomLevel: (z: number) => void }) {
  const map = useMap();
  useEffect(() => {
    const handler = () => onZoomLevel(map.getZoom());
    handler();
    map.on("zoomend", handler);
    return () => { map.off("zoomend", handler); };
  }, [map, onZoomLevel]);
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
  onZoomChange,
}: SatelliteMapProps) {
  const [zoomLevel, setZoomLevel] = useState(12);
  const handleZoom = useCallback((z: number) => {
    setZoomLevel(z);
    onZoomChange?.(z);
  }, [onZoomChange]);
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
      <ZoomTracker onZoomLevel={handleZoom} />
      <MapClickHandler onPinPlace={onPinPlace} enabled={!!selectedPropertyId} />
      <MapActionsProvider
        actionsRef={actionsRef}
        selectedLat={(() => {
          const pinned = selectedGroup?.bows.find((b) => b.pool_lat);
          return pinned?.pool_lat ?? selectedGroup?.lat ?? null;
        })()}
        selectedLng={(() => {
          const pinned = selectedGroup?.bows.find((b) => b.pool_lng);
          return pinned?.pool_lng ?? selectedGroup?.lng ?? null;
        })()}
        bounds={bounds}
      />

      {flyTo && selectedGroup && selectedPropertyId && selectedGroup.lat && selectedGroup.lng && (() => {
        const pinned = selectedGroup.bows.find((b) => b.pool_lat && b.pool_lng);
        return (
          <PanToSelected
            lat={pinned?.pool_lat ?? selectedGroup.lat}
            lng={pinned?.pool_lng ?? selectedGroup.lng}
            propertyId={selectedPropertyId}
          />
        );
      })()}

      {/* Saved pool pins for selected property */}
      {selectedGroup && selectedGroup.bows.map((bow) => {
        if (!bow.pool_lat || !bow.pool_lng) return null;
        const name = bow.bow_name || (bow.water_type === "pool" ? "Pool" : bow.water_type.replace("_", " "));
        return (
          <Marker
            key={`pin-${bow.id}`}
            position={[bow.pool_lat, bow.pool_lng]}
            icon={createPoolPin(zoomLevel >= 17 ? name : undefined)}
            zIndexOffset={1500}
          >
            <Popup>
              <div className="text-xs font-medium">{name}</div>
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

      <PropertyMarkers
        propertyGroups={propertyGroups}
        selectedPropertyId={selectedPropertyId}
        zoomLevel={zoomLevel}
        onPropertySelect={onPropertySelect}
      />
    </MapContainer>
  );
}
