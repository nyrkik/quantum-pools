"use client";

import { Package, ChevronRight } from "lucide-react";
import type { EquipmentEntry } from "./catalog-types";

interface EquipmentRowProps {
  entry: EquipmentEntry;
  backendOrigin: string;
  onClick: () => void;
}

export function EquipmentRow({ entry, backendOrigin, onClick }: EquipmentRowProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors cursor-pointer" onClick={onClick}>
      <div className="flex-shrink-0 h-10 w-10 rounded bg-muted/50 flex items-center justify-center overflow-hidden">
        {entry.image_url ? (
          <img src={`${backendOrigin}${entry.image_url}`} alt="" className="h-full w-full object-contain" />
        ) : (
          <Package className="h-4 w-4 text-muted-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{entry.canonical_name}</p>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {entry.manufacturer && <span>{entry.manufacturer}</span>}
          {entry.model_number && entry.model_number !== "?" && <span className="font-mono bg-muted px-1 rounded">{entry.model_number}</span>}
          {entry.category && <span>· {entry.category}</span>}
        </div>
      </div>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
    </div>
  );
}
