"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { toast } from "sonner";
import { Loader2, Link2, Check, X, MapPin, Info } from "lucide-react";
import type { PropertyEMDStatus } from "./inspection-types";

interface Suggestion {
  facility_id: string;
  facility_name: string;
  street_address: string | null;
  city: string | null;
  score: number;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
}

function MatchedRow({ prop, onRefresh }: { prop: PropertyEMDStatus; onRefresh: () => void }) {
  const [rejectDialog, setRejectDialog] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  const handleReject = async () => {
    setRejecting(true);
    try {
      await api.post(`/v1/inspections/reject-match/${prop.property_id}`);
      toast.success("Match removed");
      setRejectDialog(false);
      onRefresh();
    } catch {
      toast.error("Failed to remove match");
    } finally {
      setRejecting(false);
    }
  };

  return (
    <>
      <div className="flex items-center justify-between gap-3 px-3 py-2 border-b border-border/40">
        <div className="flex items-center gap-2 min-w-0">
          <Link2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
          <div className="min-w-0">
            <span className="text-sm font-medium">{prop.customer_name}</span>
            <span className="text-xs text-muted-foreground ml-2">{prop.property_address}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-muted-foreground">{prop.facility_name}</span>
          {prop.total_violations > 0 && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{prop.total_violations} viol</Badge>
          )}
          <Button variant="ghost" size="sm" className="h-6 text-[10px] text-muted-foreground" onClick={() => setRejectDialog(true)}>
            Wrong?
          </Button>
        </div>
      </div>

      <AlertDialog open={rejectDialog} onOpenChange={setRejectDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Match</AlertDialogTitle>
            <AlertDialogDescription>
              This will unlink <strong>{prop.facility_name}</strong> from <strong>{prop.property_address}</strong>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleReject} disabled={rejecting}>
              {rejecting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Remove Match"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function UnmatchedRow({ prop, onRefresh }: { prop: PropertyEMDStatus; onRefresh: () => void }) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<Suggestion[]>(`/v1/inspections/suggest-matches/${prop.property_id}`);
      setSuggestions(data);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, [prop.property_id]);

  const handleConfirm = async (facilityId: string) => {
    setConfirming(true);
    try {
      await api.post("/v1/inspections/confirm-match", {
        property_id: prop.property_id,
        facility_id: facilityId,
      });
      toast.success("Match confirmed");
      setShowSuggestions(false);
      onRefresh();
    } catch {
      toast.error("Failed to confirm match");
    } finally {
      setConfirming(false);
    }
  };

  const hasReason = !!prop.unmatched_reason;
  const isOutOfCounty = prop.unmatched_reason?.includes("not in Sacramento");

  return (
    <div className="border-b border-border/40">
      <div className="flex items-center justify-between gap-3 px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <Info className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <div className="min-w-0">
            <span className="text-sm font-medium">{prop.customer_name}</span>
            <span className="text-xs text-muted-foreground ml-2">{prop.property_address}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {hasReason && (
            <span className="text-[11px] text-muted-foreground">{prop.unmatched_reason}</span>
          )}
          {!isOutOfCounty && (
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-[10px]"
              onClick={() => { setShowSuggestions(!showSuggestions); if (!showSuggestions) loadSuggestions(); }}
            >
              Search
            </Button>
          )}
        </div>
      </div>

      {showSuggestions && (
        <div className="px-3 pb-2">
          {loading ? (
            <div className="flex items-center justify-center py-3">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : suggestions.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No matching facilities found</p>
          ) : (
            <div className="space-y-1">
              {suggestions.map((s) => (
                <div key={s.facility_id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded border bg-background text-sm">
                  <div className="min-w-0">
                    <span className="font-medium">{s.facility_name}</span>
                    <span className="text-xs text-muted-foreground ml-2">
                      <MapPin className="h-3 w-3 inline mr-0.5" />{s.street_address}
                    </span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-[10px] shrink-0"
                    onClick={() => handleConfirm(s.facility_id)}
                    disabled={confirming}
                  >
                    {confirming ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Check className="h-3 w-3 mr-0.5" />Match</>}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PropertyMatching() {
  const [properties, setProperties] = useState<PropertyEMDStatus[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.get<PropertyEMDStatus[]>("/v1/inspections/my-properties");
      setProperties(data);
    } catch {
      setProperties([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <Card className="shadow-sm">
        <CardContent className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (properties.length === 0) return null;

  const matched = properties.filter(p => p.match_status === "matched");
  const unmatched = properties.filter(p => p.match_status !== "matched");

  return (
    <div className="space-y-3">
      {/* Matched */}
      {matched.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-2 pt-3 px-3">
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm">Matched Properties</CardTitle>
              <Badge variant="default" className="text-[10px]">{matched.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {matched.map((p) => (
              <MatchedRow key={p.property_id} prop={p} onRefresh={load} />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Unmatched */}
      {unmatched.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-2 pt-3 px-3">
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm">Unmatched Properties</CardTitle>
              <Badge variant="outline" className="text-[10px] border-amber-400 text-amber-600">{unmatched.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {unmatched.map((p) => (
              <UnmatchedRow key={p.property_id} prop={p} onRefresh={load} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
