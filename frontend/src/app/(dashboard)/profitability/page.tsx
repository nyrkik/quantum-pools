"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
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
import { toast } from "sonner";
import {
  Loader2,
  TrendingUp,
  TrendingDown,
  DollarSign,
  AlertTriangle,
  Settings,
  Calculator,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ZAxis,
  Cell,
} from "recharts";
import type {
  ProfitabilityOverview,
  WhaleCurvePoint,
} from "@/types/profitability";

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function marginColor(margin: number, target: number) {
  if (margin >= target) return "text-green-600";
  if (margin >= target * 0.7) return "text-yellow-600";
  return "text-red-600";
}

function marginBadge(margin: number, target: number) {
  if (margin >= target)
    return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">{margin.toFixed(1)}%</Badge>;
  if (margin >= 0)
    return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">{margin.toFixed(1)}%</Badge>;
  return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">{margin.toFixed(1)}%</Badge>;
}

export default function ProfitabilityPage() {
  const [overview, setOverview] = useState<ProfitabilityOverview | null>(null);
  const [whaleCurve, setWhaleCurve] = useState<WhaleCurvePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [tableView, setTableView] = useState<"account" | "bow">("account");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<"all" | "residential" | "commercial">("all");
  const [sortCol, setSortCol] = useState<string>("margin");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [bowGaps, setBowGaps] = useState<any[] | null>(null);

  const loadBowGaps = useCallback(() => {
    if (bowGaps !== null) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    api.get<any[]>("/v1/profitability/gaps")
      .then(setBowGaps)
      .catch(() => setBowGaps([]));
  }, [bowGaps]);

  const loadData = useCallback(async () => {
    try {
      const [ov, wc] = await Promise.all([
        api.get<ProfitabilityOverview>("/v1/profitability/overview"),
        api.get<WhaleCurvePoint[]>("/v1/profitability/whale-curve"),
      ]);
      setOverview(ov);
      setWhaleCurve(wc);
    } catch {
      toast.error("Failed to load profitability data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading || !overview) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const filteredAccounts = overview.accounts.filter(a => typeFilter === "all" || a.customer_type === typeFilter);
  // Build per-BOW whale curve from filtered accounts
  const filteredWhale = (() => {
    const bowProfits = filteredAccounts.flatMap(a =>
      (a.bow_costs && a.bow_costs.length > 0)
        ? a.bow_costs.map(bc => ({ name: `${a.customer_name}${bc.bow_name ? ` — ${bc.bow_name}` : ""}`, profit: bc.profit, customer_id: a.customer_id }))
        : [{ name: a.customer_name, profit: a.cost_breakdown.profit, customer_id: a.customer_id }]
    );
    bowProfits.sort((a, b) => b.profit - a.profit);
    const totalProfit = bowProfits.reduce((s, b) => s + b.profit, 0);
    let cumulative = 0;
    return bowProfits.map((b, i) => {
      cumulative += b.profit;
      return { rank: i + 1, customer_name: b.name, customer_id: b.customer_id, cumulative_profit_pct: totalProfit !== 0 ? (cumulative / Math.abs(totalProfit) * 100) : 0, individual_profit: b.profit };
    });
  })();

  // Build per-BOW scatter data instead of per-account
  const scatterData = filteredAccounts.flatMap((a) =>
    (a.bow_costs && a.bow_costs.length > 0)
      ? a.bow_costs.map((bc) => ({
          x: bc.monthly_rate,
          y: bc.margin_pct,
          z: bc.difficulty_score,
          name: `${a.customer_name}${bc.bow_name ? ` — ${bc.bow_name}` : ""}`,
          id: a.customer_id,
        }))
      : [{
          x: a.monthly_rate,
          y: a.margin_pct,
          z: a.difficulty_score,
          name: a.customer_name,
          id: a.customer_id,
        }]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Profitability Analysis</h1>
          <p className="text-muted-foreground">
            {filteredAccounts.length} of {overview.total_accounts} accounts
          </p>
        </div>
        <div className="flex gap-2">
          <div className="flex gap-1">
            {(["all", "residential", "commercial"] as const).map((t) => (
              <Button key={t} variant={typeFilter === t ? "default" : "outline"} size="sm" className="h-8 text-xs capitalize" onClick={() => setTypeFilter(t)}>
                {t === "all" ? "All" : t === "residential" ? "Residential" : "Commercial"}
              </Button>
            ))}
          </div>
          <Link href="/profitability/bather-load">
            <Button variant="outline" size="sm">
              <Calculator className="mr-2 h-4 w-4" />
              Bather Load
            </Button>
          </Link>
          <Link href="/settings">
            <Button variant="outline" size="sm">
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </Button>
          </Link>
        </div>
      </div>

      {/* Summary Cards — reflect filter */}
      {(() => {
        const fRev = filteredAccounts.reduce((s, a) => s + a.cost_breakdown.revenue, 0);
        const fCost = filteredAccounts.reduce((s, a) => s + a.cost_breakdown.total_cost, 0);
        const fProfit = fRev - fCost;
        const fMargin = fRev > 0 ? (fProfit / fRev * 100) : 0;
        const fBelow = filteredAccounts.filter(a => a.margin_pct < overview.target_margin_pct).length;
        return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Monthly Revenue</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(fRev)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Monthly Profit</CardTitle>
            {fProfit >= 0 ? (
              <TrendingUp className="h-4 w-4 text-green-600" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-600" />
            )}
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${fProfit >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(fProfit)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Margin</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${marginColor(fMargin, overview.target_margin_pct)}`}>
              {fMargin.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">Target: {overview.target_margin_pct}%</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Below Target</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-600">{fBelow}</div>
            <p className="text-xs text-muted-foreground">
              of {filteredAccounts.length} accounts
            </p>
          </CardContent>
        </Card>
      </div>
        );
      })()}

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Whale Curve */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Whale Curve — Cumulative Profitability</CardTitle>
          </CardHeader>
          <CardContent>
            {filteredWhale.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={filteredWhale}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="rank"
                    label={{ value: "Account Rank", position: "insideBottom", offset: -5 }}
                  />
                  <YAxis
                    label={{ value: "Cumulative Profit %", angle: -90, position: "insideLeft" }}
                  />
                  <Tooltip
                    formatter={(value) => [`${(value as number).toFixed(1)}%`, "Cumulative Profit"]}
                    labelFormatter={(rank) => {
                      const pt = filteredWhale.find((w) => w.rank === rank);
                      return pt ? pt.customer_name : `#${rank}`;
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="cumulative_profit_pct"
                    stroke="#2989BE"
                    strokeWidth={2}
                    dot={(props: Record<string, unknown>) => {
                      const pt = filteredWhale[props.index as number];
                      if (!pt || pt.customer_id !== hoveredId) return <circle key={props.index as number} r={0} />;
                      return <circle key={props.index as number} cx={props.cx as number} cy={props.cy as number} r={6} fill="#2989BE" stroke="#fff" strokeWidth={2} />;
                    }}
                    activeDot={{ r: 6, stroke: "#fff", strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground py-12 text-center">
                No data yet
              </p>
            )}
          </CardContent>
        </Card>

        {/* Profitability Quadrant */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Revenue vs Margin</CardTitle>
          </CardHeader>
          <CardContent>
            {scatterData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    name="Revenue"
                    label={{ value: "Monthly Rate ($)", position: "insideBottom", offset: -5 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    name="Margin"
                    label={{ value: "Margin %", angle: -90, position: "insideLeft" }}
                  />
                  <ZAxis type="number" dataKey="z" range={[40, 200]} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="bg-background border rounded-md shadow-md px-3 py-2 text-sm">
                          <p className="font-semibold">{d.name}</p>
                          <p className="text-muted-foreground">{formatCurrency(d.x)}/mo · {d.y.toFixed(1)}% margin</p>
                        </div>
                      );
                    }}
                  />
                  <Scatter data={scatterData}>
                    {scatterData.map((entry, i) => {
                      const isHovered = entry.id === hoveredId;
                      const baseColor = entry.y >= overview.target_margin_pct ? "#22c55e" : entry.y >= 0 ? "#eab308" : "#ef4444";
                      return (
                        <Cell
                          key={i}
                          fill={isHovered ? "#2989BE" : baseColor}
                          stroke={isHovered ? "#fff" : "none"}
                          strokeWidth={isHovered ? 2 : 0}
                          r={isHovered ? 8 : undefined}
                        />
                      );
                    })}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground py-12 text-center">
                No data yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Account Table + Per-BOW view */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Margin Analysis</CardTitle>
            <div className="flex gap-1">
              <Button variant={tableView === "account" ? "default" : "outline"} size="sm" className="h-7 text-xs" onClick={() => setTableView("account")}>By Account</Button>
              <Button variant={tableView === "bow" ? "default" : "outline"} size="sm" className="h-7 text-xs" onClick={() => { setTableView("bow"); loadBowGaps(); }}>By Water Feature</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {tableView === "account" ? (() => {
            const filtered = overview.accounts.filter(a => typeFilter === "all" || a.customer_type === typeFilter);
            const sorted = [...filtered].sort((a, b) => {
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
            const SortHead = ({ col, children, align }: { col: string; children: React.ReactNode; align?: string }) => (
              <TableHead className={`${align || ""} cursor-pointer select-none hover:text-foreground`} onClick={() => { if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc"); else { setSortCol(col); setSortDir("asc"); } }}>
                {children} {sortCol === col ? (sortDir === "asc" ? "↑" : "↓") : ""}
              </TableHead>
            );
            return (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHead col="name">Client</SortHead>
                  <TableHead>Address</TableHead>
                  <SortHead col="rate" align="text-right">Rate</SortHead>
                  <SortHead col="cost" align="text-right">Cost</SortHead>
                  <SortHead col="profit" align="text-right">Profit</SortHead>
                  <SortHead col="margin" align="text-right">Margin</SortHead>
                  <SortHead col="suggested" align="text-right">Suggested</SortHead>
                  <SortHead col="difficulty" align="text-right">Difficulty</SortHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((account, i) => (
                  <TableRow key={`${account.customer_id}-${account.property_id}`} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${hoveredId === account.customer_id ? "bg-blue-100 dark:bg-blue-900" : i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`} onMouseEnter={() => setHoveredId(account.customer_id)} onMouseLeave={() => setHoveredId(null)}>
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
                      {marginBadge(account.margin_pct, overview.target_margin_pct)}
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
          })() : bowGaps === null ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (() => {
            const filteredGaps = bowGaps.filter((g: Record<string, unknown>) => typeFilter === "all" || g.customer_type === typeFilter);
            const sortedGaps = [...filteredGaps].sort((a: Record<string, unknown>, b: Record<string, unknown>) => {
              const dir = sortDir === "asc" ? 1 : -1;
              switch (sortCol) {
                case "name": return dir * String(a.customer_name || "").localeCompare(String(b.customer_name || ""));
                case "rate": return dir * ((a.monthly_rate as number) - (b.monthly_rate as number));
                case "cost": return dir * ((a.total_cost as number) - (b.total_cost as number));
                case "profit": return dir * ((a.profit as number) - (b.profit as number));
                case "margin": return dir * ((a.margin_pct as number) - (b.margin_pct as number));
                case "suggested": return dir * ((a.suggested_rate as number) - (b.suggested_rate as number));
                default: return dir * ((a.margin_pct as number) - (b.margin_pct as number));
              }
            });
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const SortHead2 = ({ col, children, align }: { col: string; children: React.ReactNode; align?: string }) => (
              <TableHead className={`${align || ""} cursor-pointer select-none hover:text-foreground`} onClick={() => { if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc"); else { setSortCol(col); setSortDir("asc"); } }}>
                {children} {sortCol === col ? (sortDir === "asc" ? "↑" : "↓") : ""}
              </TableHead>
            );
            return (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHead2 col="name">Client</SortHead2>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Gallons</TableHead>
                  <SortHead2 col="rate" align="text-right">Rate</SortHead2>
                  <SortHead2 col="cost" align="text-right">Cost</SortHead2>
                  <SortHead2 col="profit" align="text-right">Profit</SortHead2>
                  <SortHead2 col="margin" align="text-right">Margin</SortHead2>
                  <SortHead2 col="suggested" align="text-right">Suggested</SortHead2>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedGaps.map((gap: Record<string, unknown>, i: number) => (
                  <TableRow key={gap.bow_id as string} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${hoveredId === gap.customer_id ? "bg-blue-100 dark:bg-blue-900" : gap.below_target ? "bg-red-50/50 dark:bg-red-950/10" : i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`} onMouseEnter={() => setHoveredId(gap.customer_id as string)} onMouseLeave={() => setHoveredId(null)}>
                    <TableCell>
                      <Link
                        href={`/profitability/${gap.customer_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {String(gap.customer_name)}
                      </Link>
                      {gap.bow_name ? <span className="text-xs text-muted-foreground ml-1.5">{String(gap.bow_name)}</span> : null}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground capitalize">{String(gap.water_type)}</TableCell>
                    <TableCell className="text-right text-sm">{(gap.gallons as number)?.toLocaleString()}</TableCell>
                    <TableCell className="text-right">{(gap.monthly_rate as number) > 0 ? formatCurrency(gap.monthly_rate as number) : <span className="text-muted-foreground/50">—</span>}</TableCell>
                    <TableCell className="text-right">{formatCurrency(gap.total_cost as number)}</TableCell>
                    <TableCell className={`text-right font-medium ${(gap.profit as number) >= 0 ? "text-green-600" : "text-red-600"}`}>{formatCurrency(gap.profit as number)}</TableCell>
                    <TableCell className="text-right">{marginBadge(gap.margin_pct as number, overview.target_margin_pct)}</TableCell>
                    <TableCell className="text-right">
                      {(gap.rate_gap as number) > 0 ? <span className="text-yellow-600">{formatCurrency(gap.suggested_rate as number)}</span> : <span className="text-green-600">OK</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            );
          })()}
        </CardContent>
      </Card>
    </div>
  );
}
