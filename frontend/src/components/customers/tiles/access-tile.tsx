"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { KeyRound, Copy, PawPrint, Calendar, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import type { Property } from "../customer-types";

interface AccessCode {
  id: string;
  label: string;
  code: string;
  notes: string | null;
}

interface AccessTileProps {
  properties: Property[];
  preferredDay: string | null;
}

export function AccessTile({ properties, preferredDay }: AccessTileProps) {
  const [codesByProp, setCodesByProp] = useState<Record<string, AccessCode[]>>({});

  useEffect(() => {
    for (const prop of properties) {
      api.get<AccessCode[]>(`/v1/properties/${prop.id}/access-codes`)
        .then((codes) => setCodesByProp((prev) => ({ ...prev, [prop.id]: codes })))
        .catch(() => {});
    }
  }, [properties]);

  const hasAnyCodes = properties.some((p) => (codesByProp[p.id] || []).length > 0 || p.gate_code);
  const hasAnyAlerts = properties.some((p) => p.dog_on_property || p.access_instructions);
  const hasDays = properties.some((p) => p.service_day_pattern || preferredDay);

  if (!hasAnyCodes && !hasAnyAlerts && !hasDays) return null;

  return (
    <Card className="shadow-sm bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800">
      <CardContent className="py-3">
        {properties.map((prop) => (
          <PropertyAccessCard
            key={prop.id}
            property={prop}
            codes={codesByProp[prop.id] || []}
            preferredDay={preferredDay}
            showLabel={properties.length > 1}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function PropertyAccessCard({ property, codes, preferredDay, showLabel }: {
  property: Property;
  codes: AccessCode[];
  preferredDay: string | null;
  showLabel: boolean;
}) {
  const days = property.service_day_pattern || preferredDay;
  const hasCodes = codes.length > 0 || !!property.gate_code;
  const hasAlerts = property.dog_on_property || !!property.access_instructions;

  if (!hasCodes && !hasAlerts && !days) return null;

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    toast.success("Copied");
  };

  return (
    <div className="space-y-2">
      {showLabel && property.name && (
        <p className="text-[10px] font-medium text-amber-700 dark:text-amber-400 uppercase tracking-wide">{property.name}</p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
        {/* Left column: Codes */}
        {hasCodes && (
          <div className="space-y-1">
            <p className="text-[10px] text-amber-700/70 dark:text-amber-400/70 uppercase tracking-wide font-medium flex items-center gap-1">
              <KeyRound className="h-2.5 w-2.5" /> Access Codes
            </p>
            {codes.length > 0 ? (
              codes.map((c) => (
                <div key={c.id} className="flex items-center gap-2">
                  <span className="text-[11px] text-amber-700 dark:text-amber-400 w-16 shrink-0">{c.label}</span>
                  <button
                    onClick={() => copyCode(c.code)}
                    className="flex items-center gap-1 hover:text-primary transition-colors"
                  >
                    <span className="font-bold text-sm">{c.code}</span>
                    <Copy className="h-2.5 w-2.5 text-muted-foreground" />
                  </button>
                  {c.notes && <span className="text-[10px] text-amber-600/70">({c.notes})</span>}
                </div>
              ))
            ) : property.gate_code ? (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-amber-700 dark:text-amber-400 w-16 shrink-0">Gate</span>
                <button
                  onClick={() => copyCode(property.gate_code!)}
                  className="flex items-center gap-1 hover:text-primary transition-colors"
                >
                  <span className="font-bold text-sm">{property.gate_code}</span>
                  <Copy className="h-2.5 w-2.5 text-muted-foreground" />
                </button>
              </div>
            ) : null}
          </div>
        )}

        {/* Right column: Schedule + Alerts */}
        <div className="space-y-1.5">
          {days && (
            <div className="space-y-0.5">
              <p className="text-[10px] text-amber-700/70 dark:text-amber-400/70 uppercase tracking-wide font-medium flex items-center gap-1">
                <Calendar className="h-2.5 w-2.5" /> Service Days
              </p>
              <div className="flex gap-1">
                {days.split(",").map((d) => (
                  <Badge key={d.trim()} variant="secondary" className="text-[10px] px-1.5">{d.trim()}</Badge>
                ))}
              </div>
            </div>
          )}

          {hasAlerts && (
            <div className="space-y-0.5">
              <p className="text-[10px] text-amber-700/70 dark:text-amber-400/70 uppercase tracking-wide font-medium flex items-center gap-1">
                <AlertTriangle className="h-2.5 w-2.5" /> Alerts
              </p>
              {property.dog_on_property && (
                <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400 text-xs font-medium">
                  <PawPrint className="h-3 w-3" /> Dog on property
                </span>
              )}
              {property.access_instructions && codes.length === 0 && (
                <p className="text-xs text-amber-800 dark:text-amber-300">{property.access_instructions}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
