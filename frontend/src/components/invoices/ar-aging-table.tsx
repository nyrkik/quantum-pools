"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, ArrowUpDown, Download, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface AgingRow {
  customer_id: string | null;
  customer_name: string;
  current: number;
  days_30: number;
  days_60: number;
  days_90: number;
  over_90: number;
  total_owed: number;
  invoice_count: number;
  oldest_invoice_age_days: number;
}

interface AgingResponse {
  as_of: string;
  rows: AgingRow[];
  totals: {
    current: number;
    days_30: number;
    days_60: number;
    days_90: number;
    over_90: number;
    total_owed: number;
    invoice_count: number;
  };
}

type SortKey =
  | "customer_name"
  | "current"
  | "days_30"
  | "days_60"
  | "days_90"
  | "over_90"
  | "total_owed"
  | "invoice_count"
  | "oldest_invoice_age_days";

type SortDir = "asc" | "desc";

function fmt(n: number): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function compare(a: AgingRow, b: AgingRow, key: SortKey, dir: SortDir): number {
  const av = a[key];
  const bv = b[key];
  let cmp = 0;
  if (typeof av === "string" && typeof bv === "string") {
    cmp = av.localeCompare(bv);
  } else if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv;
  }
  return dir === "asc" ? cmp : -cmp;
}

export function ArAgingTable() {
  const [data, setData] = useState<AgingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("total_owed");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    api
      .get<AgingResponse>("/v1/billing/ar-aging")
      .then((r) => setData(r))
      .finally(() => setLoading(false));
  }, []);

  const sortedRows = useMemo(() => {
    if (!data) return [];
    return [...data.rows].sort((a, b) => compare(a, b, sortKey, sortDir));
  }, [data, sortKey, sortDir]);

  function clickHeader(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      // First click on a numeric column lands on desc (biggest first —
      // typically what you want for outstanding-balance columns); on a
      // text column, asc.
      setSortDir(key === "customer_name" ? "asc" : "desc");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
      </div>
    );
  }

  if (!data || data.rows.length === 0) {
    return (
      <Card className="shadow-sm">
        <CardContent className="py-12 text-center text-muted-foreground">
          No outstanding invoices.
        </CardContent>
      </Card>
    );
  }

  const cols: { key: SortKey; label: string; align: "left" | "right"; destructive?: boolean }[] = [
    { key: "customer_name", label: "Customer", align: "left" },
    { key: "current", label: "Current", align: "right" },
    { key: "days_30", label: "1-30", align: "right" },
    { key: "days_60", label: "31-60", align: "right" },
    { key: "days_90", label: "61-90", align: "right" },
    { key: "over_90", label: "90+", align: "right", destructive: true },
    { key: "total_owed", label: "Total", align: "right" },
    { key: "invoice_count", label: "Inv", align: "right" },
    { key: "oldest_invoice_age_days", label: "Oldest", align: "right" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">As of {data.as_of}</div>
        <a href="/api/v1/billing/ar-aging?format=csv" download className="inline-flex">
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4 mr-2" />
            CSV
          </Button>
        </a>
      </div>
      <Card className="shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 dark:bg-slate-800 text-xs font-medium uppercase tracking-wide">
              <tr>
                {cols.map((c) => (
                  <SortableHeader
                    key={c.key}
                    label={c.label}
                    align={c.align}
                    destructive={c.destructive}
                    active={sortKey === c.key}
                    dir={sortDir}
                    onClick={() => clickHeader(c.key)}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((r, idx) => (
                <tr
                  key={r.customer_id ?? `_${idx}`}
                  className={
                    "hover:bg-blue-50 dark:hover:bg-blue-950 " +
                    (idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : "")
                  }
                >
                  <td className="px-4 py-2">
                    {r.customer_id ? (
                      <Link
                        href={`/customers/${r.customer_id}`}
                        className="text-primary hover:underline"
                      >
                        {r.customer_name}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground italic">{r.customer_name}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(r.current)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(r.days_30)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(r.days_60)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(r.days_90)}</td>
                  <td
                    className={
                      "px-3 py-2 text-right tabular-nums " +
                      (r.over_90 > 0 ? "text-destructive font-medium" : "")
                    }
                  >
                    {fmt(r.over_90)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium">
                    {fmt(r.total_owed)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {r.invoice_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {r.oldest_invoice_age_days}d
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-100 dark:bg-slate-800 font-medium text-sm">
              <tr>
                <td className="px-4 py-2.5">TOTAL</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(data.totals.current)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(data.totals.days_30)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(data.totals.days_60)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(data.totals.days_90)}</td>
                <td
                  className={
                    "px-3 py-2.5 text-right tabular-nums " +
                    (data.totals.over_90 > 0 ? "text-destructive" : "")
                  }
                >
                  {fmt(data.totals.over_90)}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(data.totals.total_owed)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                  {data.totals.invoice_count}
                </td>
                <td className="px-3 py-2.5"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>
    </div>
  );
}

function SortableHeader({
  label,
  align,
  destructive,
  active,
  dir,
  onClick,
}: {
  label: string;
  align: "left" | "right";
  destructive?: boolean;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      className={
        "px-3 py-2.5 select-none cursor-pointer " +
        (align === "left" ? "text-left" : "text-right") +
        (destructive ? " text-destructive" : "") +
        " hover:text-foreground"
      }
      onClick={onClick}
    >
      <span className={"inline-flex items-center gap-1 " + (align === "right" ? "justify-end" : "")}>
        {label}
        <Icon
          className={
            "h-3 w-3 " +
            (active ? "opacity-80" : "opacity-30")
          }
        />
      </span>
    </th>
  );
}
