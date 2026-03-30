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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { Loader2, Link2, Search, Check, X, AlertTriangle, MapPin } from "lucide-react";

interface PropertyEMDStatus {
  property_id: string;
  property_address: string;
  customer_name: string;
  customer_id: string;
  match_status: string;
  facility_id: string | null;
  facility_name: string | null;
  last_inspection_date: string | null;
  total_violations: number;
}

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

function MatchingRow({ prop, onRefresh }: { prop: PropertyEMDStatus; onRefresh: () => void }) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [rejectDialog, setRejectDialog] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  const loadSuggestions = useCallback(async () => {
    setLoadingSuggestions(true);
    try {
      const data = await api.get<Suggestion[]>(`/v1/inspections/suggest-matches/${prop.property_id}`);
      setSuggestions(data);
    } catch {
      setSuggestions([]);
    } finally {
      setLoadingSuggestions(false);
    }
  }, [prop.property_id]);

  const handleFindRecords = () => {
    setShowSuggestions(true);
    loadSuggestions();
  };

  const handleConfirm = async (facilityId: string) => {
    setConfirming(true);
    try {
      await api.post("/v1/inspections/confirm-match", {
        property_id: prop.property_id,
        facility_id: facilityId,
      });
      toast.success("Match confirmed — inspections unlocked");
      setShowSuggestions(false);
      onRefresh();
    } catch (e) {
      toast.error("Failed to confirm match");
    } finally {
      setConfirming(false);
    }
  };

  const handleReject = async () => {
    setRejecting(true);
    try {
      await api.post(`/v1/inspections/reject-match/${prop.property_id}`);
      toast.success("Match removed");
      setRejectDialog(false);
      onRefresh();
      // Auto-show suggestions after rejection
      setShowSuggestions(true);
      loadSuggestions();
    } catch {
      toast.error("Failed to remove match");
    } finally {
      setRejecting(false);
    }
  };

  const scoreLabel = (score: number) => {
    if (score >= 80) return { text: "High", color: "bg-green-600" };
    if (score >= 60) return { text: "Medium", color: "bg-amber-500" };
    return { text: "Low", color: "bg-slate-500" };
  };

  return (
    <>
      <TableRow>
        <TableCell>
          <div>
            <span className="text-sm font-medium">{prop.customer_name}</span>
            <p className="text-xs text-muted-foreground">{prop.property_address}</p>
          </div>
        </TableCell>
        <TableCell>
          {prop.match_status === "matched" ? (
            <Badge className="bg-green-600 text-white">Matched</Badge>
          ) : (
            <Badge variant="outline" className="border-amber-400 text-amber-600">Unmatched</Badge>
          )}
        </TableCell>
        <TableCell className="text-sm text-muted-foreground">
          {prop.facility_name || "—"}
        </TableCell>
        <TableCell className="text-sm text-right">{prop.total_violations || "—"}</TableCell>
        <TableCell>
          {prop.match_status === "matched" ? (
            <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground" onClick={() => setRejectDialog(true)}>
              Wrong match?
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleFindRecords}>
              <Search className="h-3 w-3 mr-1" />Find Records
            </Button>
          )}
        </TableCell>
      </TableRow>

      {/* Suggestions panel */}
      {showSuggestions && (
        <TableRow>
          <TableCell colSpan={5} className="bg-muted/30">
            <div className="py-2">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Suggested matches for {prop.property_address}
                </p>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowSuggestions(false)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
              {loadingSuggestions ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : suggestions.length === 0 ? (
                <p className="text-sm text-muted-foreground py-3">No matching inspection records found for this address</p>
              ) : (
                <div className="space-y-1.5">
                  {suggestions.map((s) => {
                    const sl = scoreLabel(s.score);
                    return (
                      <div key={s.facility_id} className="flex items-center justify-between px-3 py-2 rounded border bg-background">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{s.facility_name}</span>
                            <Badge className={`${sl.color} text-white text-[10px] px-1.5 py-0`}>{sl.text}</Badge>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                            <span><MapPin className="h-3 w-3 inline mr-0.5" />{s.street_address}, {s.city}</span>
                            <span>{s.total_inspections} inspections</span>
                            <span>{s.total_violations} violations</span>
                          </div>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs shrink-0 ml-3"
                          onClick={() => handleConfirm(s.facility_id)}
                          disabled={confirming}
                        >
                          {confirming ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Check className="h-3 w-3 mr-1" />Confirm</>}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}

      {/* Reject confirmation */}
      <AlertDialog open={rejectDialog} onOpenChange={setRejectDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Match</AlertDialogTitle>
            <AlertDialogDescription>
              This will unlink <strong>{prop.facility_name}</strong> from <strong>{prop.property_address}</strong>.
              You&apos;ll be able to search for the correct match afterward.
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
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (properties.length === 0) return null;

  const matched = properties.filter(p => p.match_status === "matched").length;
  const unmatched = properties.length - matched;

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">My Properties — Health Inspections</CardTitle>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="text-green-600 font-medium">{matched} matched</span>
            {unmatched > 0 && <span className="text-amber-600 font-medium">{unmatched} unmatched</span>}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-100 dark:bg-slate-800">
                <TableHead className="text-xs font-medium uppercase tracking-wide">Property</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Facility</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Violations</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide w-32"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {properties.map((p) => (
                <MatchingRow key={p.property_id} prop={p} onRefresh={load} />
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
