"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, Copy, Dog, KeyRound, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import type { VisitCustomer, VisitProperty, VisitWaterFeature } from "@/types/visit";

interface VisitHeaderProps {
  customer: VisitCustomer;
  property: VisitProperty;
  waterFeatures: VisitWaterFeature[];
  startedAt: string;
  onBack: () => void;
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export function VisitHeader({ customer, property, waterFeatures, startedAt, onBack }: VisitHeaderProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = new Date(startedAt).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [startedAt]);

  const copyGateCode = () => {
    if (property.gate_code) {
      navigator.clipboard.writeText(property.gate_code);
      toast.success("Gate code copied");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="font-mono text-lg font-semibold tabular-nums">
          {formatElapsed(elapsed)}
        </div>
      </div>

      <div>
        <Link href={`/customers/${customer.id}`} className="text-base font-semibold hover:underline">
          {customer.name}
        </Link>
        {customer.company && (
          <span className="ml-1.5 text-sm text-muted-foreground">{customer.company}</span>
        )}
        <p className="text-sm text-muted-foreground">{property.address}{property.city ? `, ${property.city}` : ""}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {waterFeatures.map((wf) => (
          <Badge key={wf.id} variant="secondary" className="text-xs">
            {wf.name} {wf.pool_gallons ? `${(wf.pool_gallons / 1000).toFixed(0)}k gal` : ""}
          </Badge>
        ))}
      </div>

      {(property.gate_code || property.dog_on_property || property.access_instructions) && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {property.gate_code && (
            <button onClick={copyGateCode} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs font-medium hover:bg-muted/80">
              <KeyRound className="h-3 w-3" />
              {property.gate_code}
              <Copy className="h-2.5 w-2.5 text-muted-foreground" />
            </button>
          )}
          {property.dog_on_property && (
            <Badge variant="outline" className="border-amber-400 text-amber-600 text-xs">
              <Dog className="h-3 w-3 mr-1" />
              Dog
            </Badge>
          )}
          {property.access_instructions && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Info className="h-3 w-3" />
              {property.access_instructions}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
