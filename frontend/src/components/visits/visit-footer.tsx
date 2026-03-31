"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Receipt, CheckCircle, Loader2, AlertTriangle } from "lucide-react";
import { AddChargeSheet } from "@/components/charges/add-charge-sheet";
import type { VisitContext } from "@/types/visit";

interface VisitFooterProps {
  context: VisitContext;
  notes: string;
  onChargesChanged: () => void;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} minute${m !== 1 ? "s" : ""}`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}

export function VisitFooter({ context, notes, onChargesChanged }: VisitFooterProps) {
  const router = useRouter();
  const [showConfirm, setShowConfirm] = useState(false);
  const [completing, setCompleting] = useState(false);

  const summary = useMemo(() => {
    const checklistTotal = context.checklist.length;
    const checklistDone = context.checklist.filter((i) => i.completed).length;
    const readingsCount = context.readings.length;
    const wfCount = context.water_features.length;
    const photoCount = context.photos.length;
    const chargeTotal = context.charges.reduce((s, c) => s + c.amount, 0);
    const elapsed = Math.floor((Date.now() - new Date(context.visit.started_at).getTime()) / 1000);

    return {
      checklistDone,
      checklistTotal,
      checklistComplete: checklistDone === checklistTotal,
      readingsCount,
      readingsMissing: readingsCount < wfCount,
      photoCount,
      chargeTotal,
      elapsed,
    };
  }, [context]);

  const handleComplete = async () => {
    setCompleting(true);
    try {
      await api.post(`/v1/visits/${context.visit.id}/finish`, {
        notes: notes || null,
      });
      toast.success("Visit completed");
      router.push("/routes");
    } catch {
      toast.error("Failed to complete visit");
    } finally {
      setCompleting(false);
    }
  };

  return (
    <>
      <div className="fixed bottom-0 left-0 right-0 z-40 border-t bg-background shadow-[0_-2px_10px_rgba(0,0,0,0.08)]">
        <div className="flex items-center justify-between flex-wrap gap-2 px-4 py-3 max-w-lg mx-auto">
          <AddChargeSheet
            propertyId={context.visit.property_id}
            customerId={context.visit.customer_id}
            visitId={context.visit.id}
            onChargeAdded={onChargesChanged}
            trigger={
              <Button variant="ghost" size="sm">
                <Receipt className="h-4 w-4 mr-1.5" />
                Add Charge
              </Button>
            }
          />
          <Button onClick={() => setShowConfirm(true)} size="sm">
            <CheckCircle className="h-4 w-4 mr-1.5" />
            Complete Visit
          </Button>
        </div>
      </div>

      <Dialog open={showConfirm} onOpenChange={setShowConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Complete Visit?</DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <SummaryRow
              label="Checklist"
              value={`${summary.checklistDone}/${summary.checklistTotal} completed`}
              warn={!summary.checklistComplete}
            />
            <SummaryRow
              label="Readings"
              value={summary.readingsCount > 0 ? `${summary.readingsCount} saved` : "No readings recorded"}
              warn={summary.readingsMissing}
            />
            <SummaryRow
              label="Photos"
              value={summary.photoCount > 0 ? `${summary.photoCount} photo${summary.photoCount !== 1 ? "s" : ""}` : "No photos"}
              warn={false}
            />
            <SummaryRow
              label="Charges"
              value={summary.chargeTotal > 0 ? `$${summary.chargeTotal.toFixed(2)}` : "No charges"}
              warn={false}
            />
            <SummaryRow
              label="Duration"
              value={formatDuration(summary.elapsed)}
              warn={false}
            />
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowConfirm(false)}>
              Cancel
            </Button>
            <Button onClick={handleComplete} disabled={completing}>
              {completing && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Complete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function SummaryRow({ label, value, warn }: { label: string; value: string; warn: boolean }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`flex items-center gap-1 ${warn ? "text-amber-600 font-medium" : ""}`}>
        {warn && <AlertTriangle className="h-3.5 w-3.5" />}
        {value}
      </span>
    </div>
  );
}
