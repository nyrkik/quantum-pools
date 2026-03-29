"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Property } from "../customer-types";

interface InspectionInfo {
  id: string;
  inspection_date: string | null;
  total_violations: number;
  closure_required: boolean;
}

interface PropertyInspections {
  propertyId: string;
  propertyLabel: string;
  wfLabels: string[];
  inspections: InspectionInfo[];
}

interface InspectionsTileProps {
  properties: Property[];
}

export function InspectionsTile({ properties }: InspectionsTileProps) {
  const [groups, setGroups] = useState<PropertyInspections[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const results: PropertyInspections[] = [];
      for (const prop of properties) {
        try {
          const data = await api.get<InspectionInfo[]>(`/v1/emd/property/${prop.id}/inspections`);
          const inspections = (data || []).slice(0, 5);
          if (inspections.length > 0) {
            const wfs = prop.water_features || [];
            results.push({
              propertyId: prop.id,
              propertyLabel: prop.name || prop.address,
              wfLabels: wfs.map((wf) => wf.name || wf.water_type),
              inspections,
            });
          }
        } catch {
          // skip
        }
      }
      setGroups(results);
      setLoading(false);
    }
    load();
  }, [properties]);

  if (loading || groups.length === 0) return null;

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          Inspections
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {groups.map((group) => (
          <div key={group.propertyId}>
            {groups.length > 1 && (
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium mb-1">
                {group.propertyLabel}
                {group.wfLabels.length > 0 && ` — ${group.wfLabels.join(", ")}`}
              </p>
            )}
            <div className="space-y-0.5">
              {group.inspections.map((insp) => {
                const passed = insp.total_violations === 0 && !insp.closure_required;
                const dateStr = insp.inspection_date
                  ? new Date(insp.inspection_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                  : "No date";
                return (
                  <div key={insp.id} className="flex items-center justify-between text-xs py-0.5">
                    <span className="text-muted-foreground">{dateStr}</span>
                    {passed ? (
                      <Badge variant="default" className="bg-green-600 text-[10px] px-1.5">Pass</Badge>
                    ) : (
                      <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px] px-1.5">
                        {insp.total_violations} violation{insp.total_violations !== 1 ? "s" : ""}
                      </Badge>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
