"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck, ChevronDown } from "lucide-react";
import type { Property } from "../customer-types";

interface InspectionRow {
  id: string;
  inspection_date: string | null;
  inspection_type: string | null;
  total_violations: number;
  major_violations: number;
  closure_required: boolean;
  violations?: { description: string; severity: string }[];
}

interface InspectionsTileProps {
  properties: Property[];
  customerId: string;
}

export function InspectionsTile({ properties, customerId }: InspectionsTileProps) {
  const [inspections, setInspections] = useState<InspectionRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (properties.length === 0) { setLoaded(true); return; }
    let cancelled = false;
    Promise.all(
      properties.map((p) =>
        api.get<InspectionRow[]>(`/v1/emd/property/${p.id}/inspections`).catch(() => [])
      )
    ).then((results) => {
      if (!cancelled) {
        const all = results.flat()
          .sort((a, b) => {
            const da = a.inspection_date ? new Date(a.inspection_date).getTime() : 0;
            const db = b.inspection_date ? new Date(b.inspection_date).getTime() : 0;
            return db - da;
          })
          .slice(0, 5);
        setInspections(all);
      }
    }).finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [properties]);

  if (!loaded || inspections.length === 0) return null;

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <span className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            Inspections
          </span>
          <Link href={`/emd?customer_id=${customerId}`} className="text-xs text-muted-foreground hover:text-primary font-normal">
            View all →
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {inspections.map((insp) => {
            const passed = insp.total_violations === 0 && !insp.closure_required;
            const dateStr = insp.inspection_date
              ? new Date(insp.inspection_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
              : "No date";
            const isExpanded = expandedId === insp.id;

            return (
              <div key={insp.id}>
                <div
                  className="flex items-center justify-between py-2 text-sm cursor-pointer hover:bg-muted/50 -mx-2 px-2 rounded transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : insp.id)}
                >
                  <div className="min-w-0 flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{dateStr}</span>
                    {insp.inspection_type && (
                      <span className="text-xs capitalize">{insp.inspection_type}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {insp.closure_required && (
                      <Badge variant="destructive" className="text-[10px] px-1.5">Closed</Badge>
                    )}
                    {passed ? (
                      <Badge variant="default" className="bg-green-600 text-[10px] px-1.5">Pass</Badge>
                    ) : insp.total_violations > 0 ? (
                      <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px] px-1.5">
                        {insp.total_violations} violations
                      </Badge>
                    ) : null}
                    <ChevronDown className={`h-3 w-3 text-muted-foreground transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                  </div>
                </div>
                {isExpanded && insp.violations && insp.violations.length > 0 && (
                  <div className="ml-4 pb-2 space-y-1">
                    {insp.violations.map((v, i) => (
                      <p key={i} className="text-xs text-muted-foreground">
                        <span className={v.severity === "major" ? "text-red-600 font-medium" : ""}>{v.severity}: </span>
                        {v.description}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
