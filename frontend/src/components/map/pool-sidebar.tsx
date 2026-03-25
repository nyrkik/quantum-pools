"use client";

import { RefObject } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Search,
  Building2,
  Home,
  Droplets,
  Waves,
  WavesLadder,
} from "lucide-react";
import type { PropertyGroup } from "@/components/maps/satellite-map";
import type { PoolBowWithCoords } from "@/types/satellite";

function waterTypeIcon(type: string, className: string) {
  switch (type) {
    case "spa": case "hot_tub": return <Droplets className={className} />;
    case "fountain": case "water_feature": case "wading_pool": return <Waves className={className} />;
    default: return <WavesLadder className={className} />;
  }
}

interface PoolSidebarProps {
  search: string;
  onSearchChange: (value: string) => void;
  typeFilter: string | null;
  onToggleType: (type: string) => void;
  commercialGroups: PropertyGroup[];
  residentialGroups: PropertyGroup[];
  filteredGroups: PropertyGroup[];
  propertyGroups: PropertyGroup[];
  selectedPropertyId: string | null;
  highlightedBowId: string | null;
  onPropertySelect: (propertyId: string) => void;
  onHighlightBow: (bowId: string | null) => void;
  listRef: RefObject<HTMLDivElement | null>;
}

export default function PoolSidebar({
  search,
  onSearchChange,
  typeFilter,
  onToggleType,
  commercialGroups,
  residentialGroups,
  filteredGroups,
  propertyGroups,
  selectedPropertyId,
  highlightedBowId,
  onPropertySelect,
  onHighlightBow,
  listRef,
}: PoolSidebarProps) {
  const countBows = (groups: PropertyGroup[]) => groups.reduce((sum, g) => sum + g.wfs.length, 0);

  return (
    <>
      {/* Search + type toggles */}
      <div className="flex items-center gap-1.5 mb-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
        <Button
          variant={typeFilter === "commercial" ? "default" : "outline"}
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={() => onToggleType("commercial")}
          title="Commercial"
        >
          <Building2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant={typeFilter === "residential" ? "default" : "outline"}
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={() => onToggleType("residential")}
          title="Residential"
        >
          <Home className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Property list — commercial first */}
      <div ref={listRef} className="flex-1 overflow-y-auto space-y-0 pr-1">
        {[
          { label: "Commercial", Icon: Building2, items: commercialGroups, show: typeFilter === null || typeFilter === "commercial" },
          { label: "Residential", Icon: Home, items: residentialGroups, show: typeFilter === null || typeFilter === "residential" },
        ].map((section) => section.show && section.items.length > 0 && (
          <div key={section.label}>
            <div className="flex items-center gap-2 px-1 pt-3 pb-1.5 mb-0.5 sticky top-0 z-10 bg-background border-b border-border">
              <section.Icon className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{section.label}</span>
              <span className="text-[11px] text-muted-foreground/50">
                {section.items.length}
                {countBows(section.items) !== section.items.length && (
                  <> ({countBows(section.items)} features)</>
                )}
              </span>
              <div className="flex-1 border-t border-border ml-1" />
            </div>
            <div className="space-y-0.5 mb-2">
              {section.items.map((g) => {
                const isSelected = g.property_id === selectedPropertyId;
                return (
                  <div key={g.property_id}>
                    <button
                      id={`prop-${g.property_id}`}
                      onClick={() => { onPropertySelect(g.property_id); onHighlightBow(null); }}
                      className={`w-full text-left rounded-md px-3 py-2 text-sm transition-colors ${
                        isSelected
                          ? "bg-accent border-l-3 border-l-primary font-medium"
                          : "hover:bg-muted"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
                            g.best_status === "pinned"
                              ? "bg-green-500"
                              : g.best_status === "analyzed"
                              ? "bg-yellow-500"
                              : "bg-red-500"
                          }`}
                        />
                        <span className="font-medium truncate flex-1">
                          {g.customer_name}
                        </span>
                        {g.wfs.length > 1 && (
                          <Badge variant="secondary" className="text-[9px] px-1.5 py-0 shrink-0">
                            {g.wfs.length}
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs truncate ml-4 text-muted-foreground">
                        {g.address}
                      </div>
                      {g.city && (
                        <div className="text-xs truncate ml-4 text-muted-foreground/70">
                          {g.city}
                        </div>
                      )}
                      {g.tech_name && (
                        <div className="text-xs truncate ml-4 text-muted-foreground flex items-center gap-1.5">
                          <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: g.tech_color || '#94a3b8' }} />
                          {g.tech_name}
                        </div>
                      )}
                    </button>
                    {/* Child WF entries — show when selected and multi-WF */}
                    {isSelected && g.wfs.length > 1 && (
                      <div className="ml-6 border-l-2 border-border pl-2 py-1 space-y-0.5">
                        {g.wfs.map((b: PoolBowWithCoords) => (
                          <button
                            key={b.id}
                            onClick={() => {
                              onHighlightBow(b.id);
                              setTimeout(() => {
                                document.getElementById(`wf-tile-${b.id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                              }, 50);
                            }}
                            className={`w-full text-left rounded px-2 py-1 text-xs transition-colors ${
                              highlightedBowId === b.id
                                ? "bg-accent font-medium"
                                : "hover:bg-muted text-muted-foreground"
                            }`}
                          >
                            <div className="flex items-center gap-1.5">
                              {waterTypeIcon(b.water_type, "h-2.5 w-2.5 text-blue-500 shrink-0")}
                              <span className="truncate">{b.wf_name || b.water_type.replace("_", " ")}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        {filteredGroups.length === 0 && (
          <div className="text-center py-6 text-sm text-muted-foreground">No matching properties</div>
        )}
      </div>
      <div className="text-[11px] text-muted-foreground pt-1 border-t mt-1">
        {filteredGroups.length} of {propertyGroups.length} properties shown
      </div>
    </>
  );
}
