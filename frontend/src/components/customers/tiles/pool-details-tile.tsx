"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Droplets } from "lucide-react";
import type { Property, WaterFeature } from "../customer-types";

interface PoolDetailsTileProps {
  properties: Property[];
}

export function PoolDetailsTile({ properties }: PoolDetailsTileProps) {
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

  if (!loaded || wfs.length === 0) return null;

  const showSubHeaders = wfs.length > 1;

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Droplets className="h-4 w-4 text-muted-foreground" />
          Pool Details
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {wfs.map((wf) => (
          <div key={wf.id} className="space-y-1">
            {showSubHeaders && (
              <p className="text-xs font-medium text-muted-foreground">
                {wf.name || wf.water_type.replace("_", " ")}
              </p>
            )}
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-sm">
              {wf.pool_gallons != null && (
                <>
                  <span className="text-muted-foreground">Gallons</span>
                  <span className="font-medium text-right">{wf.pool_gallons.toLocaleString()}</span>
                </>
              )}
              {wf.pool_length_ft != null && wf.pool_width_ft != null && (
                <>
                  <span className="text-muted-foreground">Dimensions</span>
                  <span className="font-medium text-right">
                    {wf.pool_length_ft}&apos; x {wf.pool_width_ft}&apos;
                  </span>
                </>
              )}
              {wf.pool_shape && (
                <>
                  <span className="text-muted-foreground">Shape</span>
                  <span className="font-medium text-right capitalize">{wf.pool_shape}</span>
                </>
              )}
              {wf.pool_surface && (
                <>
                  <span className="text-muted-foreground">Surface</span>
                  <span className="font-medium text-right capitalize">{wf.pool_surface}</span>
                </>
              )}
              {wf.sanitizer_type && (
                <>
                  <span className="text-muted-foreground">Sanitizer</span>
                  <span className="font-medium text-right capitalize">{wf.sanitizer_type}</span>
                </>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
