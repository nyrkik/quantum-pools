"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { toast } from "sonner";
import {
  Loader2,
  Settings,
  Settings2,
  Calculator,
  Building2,
  Home,
} from "lucide-react";
import type {
  ProfitabilityOverview,
} from "@/types/profitability";

import { usePermissions } from "@/lib/permissions";
import { CostSettingsSheet } from "@/components/profitability/cost-settings-sheet";
import { PageLayout } from "@/components/layout/page-layout";
import { SummaryCards } from "@/components/profitability/summary-cards";
import { WhaleCurveChart } from "@/components/profitability/whale-curve-chart";
import { ScatterQuadrantChart } from "@/components/profitability/scatter-quadrant-chart";
import type { ScatterPoint } from "@/components/profitability/scatter-quadrant-chart";
import { AccountTable } from "@/components/profitability/account-table";
import { WfGapsTable } from "@/components/profitability/wf-gaps-table";

export default function ProfitabilityPage() {
  const perms = usePermissions();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [overview, setOverview] = useState<ProfitabilityOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [tableView, setTableView] = useState<"account" | "wf">("account");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<string>("margin");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [wfGaps, setBowGaps] = useState<any[] | null>(null);

  const loadWfGaps = useCallback(() => {
    if (wfGaps !== null) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    api.get<any[]>("/v1/profitability/gaps")
      .then(setBowGaps)
      .catch(() => setBowGaps([]));
  }, [wfGaps]);

  const loadData = useCallback(async () => {
    try {
      const ov = await api.get<ProfitabilityOverview>("/v1/profitability/overview");
      setOverview(ov);
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

  const filteredAccounts = overview.accounts.filter(a => typeFilter === null || a.customer_type === typeFilter);

  const filteredWhale = (() => {
    const sorted = [...filteredAccounts].sort((a, b) => b.cost_breakdown.profit - a.cost_breakdown.profit);
    const totalProfit = sorted.reduce((s, a) => s + a.cost_breakdown.profit, 0);
    let cumulative = 0;
    return sorted.map((a, i) => {
      cumulative += a.cost_breakdown.profit;
      return { rank: i + 1, customer_name: a.customer_name, customer_id: a.customer_id, cumulative_profit_pct: totalProfit !== 0 ? (cumulative / Math.abs(totalProfit) * 100) : 0, individual_profit: a.cost_breakdown.profit };
    });
  })();

  const scatterData: ScatterPoint[] = filteredAccounts
    .filter(a => a.estimated_service_minutes > 0 && a.monthly_rate > 0)
    .map((a) => {
      const visitsPerMonth = 4.33;
      const hoursPerMonth = (a.estimated_service_minutes * visitsPerMonth) / 60;
      return {
        x: Math.round(a.monthly_rate / hoursPerMonth),
        y: a.margin_pct,
        z: a.difficulty_score,
        name: a.customer_name,
        id: a.customer_id,
        rate: a.monthly_rate,
        minutes: a.estimated_service_minutes,
      };
    });

  const fRev = filteredAccounts.reduce((s, a) => s + a.cost_breakdown.revenue, 0);
  const fCost = filteredAccounts.reduce((s, a) => s + a.cost_breakdown.total_cost, 0);
  const fBelow = filteredAccounts.filter(a => a.margin_pct < overview.target_margin_pct).length;

  const handleSort = (col: string) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  };

  return (
    <PageLayout
      title="Profitability Analysis"
      subtitle={`${filteredAccounts.length} of ${overview.total_accounts} accounts`}
      action={
        <div className="flex gap-2 items-center">
          {perms.can("profitability.edit_settings") && (
            <Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)}>
              <Settings2 className="h-4 w-4" />
            </Button>
          )}
          <div className="flex gap-1">
            {([
              { value: "commercial", label: "Commercial", icon: Building2 },
              { value: "residential", label: "Residential", icon: Home },
            ] as const).map((t) => (
              <Button key={t.value} variant={typeFilter === t.value ? "default" : "outline"} size="sm" className="h-8 text-xs" onClick={() => setTypeFilter(prev => prev === t.value ? null : t.value)}>
                <t.icon className="h-3.5 w-3.5 mr-1" />{t.label}
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
      }
    >
      <SummaryCards
        revenue={fRev}
        cost={fCost}
        targetMarginPct={overview.target_margin_pct}
        belowTargetCount={fBelow}
        totalAccounts={filteredAccounts.length}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <WhaleCurveChart data={filteredWhale} hoveredId={hoveredId} />
        <ScatterQuadrantChart data={scatterData} targetMarginPct={overview.target_margin_pct} hoveredId={hoveredId} />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Margin Analysis</CardTitle>
            <div className="flex gap-1">
              <Button variant={tableView === "account" ? "default" : "outline"} size="sm" className="h-7 text-xs" onClick={() => setTableView("account")}>By Account</Button>
              <Button variant={tableView === "wf" ? "default" : "outline"} size="sm" className="h-7 text-xs" onClick={() => { setTableView("wf"); loadWfGaps(); }}>By Water Feature</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {tableView === "account" ? (
            <AccountTable
              accounts={filteredAccounts}
              targetMarginPct={overview.target_margin_pct}
              sortCol={sortCol}
              sortDir={sortDir}
              onSort={handleSort}
              hoveredId={hoveredId}
              onHover={setHoveredId}
            />
          ) : wfGaps === null ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <WfGapsTable
              gaps={wfGaps.filter((g: Record<string, unknown>) => typeFilter === null || g.customer_type === typeFilter)}
              targetMarginPct={overview.target_margin_pct}
              sortCol={sortCol}
              sortDir={sortDir}
              onSort={handleSort}
              hoveredId={hoveredId}
              onHover={setHoveredId}
            />
          )}
        </CardContent>
      </Card>

      <CostSettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </PageLayout>
  );
}
