"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import { ClipboardCheck, Camera, Beaker, Clock, Loader2, Check, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Property } from "../customer-types";
import type { VisitContext } from "@/types/visit";

interface VisitSummary {
  id: string;
  scheduled_date: string | null;
  status: string;
  duration_minutes: number | null;
  tech_name: string | null;
  notes: string | null;
  photo_count: number;
  reading_count: number;
  checklist_total: number;
  checklist_completed: number;
}

interface VisitsTileProps {
  properties: Property[];
}

const STATUS_STYLES: Record<string, { variant: "default" | "secondary" | "outline"; className?: string }> = {
  completed: { variant: "default" },
  in_progress: { variant: "outline", className: "border-blue-400 text-blue-600" },
  scheduled: { variant: "secondary" },
  cancelled: { variant: "secondary" },
};

export function VisitsTile({ properties }: VisitsTileProps) {
  const [visits, setVisits] = useState<VisitSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedVisitId, setSelectedVisitId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const allVisits: VisitSummary[] = [];
      for (const prop of properties) {
        try {
          const data = await api.get<VisitSummary[]>(`/v1/visits/history/${prop.id}?limit=5`);
          if (data) allVisits.push(...data);
        } catch {
          // skip
        }
      }
      allVisits.sort((a, b) => {
        const da = a.scheduled_date || "";
        const db = b.scheduled_date || "";
        return db.localeCompare(da);
      });
      setVisits(allVisits.slice(0, 5));
      setLoaded(true);
    }
    load();
  }, [properties]);

  if (!loaded) return null;

  return (
    <>
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <ClipboardCheck className="h-4 w-4 text-muted-foreground" />
            Recent Visits
          </CardTitle>
        </CardHeader>
        <CardContent>
          {visits.length === 0 ? (
            <p className="text-sm text-muted-foreground">No visit history</p>
          ) : (
            <div className="space-y-1">
              {visits.map((v) => {
                const dateStr = v.scheduled_date
                  ? new Date(v.scheduled_date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })
                  : "No date";
                const style = STATUS_STYLES[v.status] || { variant: "secondary" as const };
                return (
                  <div
                    key={v.id}
                    className="flex items-center justify-between py-2 -mx-2 px-2 rounded cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => setSelectedVisitId(v.id)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-sm font-medium w-16 shrink-0">{dateStr}</span>
                      <span className="text-xs text-muted-foreground truncate">{v.tech_name || "Unassigned"}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {v.duration_minutes && (
                        <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                          <Clock className="h-2.5 w-2.5" />{v.duration_minutes}m
                        </span>
                      )}
                      {v.photo_count > 0 && (
                        <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                          <Camera className="h-2.5 w-2.5" />{v.photo_count}
                        </span>
                      )}
                      {v.reading_count > 0 && (
                        <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                          <Beaker className="h-2.5 w-2.5" />{v.reading_count}
                        </span>
                      )}
                      <Badge variant={style.variant} className={`${style.className || ""} text-[10px] px-1.5`}>
                        {v.status === "in_progress" ? "Active" : v.status.charAt(0).toUpperCase() + v.status.slice(1)}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <VisitDetailOverlay
        visitId={selectedVisitId}
        open={!!selectedVisitId}
        onClose={() => setSelectedVisitId(null)}
      />
    </>
  );
}

function VisitDetailOverlay({ visitId, open, onClose }: { visitId: string | null; open: boolean; onClose: () => void }) {
  const [context, setContext] = useState<VisitContext | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !visitId) return;
    setLoading(true);
    setContext(null);
    api.get<VisitContext>(`/v1/visits/${visitId}/context`)
      .then((data) => setContext(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, visitId]);

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <OverlayContent className="max-w-lg">
        <OverlayHeader>
          <OverlayTitle>
            {context ? `Visit — ${new Date(context.visit.started_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : "Visit Detail"}
          </OverlayTitle>
        </OverlayHeader>
        <OverlayBody>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !context ? (
            <p className="text-sm text-muted-foreground text-center py-8">Visit not found</p>
          ) : (
            <div className="space-y-4">
              {/* Status + duration */}
              <div className="flex items-center gap-3">
                <Badge variant={STATUS_STYLES[context.visit.status]?.variant || "secondary"} className={STATUS_STYLES[context.visit.status]?.className}>
                  {context.visit.status === "in_progress" ? "Active" : context.visit.status.charAt(0).toUpperCase() + context.visit.status.slice(1)}
                </Badge>
                {context.elapsed_seconds > 0 && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {Math.round(context.elapsed_seconds / 60)}min
                  </span>
                )}
              </div>

              {/* Checklist */}
              {context.checklist.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Checklist</p>
                  <div className="space-y-0.5">
                    {context.checklist.map((item) => (
                      <div key={item.id} className="flex items-center gap-2 text-xs py-0.5">
                        {item.completed ? (
                          <Check className="h-3 w-3 text-green-600 shrink-0" />
                        ) : (
                          <X className="h-3 w-3 text-muted-foreground shrink-0" />
                        )}
                        <span className={item.completed ? "text-foreground" : "text-muted-foreground"}>
                          {item.name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Chemical readings */}
              {context.readings.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Chemical Readings</p>
                  {context.readings.map((r) => {
                    const wf = context.water_features.find((w) => w.id === r.water_feature_id);
                    const values = [
                      { label: "pH", value: r.ph },
                      { label: "FC", value: r.free_chlorine },
                      { label: "TC", value: r.total_chlorine },
                      { label: "Alk", value: r.alkalinity },
                      { label: "CH", value: r.calcium_hardness },
                      { label: "CYA", value: r.cya },
                      { label: "Salt", value: r.salt },
                      { label: "Temp", value: r.water_temp },
                    ].filter((v) => v.value != null);

                    return (
                      <div key={r.id} className="space-y-0.5">
                        {wf && <p className="text-[10px] text-muted-foreground">{wf.name || wf.water_type}</p>}
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
                          {values.map((v) => (
                            <span key={v.label}>
                              <span className="text-muted-foreground">{v.label}:</span>{" "}
                              <span className="font-medium">{v.value}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Photos */}
              {context.photos.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Photos ({context.photos.length})</p>
                  <div className="grid grid-cols-3 gap-1.5">
                    {context.photos.map((p) => (
                      <img
                        key={p.id}
                        src={`${process.env.NEXT_PUBLIC_API_URL || ""}${p.photo_url}`}
                        alt={p.caption || "Visit photo"}
                        className="rounded-md aspect-square object-cover w-full"
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Charges */}
              {context.charges.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Charges</p>
                  {context.charges.map((c) => (
                    <div key={c.id} className="flex items-center justify-between text-xs">
                      <span>{c.description}</span>
                      <span className="font-medium">${c.amount.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Notes */}
              {context.visit.notes && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Notes</p>
                  <p className="text-xs text-muted-foreground whitespace-pre-line">{context.visit.notes}</p>
                </div>
              )}

              {/* Empty state */}
              {context.checklist.length === 0 && context.readings.length === 0 && context.photos.length === 0 && context.charges.length === 0 && !context.visit.notes && (
                <p className="text-sm text-muted-foreground text-center py-4">No visit data recorded</p>
              )}
            </div>
          )}
        </OverlayBody>
      </OverlayContent>
    </Overlay>
  );
}
