"use client";

import { useState, useEffect, useCallback } from "react";
import { api, getBackendOrigin } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Check, X, Loader2, Clock, ImageIcon } from "lucide-react";

interface Charge {
  id: string;
  description: string;
  amount: number;
  category: string;
  status: string;
  photo_url: string | null;
  notes: string | null;
  customer_name: string | null;
  property_address: string | null;
  creator_name: string | null;
  created_at: string | null;
}

interface PendingChargesProps {
  onCountChange?: (count: number) => void;
  refreshKey?: number;
}

export function PendingCharges({ onCountChange, refreshKey }: PendingChargesProps) {
  const [charges, setCharges] = useState<Charge[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.get<Charge[]>("/v1/visit-charges?status=pending");
      setCharges(data);
      onCountChange?.(data.length);
    } catch {
      /* ignore — may not have permission */
    } finally {
      setLoading(false);
    }
  }, [onCountChange]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const handleApprove = async (chargeId: string) => {
    setActionId(chargeId);
    try {
      await api.post(`/v1/visit-charges/${chargeId}/approve`);
      toast.success("Charge approved");
      load();
    } catch {
      toast.error("Failed to approve charge");
    } finally {
      setActionId(null);
    }
  };

  const handleReject = async () => {
    if (!rejectId || !rejectReason.trim()) return;
    setActionId(rejectId);
    try {
      await api.post(`/v1/visit-charges/${rejectId}/reject`, {
        reason: rejectReason.trim(),
      });
      toast.success("Charge rejected");
      setRejectId(null);
      setRejectReason("");
      load();
    } catch {
      toast.error("Failed to reject charge");
    } finally {
      setActionId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (charges.length === 0) return null;

  return (
    <>
      <Card className="shadow-sm border-l-4 border-amber-400">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-500" />
            Pending Approval
            <Badge variant="outline" className="border-amber-400 text-amber-600 ml-auto">
              {charges.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {charges.map((charge) => (
            <div
              key={charge.id}
              className="flex items-start gap-3 rounded-lg border p-3 bg-muted/30"
            >
              {/* Photo thumbnail */}
              {charge.photo_url ? (
                <img
                  src={`${getBackendOrigin()}${charge.photo_url}`}
                  alt=""
                  className="h-12 w-12 rounded object-cover flex-shrink-0"
                />
              ) : (
                <div className="h-12 w-12 rounded bg-muted flex items-center justify-center flex-shrink-0">
                  <ImageIcon className="h-4 w-4 text-muted-foreground" />
                </div>
              )}

              {/* Details */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{charge.description}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {charge.customer_name}
                  {charge.property_address && ` · ${charge.property_address}`}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm font-semibold">
                    ${charge.amount.toFixed(2)}
                  </span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {charge.category}
                  </Badge>
                  {charge.creator_name && (
                    <span className="text-[10px] text-muted-foreground">
                      by {charge.creator_name}
                    </span>
                  )}
                </div>
                {charge.notes && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                    {charge.notes}
                  </p>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 flex-shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleApprove(charge.id)}
                  disabled={actionId === charge.id}
                  className="text-muted-foreground hover:text-green-600"
                >
                  {actionId === charge.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setRejectId(charge.id)}
                  disabled={actionId === charge.id}
                  className="text-muted-foreground hover:text-destructive"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Reject dialog */}
      <AlertDialog
        open={!!rejectId}
        onOpenChange={(v) => {
          if (!v) {
            setRejectId(null);
            setRejectReason("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reject Charge</AlertDialogTitle>
            <AlertDialogDescription>
              Provide a reason for rejecting this charge. The tech will be notified.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Reason for rejection..."
            autoFocus
          />
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleReject}
              disabled={!rejectReason.trim()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Reject
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
