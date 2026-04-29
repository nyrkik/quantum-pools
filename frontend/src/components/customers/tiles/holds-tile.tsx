"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Pause, Plus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Property } from "../customer-types";

interface Hold {
  id: string;
  property_id: string;
  start_date: string;
  end_date: string;
  reason: string | null;
  created_at: string;
  updated_at: string;
}

interface HoldsTileProps {
  properties: Property[];
  canEdit: boolean;
}

export function HoldsTile({ properties, canEdit }: HoldsTileProps) {
  const [holdsByProp, setHoldsByProp] = useState<Record<string, Hold[]>>({});
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [addForProp, setAddForProp] = useState<string | null>(null);
  const [addStart, setAddStart] = useState("");
  const [addEnd, setAddEnd] = useState("");
  const [addReason, setAddReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const all: Record<string, Hold[]> = {};
      await Promise.all(
        properties.map(async (p) => {
          try {
            const rows = await api.get<Hold[]>(`/v1/properties/${p.id}/holds`);
            all[p.id] = rows;
          } catch {
            all[p.id] = [];
          }
        }),
      );
      setHoldsByProp(all);
    } finally {
      setLoading(false);
    }
  }, [properties]);

  useEffect(() => {
    if (properties.length > 0) load();
    else setLoading(false);
  }, [properties, load]);

  const totalHolds = Object.values(holdsByProp).reduce((s, h) => s + h.length, 0);

  // Hide tile entirely when there are no holds AND user can't add — keeps
  // tech/readonly customer detail clean. Owners always see the tile so
  // they can add a hold.
  if (!loading && totalHolds === 0 && !canEdit) return null;

  function openAdd(propId: string) {
    setAddForProp(propId);
    setAddStart("");
    setAddEnd("");
    setAddReason("");
    setAddOpen(true);
  }

  async function fireAdd() {
    if (!addForProp || !addStart || !addEnd) {
      toast.error("Pick start and end dates");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/v1/properties/${addForProp}/holds`, {
        start_date: addStart,
        end_date: addEnd,
        reason: addReason || null,
      });
      toast.success("Hold added");
      setAddOpen(false);
      await load();
    } catch (err) {
      toast.error((err as Error).message || "Failed to add hold");
    } finally {
      setSaving(false);
    }
  }

  async function fireDelete() {
    if (!deleteId) return;
    try {
      await api.delete(`/v1/property-holds/${deleteId}`);
      toast.success("Hold removed");
      setDeleteId(null);
      await load();
    } catch (err) {
      toast.error((err as Error).message || "Failed to remove hold");
    }
  }

  return (
    <Card className="shadow-sm">
      <div className="bg-primary text-primary-foreground px-4 py-2.5 flex items-center gap-2 text-sm font-medium">
        <Pause className="h-3.5 w-3.5 opacity-70" />
        <span>Service Holds</span>
        {totalHolds > 0 && (
          <span className="opacity-70 ml-auto">{totalHolds}</span>
        )}
      </div>
      <CardContent className="py-3 space-y-3">
        {loading ? (
          <div className="flex items-center text-xs text-muted-foreground py-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" /> Loading holds…
          </div>
        ) : (
          properties.map((prop) => {
            const holds = holdsByProp[prop.id] || [];
            return (
              <div key={prop.id} className="space-y-2">
                {properties.length > 1 && (
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    {prop.address}
                  </div>
                )}
                {holds.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic">
                    No active or upcoming holds.
                  </div>
                ) : (
                  <ul className="space-y-1.5">
                    {holds.map((h) => (
                      <li
                        key={h.id}
                        className="flex items-center gap-2 text-sm bg-muted/50 rounded px-2.5 py-1.5"
                      >
                        <Badge
                          variant="outline"
                          className="border-amber-400 text-amber-700"
                        >
                          {fmtRange(h.start_date, h.end_date)}
                        </Badge>
                        <span className="flex-1 truncate text-muted-foreground text-xs">
                          {h.reason || "(no reason)"}
                        </span>
                        {canEdit && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => setDeleteId(h.id)}
                            aria-label="Remove hold"
                          >
                            <Trash2 className="h-3.5 w-3.5 text-destructive" />
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {canEdit && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs h-7"
                    onClick={() => openAdd(prop.id)}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add hold
                  </Button>
                )}
              </div>
            );
          })
        )}
      </CardContent>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add service hold</DialogTitle>
            <DialogDescription>
              Recurring billing skips this property while a hold covers the billing period start
              date. Visits scheduled inside the window are not auto-canceled — that&apos;s a manual call.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Start date</Label>
                <Input
                  type="date"
                  value={addStart}
                  onChange={(e) => setAddStart(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">End date</Label>
                <Input
                  type="date"
                  value={addEnd}
                  onChange={(e) => setAddEnd(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Reason (optional)</Label>
              <Textarea
                rows={2}
                value={addReason}
                onChange={(e) => setAddReason(e.target.value)}
                placeholder="e.g. Winterized, owner traveling, equipment swap"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAddOpen(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button onClick={fireAdd} disabled={saving} size="sm">
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              ) : null}
              Add hold
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this service hold?</AlertDialogTitle>
            <AlertDialogDescription>
              The property will resume normal recurring billing on its next billing date.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={fireDelete}>Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function fmtRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const sameYear = s.getUTCFullYear() === e.getUTCFullYear();
  const startStr = s.toLocaleDateString("en-US", opts);
  const endStr = e.toLocaleDateString(
    "en-US",
    sameYear ? opts : { ...opts, year: "numeric" },
  );
  const yearStr = sameYear ? `, ${s.getUTCFullYear()}` : "";
  return `${startStr} – ${endStr}${yearStr}`;
}
