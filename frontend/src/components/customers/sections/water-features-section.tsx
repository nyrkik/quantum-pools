"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Copy, Check, DogIcon, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Permissions } from "@/lib/permissions";
import type { Customer, Property, WaterFeature, PropertyPhoto } from "../customer-types";
import { WfTile, type WaterFeature as WfTileWF, type TechAssignment } from "@/components/water-features/wf-tile";
import { AddWfForm } from "@/components/water-features/add-wf-form";
import { getBackendOrigin } from "@/lib/api";

const API_BASE = typeof window !== "undefined" ? getBackendOrigin() : "http://localhost:7061";

interface WaterFeaturesSectionProps {
  customer: Customer;
  properties: Property[];
  perms: Permissions;
  onUpdate: () => void;
}

export function WaterFeaturesSection({ customer, properties, perms, onUpdate }: WaterFeaturesSectionProps) {
  const [fullWfs, setFullWfs] = useState<WaterFeature[]>([]);
  const [loading, setLoading] = useState(true);
  const [heroImages, setHeroImages] = useState<Record<string, PropertyPhoto>>({});
  const [techAssignments, setTechAssignments] = useState<Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>>({});
  const [wfProfitability, setWfProfitability] = useState<Record<string, { margin_pct: number; suggested_rate: number }>>({});
  const [latestReadings, setLatestReadings] = useState<Record<string, { ph?: number | null; free_chlorine?: number | null; cyanuric_acid?: number | null; created_at?: string }>>({});
  const [selectedWfId, setSelectedWfId] = useState<string | null>(null);

  useEffect(() => {
    if (properties.length === 0) { setLoading(false); return; }

    const loadAll = async () => {
      setLoading(true);
      try {
        const [wfResults, heroes, assignments] = await Promise.all([
          Promise.all(properties.map((p) => api.get<WaterFeature[]>(`/v1/water-features/property/${p.id}`).catch(() => []))),
          api.get<Record<string, PropertyPhoto>>("/v1/photos/heroes").catch(() => ({})),
          api.get<Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>>("/v1/routes/tech-assignments").catch(() => ({})),
        ]);
        setFullWfs(wfResults.flat());
        setHeroImages(heroes);
        setTechAssignments(assignments);

        // Readings
        const readingResults = await Promise.all(
          properties.map((p) =>
            api.get<Array<{ water_feature_id?: string | null; ph?: number | null; free_chlorine?: number | null; cyanuric_acid?: number | null; created_at: string }>>(`/v1/visits/readings/property/${p.id}?limit=50`).catch(() => [])
          )
        );
        const readingMap: Record<string, { ph?: number | null; free_chlorine?: number | null; cyanuric_acid?: number | null; created_at?: string }> = {};
        for (const readings of readingResults) {
          for (const r of readings) {
            const key = r.water_feature_id || "property";
            if (!readingMap[key]) readingMap[key] = r;
          }
        }
        setLatestReadings(readingMap);

        // Profitability
        api.get<Array<{ wf_id: string; margin_pct: number; suggested_rate: number; customer_id: string }>>("/v1/profitability/gaps")
          .then((gaps) => {
            const map: Record<string, { margin_pct: number; suggested_rate: number }> = {};
            for (const g of gaps) {
              if (g.customer_id === customer.id) map[g.wf_id] = { margin_pct: g.margin_pct, suggested_rate: g.suggested_rate };
            }
            setWfProfitability(map);
          })
          .catch(() => {});
      } finally {
        setLoading(false);
      }
    };
    loadAll();
  }, [properties, customer.id]);

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {properties.map((prop) => {
        const propWfs = fullWfs.filter((wf) => wf.property_id === prop.id);
        const firstTech = techAssignments[prop.id]?.[0];

        return (
          <div key={prop.id} className="space-y-3">
            {/* Property header with address */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 text-sm font-medium">
                <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span>{prop.name || prop.address.split(",")[0]}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {prop.dog_on_property && (
                  <Badge variant="outline" className="border-amber-400 text-amber-600 gap-1 text-[10px]">
                    <DogIcon className="h-3 w-3" />
                    Dog
                  </Badge>
                )}
              </div>
            </div>
            {/* Inline access info */}
            <PropertyAccessInline property={prop} />
            {propWfs.length > 0 ? (
              propWfs.map((wf) => (
                <WfTile
                  key={wf.id}
                  wf={wf as WfTileWF}
                  propertyId={prop.id}
                  perms={perms}
                  techAssignment={firstTech as TechAssignment | undefined}
                  marginPct={wfProfitability[wf.id]?.margin_pct ?? null}
                  suggestedRate={wfProfitability[wf.id]?.suggested_rate ?? null}
                  customerType={customer.customer_type}
                  collapsed={selectedWfId !== null && selectedWfId !== wf.id}
                  propertyContext={{
                    gate_code: prop.gate_code,
                    access_instructions: prop.access_instructions,
                    dog_on_property: prop.dog_on_property,
                    service_day_pattern: prop.service_day_pattern,
                  }}
                  customerContext={{ preferred_day: customer.preferred_day }}
                  lastReading={latestReadings[wf.id] || null}
                  onExpand={() => setSelectedWfId(wf.id)}
                  onUpdated={() => { onUpdate(); }}
                  onDeleted={() => { onUpdate(); }}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground text-center py-3">No water features</p>
            )}
            {perms.canEditCustomers && (
              <AddWfForm propertyId={prop.id} customerType={customer.customer_type} onCreated={onUpdate} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* Inline access info — gate code (copyable) + access notes */
function PropertyAccessInline({ property }: { property: Property }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!property.gate_code) return;
    navigator.clipboard.writeText(property.gate_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasAccess = property.gate_code || property.access_instructions;
  if (!hasAccess) return null;

  return (
    <div className="flex items-center gap-4 flex-wrap text-sm">
      {property.gate_code && (
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 bg-muted/50 rounded-md px-3 py-1.5 hover:bg-muted transition-colors"
          title="Tap to copy"
        >
          <span className="text-[10px] text-muted-foreground uppercase tracking-wide">Gate</span>
          <span className="font-bold tracking-wider">{property.gate_code}</span>
          {copied ? (
            <Check className="h-3 w-3 text-green-600" />
          ) : (
            <Copy className="h-3 w-3 text-muted-foreground" />
          )}
        </button>
      )}
      {property.access_instructions && (
        <span className="text-muted-foreground">{property.access_instructions}</span>
      )}
    </div>
  );
}
