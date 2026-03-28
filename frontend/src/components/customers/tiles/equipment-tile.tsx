"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Wrench } from "lucide-react";
import type { Property, WaterFeature } from "../customer-types";

interface EquipmentTileProps {
  properties: Property[];
}

const EQUIP_FIELDS: { key: keyof WaterFeature; label: string }[] = [
  { key: "pump_type", label: "Pump" },
  { key: "filter_type", label: "Filter" },
  { key: "heater_type", label: "Heater" },
  { key: "chlorinator_type", label: "Chlorinator" },
  { key: "automation_system", label: "Automation" },
];

export function EquipmentTile({ properties }: EquipmentTileProps) {
  const [wfs, setWfs] = useState<WaterFeature[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (properties.length === 0) { setLoaded(true); return; }
    let cancelled = false;
    Promise.all(
      properties.map((p) =>
        api.get<WaterFeature[]>(`/v1/water-features/property/${p.id}`).catch(() => [])
      )
    ).then((results) => {
      if (!cancelled) setWfs(results.flat());
    }).finally(() => {
      if (!cancelled) setLoaded(true);
    });
    return () => { cancelled = true; };
  }, [properties]);

  if (!loaded) return null;

  // Only show WFs that have at least one equipment field set
  const wfsWithEquip = wfs.filter((wf) =>
    EQUIP_FIELDS.some((f) => wf[f.key])
  );

  if (wfsWithEquip.length === 0) return null;

  const showSubHeaders = wfsWithEquip.length > 1;

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Wrench className="h-4 w-4 text-muted-foreground" />
          Equipment
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {wfsWithEquip.map((wf) => (
          <div key={wf.id} className="space-y-1">
            {showSubHeaders && (
              <p className="text-xs font-medium text-muted-foreground">
                {wf.name || wf.water_type.replace("_", " ")}
              </p>
            )}
            {EQUIP_FIELDS.map((f) => {
              const val = wf[f.key] as string | null;
              if (!val) return null;
              return (
                <div key={f.key} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{f.label}</span>
                  <span className="font-medium truncate ml-4 text-right">{val}</span>
                </div>
              );
            })}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
