"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import { Loader2, Package, ExternalLink } from "lucide-react";
import type { EquipmentEntry } from "./catalog-types";

interface EquipmentDetailOverlayProps {
  equipmentId: string | null;
  open: boolean;
  onClose: () => void;
  backendOrigin: string;
}

export function EquipmentDetailOverlay({ equipmentId, open, onClose, backendOrigin }: EquipmentDetailOverlayProps) {
  const [data, setData] = useState<EquipmentEntry | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !equipmentId) return;
    setLoading(true);
    setData(null);
    api.get<EquipmentEntry>(`/v1/equipment-catalog/${equipmentId}`)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, equipmentId]);

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <OverlayContent className="max-w-md">
        <OverlayHeader>
          <OverlayTitle>{data?.canonical_name || "Equipment"}</OverlayTitle>
        </OverlayHeader>
        <OverlayBody className="space-y-4">
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : !data ? (
            <p className="text-sm text-muted-foreground text-center py-8">Not found</p>
          ) : (
            <>
              {data.image_url && (
                <div className="flex justify-center">
                  <img src={`${backendOrigin}${data.image_url}`} alt={data.canonical_name} className="h-32 w-32 object-contain rounded-md bg-muted/30" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                {[
                  { label: "Manufacturer", value: data.manufacturer },
                  { label: "Model #", value: data.model_number !== "?" ? data.model_number : null },
                  { label: "Category", value: data.category },
                  ...(data.specs ? Object.entries(data.specs).map(([k, v]) => ({ label: k.toUpperCase(), value: String(v) })) : []),
                ].filter(d => d.value).map(d => (
                  <div key={d.label} className="contents">
                    <span className="text-muted-foreground text-xs">{d.label}</span>
                    <span className="font-medium text-xs">{d.value}</span>
                  </div>
                ))}
              </div>

              {data.parts && data.parts.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Compatible Parts ({data.parts.length})</p>
                  <div className="space-y-1.5">
                    {data.parts.map(p => (
                      <div key={p.id} className="flex items-start justify-between text-xs border rounded-md p-2 bg-muted/30">
                        <div className="min-w-0">
                          <p className="font-medium truncate">{p.name}</p>
                          <div className="flex items-center gap-2 text-muted-foreground mt-0.5">
                            {p.brand && <span>{p.brand}</span>}
                            {p.sku && <span>SKU: {p.sku}</span>}
                          </div>
                          {p.category && <Badge variant="secondary" className="text-[9px] px-1 mt-1">{p.category}</Badge>}
                        </div>
                        {p.product_url && (
                          <a href={p.product_url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-primary shrink-0 ml-2">
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(!data.parts || data.parts.length === 0) && (
                <p className="text-xs text-muted-foreground italic text-center">No parts linked yet</p>
              )}
            </>
          )}
        </OverlayBody>
      </OverlayContent>
    </Overlay>
  );
}
