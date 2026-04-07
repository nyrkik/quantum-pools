"use client";

import { Package, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CatalogPart } from "./catalog-types";

interface PartRowProps {
  part: CatalogPart;
  backendOrigin: string;
  onViewEquipment?: () => void;
}

export function PartRow({ part, backendOrigin, onViewEquipment }: PartRowProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors">
      <div className="flex-shrink-0 h-8 w-8 rounded bg-muted flex items-center justify-center overflow-hidden">
        {part.image_url ? (
          <img src={part.image_url.startsWith("/uploads") ? `${backendOrigin}${part.image_url}` : part.image_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <Package className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{part.name}</p>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="font-mono bg-muted px-1 rounded">{part.sku}</span>
          {part.brand && <span>{part.brand}</span>}
        </div>
      </div>
      {onViewEquipment && (
        <Button variant="ghost" size="sm" className="text-xs h-7 shrink-0" onClick={onViewEquipment}>
          View Equipment
        </Button>
      )}
      {part.product_url && (
        <a href={part.product_url} target="_blank" rel="noopener noreferrer" className="p-1.5 text-muted-foreground hover:text-primary shrink-0">
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      )}
    </div>
  );
}
