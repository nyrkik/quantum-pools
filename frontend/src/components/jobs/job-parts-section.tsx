"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Plus, Trash2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { LogPurchaseForm } from "@/components/parts/log-purchase-form";
import { PartsSearchDialog } from "@/components/parts/parts-search-dialog";

interface PartPurchase {
  id: string;
  description: string;
  sku: string | null;
  vendor_name: string;
  unit_cost: number;
  quantity: number;
  total_cost: number;
  customer_price: number | null;
  purchased_at: string;
  notes: string | null;
}

interface JobPartsSectionProps {
  jobId: string;
  propertyId?: string | null;
}

export function JobPartsSection({ jobId, propertyId }: JobPartsSectionProps) {
  const [parts, setParts] = useState<PartPurchase[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<PartPurchase[]>(`/v1/part-purchases/job/${jobId}`);
      setParts(data);
    } catch {
      // Silently fail for jobs with no parts
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/v1/part-purchases/${id}`);
      toast.success("Purchase removed");
      load();
    } catch {
      toast.error("Failed to remove");
    }
  };

  const runningTotal = parts.reduce((sum, p) => sum + p.total_cost, 0);
  const customerTotal = parts.reduce((sum, p) => sum + (p.customer_price || p.total_cost), 0);

  if (loading) {
    return <div className="flex justify-center py-3"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-2">
      {/* Parts list */}
      {parts.length > 0 && (
        <div className="space-y-1.5">
          {parts.map((p) => (
            <div key={p.id} className="flex items-start justify-between bg-background rounded-md p-2.5 border text-sm">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium truncate">{p.description}</span>
                  {p.sku && <span className="text-[10px] text-muted-foreground bg-muted px-1 rounded">{p.sku}</span>}
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                  <span>{p.vendor_name}</span>
                  <span>{p.quantity} x ${p.unit_cost.toFixed(2)}</span>
                  <span className="font-medium text-foreground">${p.total_cost.toFixed(2)}</span>
                  <span>{p.purchased_at}</span>
                </div>
                {p.notes && <p className="text-[10px] text-muted-foreground mt-0.5">{p.notes}</p>}
              </div>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-6 w-6 flex-shrink-0">
                    <Trash2 className="h-3 w-3 text-destructive" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Remove this purchase?</AlertDialogTitle>
                    <AlertDialogDescription>{p.description} - ${p.total_cost.toFixed(2)}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => handleDelete(p.id)}>Remove</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          ))}

          {/* Running totals */}
          <div className="flex items-center justify-end gap-4 text-xs py-1 px-2">
            <span className="text-muted-foreground">Cost: <span className="font-medium text-foreground">${runningTotal.toFixed(2)}</span></span>
            <span className="text-muted-foreground">Customer: <span className="font-medium text-green-600">${customerTotal.toFixed(2)}</span></span>
          </div>
        </div>
      )}

      {parts.length === 0 && !showAdd && (
        <p className="text-xs text-muted-foreground text-center py-2">No parts purchased yet</p>
      )}

      {/* Add purchase form */}
      {showAdd ? (
        <LogPurchaseForm
          jobId={jobId}
          propertyId={propertyId || undefined}
          onPurchaseLogged={() => { setShowAdd(false); load(); }}
          onCancel={() => setShowAdd(false)}
        />
      ) : (
        <div className="flex gap-1.5">
          <Button variant="outline" size="sm" className="flex-1 h-7 text-xs" onClick={() => setShowAdd(true)}>
            <Plus className="h-3 w-3 mr-1" /> Add Part
          </Button>
          <Button variant="outline" size="sm" className="flex-1 h-7 text-xs" onClick={() => setCatalogOpen(true)}>
            <Search className="h-3 w-3 mr-1" /> Search Catalog
          </Button>
        </div>
      )}

      <PartsSearchDialog
        open={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        jobId={jobId}
        propertyId={propertyId || undefined}
        onLogPurchase={() => {
          setCatalogOpen(false);
          setShowAdd(true);
        }}
      />
    </div>
  );
}
