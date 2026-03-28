"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { MapPin, Copy, Check, DogIcon, Lock, Calendar } from "lucide-react";
import type { Property } from "../customer-types";

interface PropertyTileProps {
  properties: Property[];
  preferredDay: string | null;
}

export function PropertyTile({ properties, preferredDay }: PropertyTileProps) {
  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <MapPin className="h-4 w-4 text-muted-foreground" />
          Property
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {properties.map((prop) => (
          <PropertyCard key={prop.id} property={prop} preferredDay={preferredDay} />
        ))}
        {properties.length === 0 && (
          <p className="text-sm text-muted-foreground">No properties</p>
        )}
      </CardContent>
    </Card>
  );
}

function PropertyCard({ property, preferredDay }: { property: Property; preferredDay: string | null }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!property.gate_code) return;
    navigator.clipboard.writeText(property.gate_code);
    setCopied(true);
    toast.success("Copied");
    setTimeout(() => setCopied(false), 2000);
  };

  const days = property.service_day_pattern || preferredDay;

  return (
    <div className="space-y-2">
      {/* Address */}
      <p className="text-sm font-medium">
        {property.name || property.address.split(",")[0]}
      </p>
      {property.name && (
        <p className="text-xs text-muted-foreground">{property.address}, {property.city}</p>
      )}

      {/* Gate code — large, copyable */}
      {property.gate_code && (
        <button
          onClick={handleCopy}
          className="flex items-center gap-2 bg-muted/50 rounded-md px-3 py-2 hover:bg-muted transition-colors w-full"
        >
          <span className="text-[10px] text-muted-foreground uppercase tracking-wide">Gate</span>
          <span className="text-lg font-bold tracking-wider">{property.gate_code}</span>
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-600 ml-auto" />
          ) : (
            <Copy className="h-3.5 w-3.5 text-muted-foreground ml-auto" />
          )}
        </button>
      )}

      {/* Badges row */}
      <div className="flex flex-wrap items-center gap-1.5">
        {property.dog_on_property && (
          <Badge variant="outline" className="border-amber-400 text-amber-600 gap-1 text-[10px]">
            <DogIcon className="h-3 w-3" />
            Dog
          </Badge>
        )}
        {property.is_locked_to_day && (
          <Badge variant="outline" className="gap-1 text-[10px]">
            <Lock className="h-3 w-3" />
            Locked
          </Badge>
        )}
        {days && (
          <Badge variant="secondary" className="gap-1 text-[10px]">
            <Calendar className="h-3 w-3" />
            {days}
          </Badge>
        )}
      </div>

      {/* Access notes */}
      {property.access_instructions && (
        <p className="text-xs text-muted-foreground">{property.access_instructions}</p>
      )}
    </div>
  );
}
