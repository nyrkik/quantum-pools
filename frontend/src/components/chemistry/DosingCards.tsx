"use client";

/**
 * Phase 3d.2 — DosingCards.
 *
 * Renders the dosing engine's output verbatim — one card per parameter
 * recommendation. The engine output is the source of truth (deterministic
 * pure function); this component is a presentational shell.
 *
 * Engine record shape (from app/src/services/dosing_engine.py):
 *   {
 *     parameter: "pH" | "Free Chlorine" | "Alkalinity" | ...,
 *     current: number,
 *     target: string,
 *     status: "low" | "high" | "ok",
 *     chemical: string | null,
 *     amount: string | null,
 *     amount_value?: number,
 *     unit?: string,
 *     notes?: string,
 *   }
 *
 * Cards stack vertically — mobile-first. Status drives the left border
 * color: ok → green, low → amber, high → red.
 */

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, AlertTriangle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DosingRecord {
  parameter: string;
  current: number | null;
  target: string;
  status: "low" | "high" | "ok";
  chemical: string | null;
  amount: string | null;
  amount_value?: number;
  unit?: string;
  notes?: string;
}

export interface DosingCardsProps {
  /** The dosing engine's `dosing` array. Empty/null is allowed —
   *  component renders nothing. */
  recommendations: DosingRecord[] | null | undefined;
  className?: string;
}


function statusStyles(status: string): {
  border: string;
  badgeVariant: "default" | "secondary" | "destructive" | "outline";
  icon: typeof CheckCircle2;
  iconColor: string;
} {
  if (status === "ok") {
    return {
      border: "border-l-green-500",
      badgeVariant: "secondary",
      icon: CheckCircle2,
      iconColor: "text-green-600",
    };
  }
  if (status === "low") {
    return {
      border: "border-l-amber-500",
      badgeVariant: "outline",
      icon: AlertTriangle,
      iconColor: "text-amber-600",
    };
  }
  // high
  return {
    border: "border-l-red-500",
    badgeVariant: "destructive",
    icon: AlertCircle,
    iconColor: "text-red-600",
  };
}


export function DosingCards({ recommendations, className }: DosingCardsProps) {
  if (!recommendations || recommendations.length === 0) {
    return null;
  }
  return (
    <div className={cn("space-y-2", className)}>
      {recommendations.map((rec, idx) => {
        const styles = statusStyles(rec.status);
        const Icon = styles.icon;
        const isOk = rec.status === "ok";
        return (
          <Card
            key={`${rec.parameter}-${idx}`}
            className={cn("shadow-sm border-l-4", styles.border)}
          >
            <CardContent className="p-3 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Icon className={cn("h-4 w-4 shrink-0", styles.iconColor)} />
                  <span className="font-medium text-sm truncate">
                    {rec.parameter}
                  </span>
                </div>
                <Badge variant={styles.badgeVariant} className="capitalize">
                  {rec.status === "ok" ? "OK" : rec.status}
                </Badge>
              </div>

              <div className="text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-0.5">
                {rec.current !== null && rec.current !== undefined ? (
                  <span>
                    <span className="text-muted-foreground/70">Current:</span>{" "}
                    {rec.current}
                  </span>
                ) : null}
                <span>
                  <span className="text-muted-foreground/70">Target:</span>{" "}
                  {rec.target}
                </span>
              </div>

              {!isOk && rec.chemical ? (
                <div className="text-sm pt-1">
                  <span className="font-medium">{rec.chemical}</span>
                  {rec.amount ? (
                    <span className="text-muted-foreground"> · {rec.amount}</span>
                  ) : null}
                </div>
              ) : null}

              {!isOk && rec.notes ? (
                <div className="text-xs text-muted-foreground italic">
                  {rec.notes}
                </div>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
