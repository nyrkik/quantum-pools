"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Loader2,
  Send,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { api } from "@/lib/api";

interface DunningRow {
  invoice_id: string;
  invoice_number: string | null;
  customer_id: string | null;
  balance: number;
  days_past_due: number;
  next_step: number;
  recipient_email: string | null;
  recipients: string[];
  recipient_count: number;
  has_recipient: boolean;
}

interface DunningPreview {
  mode: "dry_run" | "live";
  as_of: string;
  eligible: number;
  would_send_count: number;
  would_send: DunningRow[];
  not_due_yet_count: number;
  missing_recipient_count: number;
}

interface DunningRunResult {
  mode: "live";
  eligible: number;
  sent: number;
  skipped_not_due_yet: number;
  errors: string[];
}

const STEP_LABEL: Record<number, string> = {
  1: "Initial reminder",
  2: "3 days past due",
  3: "Service at risk",
  4: "Final notice",
};

type SortKey =
  | "invoice_number"
  | "recipient"
  | "balance"
  | "days_past_due"
  | "next_step";
type SortDir = "asc" | "desc";

function fmt(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function compareDunning(a: DunningRow, b: DunningRow, key: SortKey, dir: SortDir): number {
  let cmp = 0;
  switch (key) {
    case "invoice_number": {
      const av = a.invoice_number ?? "";
      const bv = b.invoice_number ?? "";
      cmp = av.localeCompare(bv);
      break;
    }
    case "recipient": {
      const av = a.recipients[0] ?? "";
      const bv = b.recipients[0] ?? "";
      cmp = av.localeCompare(bv);
      break;
    }
    case "balance":
      cmp = a.balance - b.balance;
      break;
    case "days_past_due":
      cmp = a.days_past_due - b.days_past_due;
      break;
    case "next_step":
      cmp = a.next_step - b.next_step;
      break;
  }
  return dir === "asc" ? cmp : -cmp;
}

export function DunningPreview() {
  const [preview, setPreview] = useState<DunningPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Default sort: oldest invoices first — matches the natural collection
  // priority and the backend's default ordering.
  const [sortKey, setSortKey] = useState<SortKey>("days_past_due");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function clickHeader(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      // Numeric columns: desc-first (biggest at top). Text: asc.
      const isText = key === "invoice_number" || key === "recipient";
      setSortDir(isText ? "asc" : "desc");
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.post<DunningPreview>(
        "/v1/billing/dunning/run?dry_run=true",
        {}
      );
      setPreview(res);
      // Default selection: every row that has a recipient. Rows with no
      // recipient can't be sent at all, so they're never selectable.
      setSelected(
        new Set(res.would_send.filter((r) => r.has_recipient).map((r) => r.invoice_id))
      );
    } catch (err) {
      toast.error((err as Error).message || "Failed to load reminder queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const sortedRows = useMemo(() => {
    if (!preview) return [];
    return [...preview.would_send].sort((a, b) =>
      compareDunning(a, b, sortKey, sortDir)
    );
  }, [preview, sortKey, sortDir]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll(allSelected: boolean) {
    if (!preview) return;
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(
        new Set(
          preview.would_send.filter((r) => r.has_recipient).map((r) => r.invoice_id)
        )
      );
    }
  }

  async function fireSend() {
    setSending(true);
    setConfirmOpen(false);
    try {
      const res = await api.post<DunningRunResult>(
        "/v1/billing/dunning/run?dry_run=false",
        { invoice_ids: [...selected] }
      );
      if (res.errors && res.errors.length > 0) {
        toast.error(
          `Sent ${res.sent}, ${res.errors.length} failed. First: ${res.errors[0]}`
        );
      } else {
        toast.success(`Sent ${res.sent} payment reminder${res.sent === 1 ? "" : "s"}.`);
      }
      await load();
    } catch (err) {
      toast.error((err as Error).message || "Send failed");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading reminder queue…
      </div>
    );
  }

  if (!preview) return null;

  const wouldSend = preview.would_send;
  const sendableCount = wouldSend.filter((r) => r.has_recipient).length;
  const selectedCount = selected.size;
  const allSelected = selectedCount === sendableCount && sendableCount > 0;

  return (
    <div className="space-y-4">
      <Card className="shadow-sm">
        <CardContent className="p-5 sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Reminder queue · as of {preview.as_of}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-6 text-sm">
                <div>
                  <div className="text-2xl font-semibold tabular-nums">
                    {preview.would_send_count}
                  </div>
                  <div className="text-xs text-muted-foreground">due to send</div>
                </div>
                <div>
                  <div className="text-2xl font-semibold tabular-nums text-muted-foreground">
                    {preview.not_due_yet_count}
                  </div>
                  <div className="text-xs text-muted-foreground">not yet due</div>
                </div>
                <div>
                  <div className="text-2xl font-semibold tabular-nums text-muted-foreground">
                    {preview.eligible}
                  </div>
                  <div className="text-xs text-muted-foreground">total eligible</div>
                </div>
              </div>
              {preview.missing_recipient_count > 0 ? (
                <div className="mt-3 flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5" />
                  <span>
                    {preview.missing_recipient_count} row
                    {preview.missing_recipient_count === 1 ? " has" : "s have"} no
                    recipient email and can&apos;t be sent.
                  </span>
                </div>
              ) : null}
              <div className="mt-2 text-xs text-muted-foreground">
                PSS-imported invoices are excluded from reminders by design — review them manually.
              </div>
            </div>

            <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
              <AlertDialogTrigger asChild>
                <Button disabled={selectedCount === 0 || sending} size="sm">
                  {sending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Sending…
                    </>
                  ) : (
                    <>
                      <Send className="h-4 w-4 mr-2" />
                      Send {selectedCount} reminder{selectedCount === 1 ? "" : "s"}
                    </>
                  )}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    Send {selectedCount} payment reminder{selectedCount === 1 ? "" : "s"}?
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    Each selected customer will receive an email matching their next
                    escalation step (initial → 3-day → service-at-risk → final notice).
                    The invoice&apos;s reminder counter only advances for emails that
                    actually deliver.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={fireSend}>
                    Send now
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>

      {wouldSend.length === 0 ? (
        <Card className="shadow-sm">
          <CardContent className="py-8 text-center text-muted-foreground text-sm">
            No invoices are due for a reminder today.
          </CardContent>
        </Card>
      ) : (
        <Card className="shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 dark:bg-slate-800 text-xs font-medium uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2.5 w-10">
                    <Checkbox
                      checked={allSelected}
                      onCheckedChange={() => toggleAll(allSelected)}
                      aria-label="Select all"
                    />
                  </th>
                  <DunningHeader label="Invoice" align="left" sortKey="invoice_number" active={sortKey} dir={sortDir} onClick={clickHeader} />
                  <DunningHeader label="Recipient" align="left" sortKey="recipient" active={sortKey} dir={sortDir} onClick={clickHeader} />
                  <DunningHeader label="Balance" align="right" sortKey="balance" active={sortKey} dir={sortDir} onClick={clickHeader} />
                  <DunningHeader label="Past due" align="right" sortKey="days_past_due" active={sortKey} dir={sortDir} onClick={clickHeader} />
                  <DunningHeader label="Reminder type" align="left" sortKey="next_step" active={sortKey} dir={sortDir} onClick={clickHeader} />
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((r, idx) => {
                  const isSelected = selected.has(r.invoice_id);
                  return (
                    <tr
                      key={r.invoice_id}
                      className={
                        "hover:bg-blue-50 dark:hover:bg-blue-950 " +
                        (idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : "") +
                        (r.has_recipient ? "" : " opacity-60")
                      }
                    >
                      <td className="px-3 py-2">
                        <Checkbox
                          checked={isSelected}
                          disabled={!r.has_recipient}
                          onCheckedChange={() => toggle(r.invoice_id)}
                          aria-label={`Select invoice ${r.invoice_number ?? r.invoice_id}`}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          href={`/invoices/${r.invoice_id}`}
                          className="text-primary hover:underline"
                        >
                          {r.invoice_number ? `#${r.invoice_number}` : r.invoice_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-3 py-2">
                        {r.has_recipient ? (
                          <div className="text-xs">
                            <div className="truncate max-w-xs" title={r.recipients.join(", ")}>
                              {r.recipients[0]}
                            </div>
                            {r.recipient_count > 1 ? (
                              <div className="text-muted-foreground mt-0.5">
                                +{r.recipient_count - 1} more —{" "}
                                {r.recipient_count} email
                                {r.recipient_count === 1 ? "" : "s"} will go out
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          <span className="text-xs italic text-amber-700 dark:text-amber-400">
                            (no recipient)
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">
                        {fmt(r.balance)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                        {r.days_past_due}d
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {STEP_LABEL[r.next_step] || `Step ${r.next_step}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function DunningHeader({
  label,
  align,
  sortKey,
  active,
  dir,
  onClick,
}: {
  label: string;
  align: "left" | "right";
  sortKey: SortKey;
  active: SortKey;
  dir: SortDir;
  onClick: (k: SortKey) => void;
}) {
  const isActive = sortKey === active;
  const Icon = !isActive ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      className={
        "px-3 py-2.5 select-none cursor-pointer hover:text-foreground " +
        (align === "left" ? "text-left" : "text-right")
      }
      onClick={() => onClick(sortKey)}
    >
      <span
        className={
          "inline-flex items-center gap-1 " +
          (align === "right" ? "justify-end" : "")
        }
      >
        {label}
        <Icon className={"h-3 w-3 " + (isActive ? "opacity-80" : "opacity-30")} />
      </span>
    </th>
  );
}
