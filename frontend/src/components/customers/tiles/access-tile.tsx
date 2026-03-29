"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { KeyRound, Copy, PawPrint } from "lucide-react";
import type { Property } from "../customer-types";

interface AccessTileProps {
  properties: Property[];
  preferredDay: string | null;
}

export function AccessTile({ properties, preferredDay }: AccessTileProps) {
  const hasAccess = properties.some((p) => p.gate_code || p.dog_on_property || p.access_instructions);
  const hasDays = properties.some((p) => p.service_day_pattern || preferredDay);

  if (!hasAccess && !hasDays) return null;

  return (
    <Card className="shadow-sm bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800">
      <CardContent className="py-3 space-y-2">
        {properties.map((prop) => {
          const days = prop.service_day_pattern || preferredDay;
          const hasInfo = prop.gate_code || prop.dog_on_property || prop.access_instructions || days;
          if (!hasInfo) return null;

          return (
            <PropertyAccessRow
              key={prop.id}
              property={prop}
              days={days}
              showLabel={properties.length > 1}
            />
          );
        })}
      </CardContent>
    </Card>
  );
}

function PropertyAccessRow({ property, days, showLabel }: { property: Property; days: string | null; showLabel: boolean }) {
  const copyGate = () => {
    if (!property.gate_code) return;
    navigator.clipboard.writeText(property.gate_code);
    toast.success("Gate code copied");
  };

  // Don't show access_instructions if it's just restating the gate code
  const accessNote = property.access_instructions && property.gate_code
    ? (property.access_instructions.includes(property.gate_code) ? null : property.access_instructions)
    : property.access_instructions;

  return (
    <div className="space-y-1">
      {showLabel && property.name && (
        <p className="text-[10px] font-medium text-amber-700 dark:text-amber-400 uppercase tracking-wide">{property.name}</p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        {property.gate_code && (
          <button onClick={copyGate} className="flex items-center gap-1.5 hover:text-primary transition-colors" title="Copy gate code">
            <KeyRound className="h-3.5 w-3.5 text-amber-600" />
            <span className="font-bold">{property.gate_code}</span>
            <Copy className="h-3 w-3 text-muted-foreground" />
          </button>
        )}
        {property.dog_on_property && (
          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400 text-xs font-medium">
            <PawPrint className="h-3.5 w-3.5" /> Dog on property
          </span>
        )}
        {days && (
          <div className="flex gap-1">
            {days.split(",").map((d) => (
              <Badge key={d.trim()} variant="secondary" className="text-[10px] px-1.5">{d.trim()}</Badge>
            ))}
          </div>
        )}
      </div>
      {accessNote && (
        <p className="text-xs text-amber-800 dark:text-amber-300">{accessNote}</p>
      )}
    </div>
  );
}
