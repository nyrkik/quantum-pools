"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Copy, Check, DogIcon, MapPin } from "lucide-react";
import type { Property } from "../customer-types";

interface SiteAccessSectionProps {
  properties: Property[];
}

export function SiteAccessSection({ properties }: SiteAccessSectionProps) {
  if (properties.length === 0) {
    return <p className="text-sm text-muted-foreground py-4 text-center">No properties</p>;
  }

  return (
    <div className="space-y-3">
      {properties.map((prop) => (
        <PropertyAccessCard key={prop.id} property={prop} showLabel={properties.length > 1} />
      ))}
    </div>
  );
}

function PropertyAccessCard({ property, showLabel }: { property: Property; showLabel: boolean }) {
  const [copied, setCopied] = useState(false);

  const handleCopyGate = () => {
    if (!property.gate_code) return;
    navigator.clipboard.writeText(property.gate_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="border rounded-lg p-3 space-y-2">
      {showLabel && (
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
          {property.name || property.address.split(",")[0]}
        </div>
      )}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Gate code — large, tappable */}
        {property.gate_code ? (
          <button
            onClick={handleCopyGate}
            className="flex items-center gap-2 bg-muted/50 rounded-lg px-4 py-2 hover:bg-muted transition-colors"
            title="Tap to copy"
          >
            <span className="text-xs text-muted-foreground uppercase tracking-wide">Gate</span>
            <span className="text-lg font-bold tracking-wider">{property.gate_code}</span>
            {copied ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>
        ) : (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="text-xs uppercase tracking-wide">Gate</span>
            <span>None</span>
          </div>
        )}

        {/* Dog warning */}
        {property.dog_on_property && (
          <Badge variant="outline" className="border-amber-400 text-amber-600 gap-1">
            <DogIcon className="h-3.5 w-3.5" />
            Dog on Property
          </Badge>
        )}
      </div>

      {/* Access instructions */}
      {property.access_instructions && (
        <div className="text-sm">
          <span className="text-muted-foreground">Access: </span>
          {property.access_instructions}
        </div>
      )}
    </div>
  );
}
