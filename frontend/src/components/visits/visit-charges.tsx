"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ChevronUp } from "lucide-react";
import { AddChargeSheet } from "@/components/charges/add-charge-sheet";
import type { VisitCharge } from "@/types/visit";

interface VisitChargesProps {
  visitId: string;
  propertyId: string;
  customerId: string;
  charges: VisitCharge[];
  onUpdate: () => void;
}

export function VisitCharges({ visitId, propertyId, customerId, charges, onUpdate }: VisitChargesProps) {
  const [open, setOpen] = useState(true);
  const total = charges.reduce((sum, c) => sum + c.amount, 0);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center justify-between rounded-lg bg-muted/60 px-4 py-3 text-left">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Charges</span>
            {charges.length > 0 && (
              <span className="text-xs text-muted-foreground">
                ${total.toFixed(2)}
              </span>
            )}
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="space-y-2 pt-3">
          {charges.length > 0 ? (
            <div className="space-y-1.5">
              {charges.map((charge) => (
                <div key={charge.id} className="flex items-center justify-between rounded-md bg-muted/30 px-3 py-2">
                  <span className="text-sm">{charge.description}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">${charge.amount.toFixed(2)}</span>
                    <Badge
                      variant={charge.status === "approved" ? "default" : "outline"}
                      className={`text-[10px] ${charge.status === "pending" ? "border-amber-400 text-amber-600" : ""}`}
                    >
                      {charge.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground px-1">No charges added</p>
          )}

          <AddChargeSheet
            propertyId={propertyId}
            customerId={customerId}
            visitId={visitId}
            onChargeAdded={onUpdate}
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
