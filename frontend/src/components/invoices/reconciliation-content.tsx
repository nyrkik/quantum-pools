"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Loader2, Check, X as XIcon, ArrowRight, Mail } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { PageTabs } from "@/components/layout/page-layout";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type TabKey = "pending" | "needs_review" | "unmatched";

interface PendingCheck {
  id: string;
  amount: number;
  payment_method: string;
  payment_date: string | null;
  status: string;
  reference_number: string | null;
  notes: string | null;
  source_message_id: string | null;
  customer_name: string | null;
  invoice_id: string | null;
}

interface ParsedRow {
  id: string;
  processor: string;
  amount: number | null;
  payer_name: string | null;
  property_hint: string | null;
  invoice_hint: string | null;
  payment_method: string | null;
  payment_date: string | null;
  reference_number: string | null;
  agent_message_id: string;
  thread_id: string | null;
  match_status: string;
  match_confidence: number | null;
  match_reasoning: string | null;
  candidate_invoice_id: string | null;
  candidate_invoice_number: string | null;
  candidate_invoice_total: number | null;
}

function formatCurrency(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return amount.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ReconciliationContent() {
  const [tab, setTab] = useState<TabKey>("pending");
  const [pending, setPending] = useState<PendingCheck[] | null>(null);
  const [needsReview, setNeedsReview] = useState<ParsedRow[] | null>(null);
  const [unmatched, setUnmatched] = useState<ParsedRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [p, n, u] = await Promise.all([
        api.get<{ items: PendingCheck[] }>("/v1/reconciliation/pending-checks"),
        api.get<{ items: ParsedRow[] }>("/v1/reconciliation/needs-review"),
        api.get<{ items: ParsedRow[] }>("/v1/reconciliation/unmatched"),
      ]);
      setPending(p.items);
      setNeedsReview(n.items);
      setUnmatched(u.items);
    } catch (err) {
      toast.error((err as Error).message || "Failed to load reconciliation queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function markReceived(paymentId: string) {
    setBusyId(paymentId);
    try {
      await api.post(`/v1/reconciliation/payments/${paymentId}/mark-received`, {});
      toast.success("Payment marked received");
      await loadAll();
    } catch (err) {
      toast.error((err as Error).message || "Mark received failed");
    } finally {
      setBusyId(null);
    }
  }

  async function acceptProposed(parsedId: string, invoiceId: string) {
    setBusyId(parsedId);
    try {
      await api.post(`/v1/reconciliation/parsed/${parsedId}/match`, { invoice_id: invoiceId });
      toast.success("Payment matched");
      await loadAll();
    } catch (err) {
      toast.error((err as Error).message || "Match failed");
    } finally {
      setBusyId(null);
    }
  }

  async function dismiss(parsedId: string) {
    setBusyId(parsedId);
    try {
      await api.post(`/v1/reconciliation/parsed/${parsedId}/dismiss`, {});
      toast.success("Dismissed");
      await loadAll();
    } catch (err) {
      toast.error((err as Error).message || "Dismiss failed");
    } finally {
      setBusyId(null);
    }
  }

  async function manualMatch(parsedId: string, invoiceId: string) {
    if (!invoiceId || invoiceId.length !== 36) {
      toast.error("Enter a valid invoice id");
      return;
    }
    setBusyId(parsedId);
    try {
      await api.post(`/v1/reconciliation/parsed/${parsedId}/match`, { invoice_id: invoiceId });
      toast.success("Payment matched");
      await loadAll();
    } catch (err) {
      toast.error((err as Error).message || "Match failed");
    } finally {
      setBusyId(null);
    }
  }

  const tabs = [
    { key: "pending", label: `Pending checks${pending ? ` (${pending.length})` : ""}` },
    { key: "needs_review", label: `Needs review${needsReview ? ` (${needsReview.length})` : ""}` },
    { key: "unmatched", label: `Unmatched${unmatched ? ` (${unmatched.length})` : ""}` },
  ];

  return (
    <div className="space-y-3">
      <PageTabs
        tabs={tabs}
        activeTab={tab}
        onTabChange={(k) => setTab(k as TabKey)}
      />
      {loading && pending === null ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
        </div>
      ) : tab === "pending" ? (
        <PendingChecksTab items={pending} busyId={busyId} onMarkReceived={markReceived} />
      ) : tab === "needs_review" ? (
        <NeedsReviewTab
          items={needsReview}
          busyId={busyId}
          onAccept={acceptProposed}
          onDismiss={dismiss}
        />
      ) : (
        <UnmatchedTab
          items={unmatched}
          busyId={busyId}
          onManualMatch={manualMatch}
          onDismiss={dismiss}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-tab components
// ---------------------------------------------------------------------------

function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-sm text-muted-foreground py-8 text-center">{message}</div>
  );
}

function PendingChecksTab({
  items,
  busyId,
  onMarkReceived,
}: {
  items: PendingCheck[] | null;
  busyId: string | null;
  onMarkReceived: (id: string) => Promise<void>;
}) {
  if (!items) return null;
  if (items.length === 0) {
    return (
      <EmptyState message="No pending checks. Mailed-check notifications appear here until you confirm the funds arrived." />
    );
  }
  return (
    <div className="space-y-2">
      {items.map((p) => (
        <Card key={p.id} className="shadow-sm border-l-4 border-amber-400">
          <CardContent className="p-4 flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{formatCurrency(p.amount)}</span>
                <Badge variant="outline" className="border-amber-400 text-amber-600">
                  {p.payment_method}
                </Badge>
                <span className="text-xs text-muted-foreground">{formatDate(p.payment_date)}</span>
              </div>
              <div className="text-sm text-muted-foreground truncate">
                {p.customer_name || "(unknown customer)"} ·{" "}
                {p.reference_number ? `#${p.reference_number}` : ""}
              </div>
              {p.notes ? (
                <div className="text-xs text-muted-foreground italic mt-0.5">{p.notes}</div>
              ) : null}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {p.source_message_id && (
                <Link
                  href={`/inbox?message=${p.source_message_id}`}
                  className="text-xs text-muted-foreground hover:text-foreground"
                  title="Open source email"
                >
                  <Mail className="h-4 w-4" />
                </Link>
              )}
              <Button
                size="sm"
                disabled={busyId === p.id}
                onClick={() => onMarkReceived(p.id)}
              >
                {busyId === p.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5 mr-1" />
                )}
                Mark received
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function NeedsReviewTab({
  items,
  busyId,
  onAccept,
  onDismiss,
}: {
  items: ParsedRow[] | null;
  busyId: string | null;
  onAccept: (parsedId: string, invoiceId: string) => Promise<void>;
  onDismiss: (parsedId: string) => Promise<void>;
}) {
  if (!items) return null;
  if (items.length === 0) {
    return (
      <EmptyState message="No matches awaiting review. Ambiguous parsed payments will appear here when the matcher finds multiple candidate invoices." />
    );
  }
  return (
    <div className="space-y-2">
      {items.map((pp) => (
        <Card key={pp.id} className="shadow-sm">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="secondary" className="capitalize">
                {pp.processor}
              </Badge>
              <span className="font-medium">{formatCurrency(pp.amount)}</span>
              <span className="text-sm text-muted-foreground">
                {pp.payer_name || pp.property_hint || "(unknown payer)"}
              </span>
              <span className="text-xs text-muted-foreground">{formatDate(pp.payment_date)}</span>
              {pp.match_confidence !== null && (
                <Badge variant="outline">
                  confidence {(pp.match_confidence * 100).toFixed(0)}%
                </Badge>
              )}
            </div>
            {pp.candidate_invoice_id ? (
              <div className="flex items-center justify-between gap-3 bg-muted/40 rounded p-2 text-sm">
                <div className="min-w-0">
                  <span className="text-muted-foreground">Candidate:</span>{" "}
                  <span className="font-medium">
                    {pp.candidate_invoice_number || pp.candidate_invoice_id.slice(0, 8)}
                  </span>{" "}
                  <span className="text-muted-foreground">
                    {formatCurrency(pp.candidate_invoice_total)}
                  </span>
                </div>
                {pp.match_reasoning && (
                  <span className="text-xs text-muted-foreground italic truncate ml-2 max-w-xs">
                    {pp.match_reasoning}
                  </span>
                )}
              </div>
            ) : null}
            <div className="flex items-center gap-2 justify-end">
              {pp.thread_id && (
                <Link
                  href={`/inbox?thread=${pp.thread_id}`}
                  className="text-xs text-muted-foreground hover:text-foreground mr-1"
                  title="Open source thread"
                >
                  <Mail className="h-4 w-4" />
                </Link>
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={busyId === pp.id}
                onClick={() => onDismiss(pp.id)}
                className="text-muted-foreground hover:text-destructive"
              >
                <XIcon className="h-3.5 w-3.5 mr-1" /> Dismiss
              </Button>
              <Button
                size="sm"
                disabled={busyId === pp.id || !pp.candidate_invoice_id}
                onClick={() => pp.candidate_invoice_id && onAccept(pp.id, pp.candidate_invoice_id)}
              >
                {busyId === pp.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5 mr-1" />
                )}
                Accept
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function UnmatchedTab({
  items,
  busyId,
  onManualMatch,
  onDismiss,
}: {
  items: ParsedRow[] | null;
  busyId: string | null;
  onManualMatch: (parsedId: string, invoiceId: string) => Promise<void>;
  onDismiss: (parsedId: string) => Promise<void>;
}) {
  const [invoiceInputs, setInvoiceInputs] = useState<Record<string, string>>({});
  if (!items) return null;
  if (items.length === 0) {
    return (
      <EmptyState message="No unmatched payments. Parsed payments with no candidate invoice appear here." />
    );
  }
  return (
    <div className="space-y-2">
      {items.map((pp) => (
        <Card key={pp.id} className="shadow-sm">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="secondary" className="capitalize">
                {pp.processor}
              </Badge>
              <span className="font-medium">{formatCurrency(pp.amount)}</span>
              <span className="text-sm text-muted-foreground">
                {pp.payer_name || pp.property_hint || "(unknown payer)"}
              </span>
              <span className="text-xs text-muted-foreground">{formatDate(pp.payment_date)}</span>
              {pp.payment_method && (
                <Badge variant="outline" className="capitalize">
                  {pp.payment_method}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 justify-end">
              {pp.thread_id && (
                <Link
                  href={`/inbox?thread=${pp.thread_id}`}
                  className="text-xs text-muted-foreground hover:text-foreground"
                  title="Open source thread"
                >
                  <Mail className="h-4 w-4" />
                </Link>
              )}
              <Input
                placeholder="Invoice ID"
                value={invoiceInputs[pp.id] || ""}
                onChange={(e) =>
                  setInvoiceInputs({ ...invoiceInputs, [pp.id]: e.target.value })
                }
                className="h-8 w-48 text-xs"
              />
              <Button
                size="sm"
                disabled={busyId === pp.id || !invoiceInputs[pp.id]}
                onClick={() => onManualMatch(pp.id, invoiceInputs[pp.id])}
              >
                {busyId === pp.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ArrowRight className="h-3.5 w-3.5 mr-1" />
                )}
                Match
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={busyId === pp.id}
                onClick={() => onDismiss(pp.id)}
                className="text-muted-foreground hover:text-destructive"
              >
                <XIcon className="h-3.5 w-3.5 mr-1" /> Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
