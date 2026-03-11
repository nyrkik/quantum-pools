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

  const scatterData = overview.accounts.map((a) => ({
    x: a.monthly_rate,
    y: a.margin_pct,
    z: a.difficulty_score,
    name: a.customer_name,
    id: a.customer_id,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Profitability Analysis</h1>
          <p className="text-muted-foreground">
            {overview.total_accounts} accounts analyzed
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/profitability/bather-load">
            <Button variant="outline" size="sm">
              <Calculator className="mr-2 h-4 w-4" />
              Bather Load
            </Button>
          </Link>
          <Link href="/profitability/settings">
            <Button variant="outline" size="sm">
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </Button>
          </Link>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Monthly Revenue</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(overview.total_revenue)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Monthly Profit</CardTitle>
            {overview.total_profit >= 0 ? (
              <TrendingUp className="h-4 w-4 text-green-600" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-600" />
            )}
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${overview.total_profit >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(overview.total_profit)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Margin</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${marginColor(overview.avg_margin_pct, overview.target_margin_pct)}`}>
              {overview.avg_margin_pct.toFixed(1)}%
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
            <div className="text-2xl font-bold text-yellow-600">{overview.below_target_count}</div>
            <p className="text-xs text-muted-foreground">
              of {overview.total_accounts} accounts
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Whale Curve */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Whale Curve — Cumulative Profitability</CardTitle>
          </CardHeader>
          <CardContent>
            {whaleCurve.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={whaleCurve}>
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
                      const pt = whaleCurve.find((w) => w.rank === rank);
                      return pt ? pt.customer_name : `#${rank}`;
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="cumulative_profit_pct"
                    stroke="#2989BE"
                    strokeWidth={2}
                    dot={false}
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
                    formatter={(value, name) => {
                      const v = value as number;
                      if (name === "Revenue") return [formatCurrency(v), name];
                      if (name === "Margin") return [`${v.toFixed(1)}%`, name];
                      return [v.toFixed(1), "Difficulty"];
                    }}
                  />
                  <Scatter data={scatterData}>
                    {scatterData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={
                          entry.y >= overview.target_margin_pct
                            ? "#22c55e"
                            : entry.y >= 0
                            ? "#eab308"
                            : "#ef4444"
                        }
                      />
                    ))}
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

      {/* Account Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Accounts by Margin</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead>Address</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead className="text-right">Profit</TableHead>
                <TableHead className="text-right">Margin</TableHead>
                <TableHead className="text-right">Suggested</TableHead>
                <TableHead className="text-right">Difficulty</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {overview.accounts.map((account) => (
                <TableRow key={`${account.customer_id}-${account.property_id}`}>
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
        </CardContent>
      </Card>
    </div>
  );
}
