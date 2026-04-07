"use client";

import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency } from "@/lib/format";
import { marginBadge } from "./margin-helpers";

interface WfGapRow {
  wf_id: string;
  customer_id: string;
  customer_name: string;
  customer_type: string;
  wf_name: string | null;
  water_type: string;
  gallons: number;
  monthly_rate: number;
  total_cost: number;
  profit: number;
  margin_pct: number;
  suggested_rate: number;
  rate_gap: number;
  below_target: boolean;
}

interface WfGapsTableProps {
  gaps: WfGapRow[];
  targetMarginPct: number;
  sortCol: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
}

function SortHead({ col, currentCol, currentDir, onSort, children, align }: {
  col: string;
  currentCol: string;
  currentDir: "asc" | "desc";
  onSort: (col: string) => void;
  children: React.ReactNode;
  align?: string;
}) {
  return (
    <TableHead
      className={`${align || ""} cursor-pointer select-none hover:text-foreground`}
      onClick={() => onSort(col)}
    >
      {children} {currentCol === col ? (currentDir === "asc" ? "\u2191" : "\u2193") : ""}
    </TableHead>
  );
}

export function WfGapsTable({ gaps, targetMarginPct, sortCol, sortDir, onSort, hoveredId, onHover }: WfGapsTableProps) {
  const sorted = [...gaps].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    switch (sortCol) {
      case "name": return dir * a.customer_name.localeCompare(b.customer_name);
      case "rate": return dir * (a.monthly_rate - b.monthly_rate);
      case "cost": return dir * (a.total_cost - b.total_cost);
      case "profit": return dir * (a.profit - b.profit);
      case "margin": return dir * (a.margin_pct - b.margin_pct);
      case "suggested": return dir * (a.suggested_rate - b.suggested_rate);
      default: return dir * (a.margin_pct - b.margin_pct);
    }
  });

  const headProps = { currentCol: sortCol, currentDir: sortDir, onSort };

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortHead col="name" {...headProps}>Client</SortHead>
          <TableHead>Type</TableHead>
          <TableHead className="text-right">Gallons</TableHead>
          <SortHead col="rate" align="text-right" {...headProps}>Rate</SortHead>
          <SortHead col="cost" align="text-right" {...headProps}>Cost</SortHead>
          <SortHead col="profit" align="text-right" {...headProps}>Profit</SortHead>
          <SortHead col="margin" align="text-right" {...headProps}>Margin</SortHead>
          <SortHead col="suggested" align="text-right" {...headProps}>Suggested</SortHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((gap, i) => (
          <TableRow
            key={gap.wf_id}
            className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${hoveredId === gap.customer_id ? "bg-blue-100 dark:bg-blue-900" : gap.below_target ? "bg-red-50/50 dark:bg-red-950/10" : i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
            onMouseEnter={() => onHover(gap.customer_id)}
            onMouseLeave={() => onHover(null)}
          >
            <TableCell>
              <Link
                href={`/profitability/${gap.customer_id}`}
                className="font-medium text-primary hover:underline"
              >
                {gap.customer_name}
              </Link>
              {gap.wf_name ? <span className="text-xs text-muted-foreground ml-1.5">{gap.wf_name}</span> : null}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground capitalize">{gap.water_type}</TableCell>
            <TableCell className="text-right text-sm">{gap.gallons?.toLocaleString()}</TableCell>
            <TableCell className="text-right">{gap.monthly_rate > 0 ? formatCurrency(gap.monthly_rate) : <span className="text-muted-foreground/50">&mdash;</span>}</TableCell>
            <TableCell className="text-right">{formatCurrency(gap.total_cost)}</TableCell>
            <TableCell className={`text-right font-medium ${gap.profit >= 0 ? "text-green-600" : "text-red-600"}`}>{formatCurrency(gap.profit)}</TableCell>
            <TableCell className="text-right">{marginBadge(gap.margin_pct, targetMarginPct)}</TableCell>
            <TableCell className="text-right">
              {gap.rate_gap > 0 ? <span className="text-yellow-600">{formatCurrency(gap.suggested_rate)}</span> : <span className="text-green-600">OK</span>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
