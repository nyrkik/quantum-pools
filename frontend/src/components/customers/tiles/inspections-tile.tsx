"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck } from "lucide-react";
import type { Property } from "../customer-types";

interface InspectionRow {
  id: string;
  inspection_date: string | null;
  inspection_type: string | null;
  total_violations: number;
  major_violations: number;
  closure_required: boolean;
}

interface InspectionsTileProps {
  properties: Property[];
  customerId: string;
}

export function InspectionsTile({ properties, customerId }: InspectionsTileProps) {
  const router = useRouter();
  const [inspections, setInspections] = useState<InspectionRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (properties.length === 0) { setLoaded(true); return; }
    let cancelled = false;
    Promise.all(
      properties.map((p) =>
        api.get<InspectionRow[]>(`/v1/emd/property/${p.id}/inspections`).catch(() => [])
      )
    ).then((results) => {
      if (!cancelled) {
        const all = results
          .flat()
          .sort((a, b) => {
            const da = a.inspection_date ? new Date(a.inspection_date).getTime() : 0;
            const db = b.inspection_date ? new Date(b.inspection_date).getTime() : 0;
            return db - da;
          })
          .slice(0, 3);
        setInspections(all);
      }
    }).finally(() => {
      if (!cancelled) setLoaded(true);
    });
    return () => { cancelled = true; };
  }, [properties]);

  // Don't render tile at all if no inspection data
  if (!loaded || inspections.length === 0) return null;

  return (
    <Card
      className="shadow-sm cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => router.push(`/emd?customer_id=${customerId}`)}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <span className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            Inspections
          </span>
          <span className="text-xs text-muted-foreground font-normal">View all</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {inspections.map((insp) => {
            const passed = insp.total_violations === 0 && !insp.closure_required;
            const dateStr = insp.inspection_date
              ? new Date(insp.inspection_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
              : "No date";

            return (
              <div key={insp.id} className="flex items-center justify-between py-2 text-sm">
                <div className="min-w-0">
                  <span className="text-xs text-muted-foreground">{dateStr}</span>
                  {insp.inspection_type && (
                    <span className="ml-2 text-xs capitalize">{insp.inspection_type}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {insp.closure_required && (
                    <Badge variant="destructive" className="text-[10px] px-1.5">Closed</Badge>
                  )}
                  {insp.major_violations > 0 && (
                    <Badge variant="outline" className="border-red-400 text-red-600 text-[10px] px-1.5">
                      {insp.major_violations} major
                    </Badge>
                  )}
                  {passed ? (
                    <Badge variant="default" className="bg-green-600 text-[10px] px-1.5">Pass</Badge>
                  ) : insp.total_violations > 0 ? (
                    <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px] px-1.5">
                      {insp.total_violations} violations
                    </Badge>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
