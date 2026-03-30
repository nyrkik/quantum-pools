"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Clock,
  Loader2,
  ShoppingCart,
  Unlock,
  Lock,
  X,
} from "lucide-react";
import type { InspectionLookup, RedactedDetail } from "./inspection-types";
import { formatDate } from "./inspection-constants";

interface RecentLookupsProps {
  lookups: InspectionLookup[];
  onSelectFacility: (id: string) => void;
}

export function RecentLookups({ lookups, onSelectFacility }: RecentLookupsProps) {
  if (lookups.length === 0) return null;

  return (
    <div className="shrink-0">
      <div className="flex items-center gap-2 mb-1.5">
        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Recent Lookups</span>
        <div className="flex-1 border-t border-border ml-1" />
      </div>
      <div className="flex gap-2 flex-wrap">
        {lookups.map((l) => (
          <button
            key={l.id}
            className="flex items-center gap-2 px-2.5 py-1.5 bg-muted/50 rounded-md hover:bg-accent text-sm transition-colors"
            onClick={() => onSelectFacility(l.facility_id)}
          >
            <Unlock className="h-3 w-3 text-green-500" />
            <span className="font-medium truncate max-w-[180px]">{l.facility_name}</span>
            <span className="text-[10px] text-muted-foreground">{l.days_remaining}d left</span>
          </button>
        ))}
      </div>
    </div>
  );
}

interface LookupCartProps {
  cart: Set<string>;
  purchasing: boolean;
  onClear: () => void;
  onPurchase: () => void;
}

export function LookupCart({ cart, purchasing, onClear, onPurchase }: LookupCartProps) {
  if (cart.size === 0) return null;

  return (
    <div className="shrink-0">
      <Card className="shadow-sm border-primary/30 bg-primary/5">
        <CardContent className="p-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShoppingCart className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">{cart.size} {cart.size === 1 ? "facility" : "facilities"} in cart</span>
            <span className="text-sm text-muted-foreground">${(cart.size * 0.99).toFixed(2)}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onClear}>
              Clear
            </Button>
            <Button size="sm" className="h-7 text-xs" onClick={onPurchase} disabled={purchasing}>
              {purchasing ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              Unlock {cart.size} — ${(cart.size * 0.99).toFixed(2)}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface RedactedDetailPanelProps {
  detail: RedactedDetail;
  cart: Set<string>;
  detailLoading: boolean;
  onClose: () => void;
  onToggleCart: (id: string) => void;
}

export function RedactedDetailPanel({
  detail,
  cart,
  detailLoading,
  onClose,
  onToggleCart,
}: RedactedDetailPanelProps) {
  if (detailLoading) {
    return (
      <div className="lg:col-span-8 min-h-0 overflow-y-auto space-y-3">
        <Card className="shadow-sm">
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="lg:col-span-8 min-h-0 overflow-y-auto space-y-3">
      <Card className="shadow-sm">
        <CardContent className="p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{detail.name}</h2>
              <p className="text-sm text-muted-foreground mt-0.5">{detail.city || "Sacramento County"}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={onClose}
            >
              <X className="h-4 w-4 text-muted-foreground hover:text-destructive" />
            </Button>
          </div>

          <div className="grid grid-cols-3 gap-3 mt-4">
            <div className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Inspections</p>
              <p className="text-xl font-bold leading-tight mt-0.5">{detail.total_inspections}</p>
            </div>
            <div className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Violations</p>
              <p className={`text-xl font-bold leading-tight mt-0.5 ${detail.total_violations > 10 ? "text-red-600" : detail.total_violations > 0 ? "text-amber-600" : ""}`}>{detail.total_violations}</p>
            </div>
            <div className="bg-muted/50 rounded-md px-2.5 py-2 text-center">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Last Inspected</p>
              <p className="text-xl font-bold leading-tight mt-0.5">{formatDate(detail.last_inspection_date)}</p>
            </div>
          </div>

          {/* Blurred tease area */}
          <div className="mt-6 relative">
            <div className="blur-sm pointer-events-none select-none">
              <div className="space-y-2">
                <div className="h-4 w-3/4 bg-muted rounded" />
                <div className="h-4 w-1/2 bg-muted rounded" />
                <div className="h-4 w-2/3 bg-muted rounded" />
                <div className="h-12 w-full bg-muted rounded" />
                <div className="h-4 w-1/2 bg-muted rounded" />
              </div>
            </div>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="rounded-full bg-background p-3 shadow-sm border mb-3">
                <Lock className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium mb-1">Full details locked</p>
              <p className="text-xs text-muted-foreground mb-3 text-center max-w-xs">
                Unlock this facility to see address, permit holder, inspection timeline, equipment, and violations.
              </p>
              {cart.has(detail.id) ? (
                <Button variant="outline" size="sm" onClick={() => onToggleCart(detail.id)}>
                  <X className="h-3 w-3 mr-1" /> Remove from Cart
                </Button>
              ) : (
                <Button size="sm" onClick={() => onToggleCart(detail.id)}>
                  <ShoppingCart className="h-3.5 w-3.5 mr-1.5" />
                  Add to Cart — $0.99
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
