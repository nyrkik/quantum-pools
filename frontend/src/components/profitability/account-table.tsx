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
import type { ProfitabilityAccount } from "@/types/profitability";

interface AccountTableProps {
  accounts: ProfitabilityAccount[];
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

export function AccountTable({ accounts, targetMarginPct, sortCol, sortDir, onSort, hoveredId, onHover }: AccountTableProps) {
  const sorted = [...accounts].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    switch (sortCol) {
      case "name": return dir * a.customer_name.localeCompare(b.customer_name);
      case "rate": return dir * (a.monthly_rate - b.monthly_rate);
      case "cost": return dir * (a.cost_breakdown.total_cost - b.cost_breakdown.total_cost);
      case "profit": return dir * (a.cost_breakdown.profit - b.cost_breakdown.profit);
      case "margin": return dir * (a.margin_pct - b.margin_pct);
      case "suggested": return dir * (a.cost_breakdown.suggested_rate - b.cost_breakdown.suggested_rate);
      case "difficulty": return dir * (a.difficulty_score - b.difficulty_score);
      default: return dir * (a.margin_pct - b.margin_pct);
    }
  });

  const headProps = { currentCol: sortCol, currentDir: sortDir, onSort };

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortHead col="name" {...headProps}>Client</SortHead>
          <TableHead>Address</TableHead>
          <SortHead col="rate" align="text-right" {...headProps}>Rate</SortHead>
          <SortHead col="cost" align="text-right" {...headProps}>Cost</SortHead>
          <SortHead col="profit" align="text-right" {...headProps}>Profit</SortHead>
          <SortHead col="margin" align="text-right" {...headProps}>Margin</SortHead>
          <SortHead col="suggested" align="text-right" {...headProps}>Suggested</SortHead>
          <SortHead col="difficulty" align="text-right" {...headProps}>Difficulty</SortHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((account, i) => (
          <TableRow
            key={`${account.customer_id}-${account.property_id}`}
            className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${hoveredId === account.customer_id ? "bg-blue-100 dark:bg-blue-900" : i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
            onMouseEnter={() => onHover(account.customer_id)}
            onMouseLeave={() => onHover(null)}
          >
            <TableCell>
              <Link
                href={`/profitability/${account.customer_id}`}
                className="font-medium text-primary hover:underline"
              >
                {account.customer_name}
              </Link>
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {account.property_address}
            </TableCell>
            <TableCell className="text-right">
              {formatCurrency(account.monthly_rate)}
            </TableCell>
            <TableCell className="text-right">
              {formatCurrency(account.cost_breakdown.total_cost)}
            </TableCell>
            <TableCell
              className={`text-right font-medium ${
                account.cost_breakdown.profit >= 0 ? "text-green-600" : "text-red-600"
              }`}
            >
              {formatCurrency(account.cost_breakdown.profit)}
            </TableCell>
            <TableCell className="text-right">
              {marginBadge(account.margin_pct, targetMarginPct)}
            </TableCell>
            <TableCell className="text-right">
              {account.cost_breakdown.rate_gap > 0 ? (
                <span className="text-yellow-600">
                  {formatCurrency(account.cost_breakdown.suggested_rate)}
                </span>
              ) : (
                <span className="text-green-600">OK</span>
              )}
            </TableCell>
            <TableCell className="text-right">
              {account.difficulty_score.toFixed(1)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
