"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Loader2,
  CheckCircle2,
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

interface LateFeeRow {
  invoice_id: string;
  invoice_number: string | null;
  customer_id: string | null;
  customer_name: string;
  balance: number;
  days_past_due: number;
  fee: number;
}

interface LateFeePreviewResponse {
  mode?: "dry_run";
  as_of: string;
  enabled: boolean;
  grace_days?: number;
  fee_type?: "flat" | "percent";
  fee_amount?: number;
  fee_minimum?: number | null;
  would_apply_count: number;
  would_apply: LateFeeRow[];
}

interface LateFeeRunResult {
  mode: "live";
  as_of: string;
  enabled: boolean;
  applied: number;
  skipped: number;
  errors: string[];
}

type SortKey =
  | "invoice_number"
  | "customer_name"
  | "balance"
  | "days_past_due"
  | "fee";
type SortDir = "asc" | "desc";

function fmt(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function compareRow(
  a: LateFeeRow,
  b: LateFeeRow,
  key: SortKey,
  dir: SortDir,
): number {
  let cmp = 0;
  switch (key) {
    case "invoice_number": {
      const av = a.invoice_number ?? "";
      const bv = b.invoice_number ?? "";
      cmp = av.localeCompare(bv);
      break;
    }
    case "customer_name":
      cmp = a.customer_name.localeCompare(b.customer_name);
      break;
    case "balance":
      cmp = a.balance - b.balance;
      break;
    case "days_past_due":
      cmp = a.days_past_due - b.days_past_due;
      break;
    case "fee":
      cmp = a.fee - b.fee;
      break;
  }
  return dir === "asc" ? cmp : -cmp;
}

export function LateFeePreview() {
  const [preview, setPreview] = useState<LateFeePreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<SortKey>("days_past_due");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function clickHeader(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      const isText = key === "invoice_number" || key === "customer_name";
      setSortDir(isText ? "asc" : "desc");
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.post<LateFeePreviewResponse>(
        "/v1/billing/late-fees/run?dry_run=true",
        {},
      );
      setPreview(res);
      setSelected(new Set(res.would_apply.map((r) => r.invoice_id)));
    } catch (err) {
      toast.error((err as Error).message || "Failed to load late-fee queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const sortedRows = useMemo(() => {
    if (!preview) return [];
    return [...preview.would_apply].sort((a, b) =>
      compareRow(a, b, sortKey, sortDir),
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
      setSelected(new Set(preview.would_apply.map((r) => r.invoice_id)));
    }
  }

  async function fireApply() {
    setRunning(true);
    setConfirmOpen(false);
    try {
      const res = await api.post<LateFeeRunResult>(
        "/v1/billing/late-fees/run?dry_run=false",
        { invoice_ids: [...selected] },
      );
      if (res.errors && res.errors.length > 0) {
        toast.error(
          `Applied ${res.applied}, ${res.errors.length} failed. First: ${res.errors[0]}`,
        );
      } else {
        toast.success(
          `Applied ${res.applied} late fee${res.applied === 1 ? "" : "s"}.`,
        );
      }
      await load();
    } catch (err) {
      toast.error((err as Error).message || "Apply failed");
    } finally {
      setRunning(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading late-fee queue…
      </div>
    );
  }

  if (!preview) return null;

  if (!preview.enabled) {
    return (
      <Card className="shadow-sm">
        <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
          <div>Late fees are disabled for this org.</div>
          <Link
            href="/settings?tab=billing"
            className="inline-block text-primary hover:underline text-xs"
          >
            Configure in Settings → Billing
          </Link>
        </CardContent>
      </Card>
    );
  }

  const wouldApply = preview.would_apply;
  const selectedCount = selected.size;
  const allSelected = selectedCount === wouldApply.length && wouldApply.length > 0;
  const totalFee = sortedRows
    .filter((r) => selected.has(r.invoice_id))
    .reduce((s, r) => s + r.fee, 0);

  const policyLabel =
    preview.fee_type === "percent"
      ? `${preview.fee_amount}% of balance${preview.fee_minimum ? ` (min ${fmt(preview.fee_minimum)})` : ""}`
      : `${fmt(preview.fee_amount || 0)} flat`;

  return (
    <div className="space-y-4">
      <Card className="shadow-sm">
        <CardContent className="p-5 sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Late-fee queue · as of {preview.as_of}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-6 text-sm">
                <div>
                  <div className="text-2xl font-semibold tabular-nums">
                    {preview.would_apply_count}
                  </div>
                  <div className="text-xs text-muted-foreground">eligible</div>
                </div>
                <div>
                  <div className="text-2xl font-semibold tabular-nums text-muted-foreground">
                    {preview.grace_days}d
                  </div>
                  <div className="text-xs text-muted-foreground">grace period</div>
                </div>
                <div>
                  <div className="text-2xl font-semibold tabular-nums text-muted-foreground">
                    {policyLabel}
                  </div>
                  <div className="text-xs text-muted-foreground">policy</div>
                </div>
              </div>
              <div className="mt-3 text-xs text-muted-foreground">
                PSS-imported invoices and customers with late-fee opt-out are excluded.
                Already-applied fees are skipped.
              </div>
            </div>

            <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
              <AlertDialogTrigger asChild>
                <Button disabled={selectedCount === 0 || running} size="sm">
                  {running ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Applying…
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                      Apply {selectedCount} fee{selectedCount === 1 ? "" : "s"} ({fmt(totalFee)})
                    </>
                  )}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    Apply {selectedCount} late fee{selectedCount === 1 ? "" : "s"}?
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    Each selected invoice gets a new line item ({policyLabel}) and the invoice
                    total recalculates. The customer is not notified by this action — the next
                    dunning email mentions the fee. Total this run: {fmt(totalFee)}.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={fireApply}>Apply now</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>

      {wouldApply.length === 0 ? (
        <Card className="shadow-sm">
          <CardContent className="py-8 text-center text-muted-foreground text-sm">
            No invoices are eligible for a late fee today.
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
                  <Header
                    label="Invoice"
                    align="left"
                    sortKey="invoice_number"
                    active={sortKey}
                    dir={sortDir}
                    onClick={clickHeader}
                  />
                  <Header
                    label="Customer"
                    align="left"
                    sortKey="customer_name"
                    active={sortKey}
                    dir={sortDir}
                    onClick={clickHeader}
                  />
                  <Header
                    label="Balance"
                    align="right"
                    sortKey="balance"
                    active={sortKey}
                    dir={sortDir}
                    onClick={clickHeader}
                  />
                  <Header
                    label="Past due"
                    align="right"
                    sortKey="days_past_due"
                    active={sortKey}
                    dir={sortDir}
                    onClick={clickHeader}
                  />
                  <Header
                    label="Fee"
                    align="right"
                    sortKey="fee"
                    active={sortKey}
                    dir={sortDir}
                    onClick={clickHeader}
                  />
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
                        (idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : "")
                      }
                    >
                      <td className="px-3 py-2">
                        <Checkbox
                          checked={isSelected}
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
                        {r.customer_id ? (
                          <Link
                            href={`/customers/${r.customer_id}`}
                            className="hover:underline"
                          >
                            {r.customer_name}
                          </Link>
                        ) : (
                          r.customer_name
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">
                        {fmt(r.balance)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                        {r.days_past_due}d
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">
                        {fmt(r.fee)}
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

function Header({
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
