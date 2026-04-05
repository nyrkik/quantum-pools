"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { PageLayout } from "@/components/layout/page-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, Sparkles, TrendingUp, TrendingDown } from "lucide-react";

interface UsageStats {
  current_month: {
    input_tokens: number;
    output_tokens: number;
    message_count: number;
    off_topic_count: number;
    estimated_cost_usd: number;
  };
  previous_month: {
    input_tokens: number;
    output_tokens: number;
    message_count: number;
    estimated_cost_usd: number;
  };
  limits: {
    user_daily_input: number;
    user_daily_output: number;
    user_monthly_input: number;
    user_monthly_output: number;
    org_monthly_input: number;
    org_monthly_output: number;
    rate_limit_per_minute: number;
  };
  users: {
    user_id: string;
    name: string;
    message_count: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
    off_topic_count: number;
    off_topic_pct: number;
    last_active: string | null;
  }[];
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
}

export default function DeepBlueUsagePage() {
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<UsageStats>("/v1/deepblue/usage-stats")
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <PageLayout title="DeepBlue Usage">
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </PageLayout>
    );
  }

  if (!stats) {
    return <PageLayout title="DeepBlue Usage"><p>No data.</p></PageLayout>;
  }

  const { current_month: cur, previous_month: prev, limits, users } = stats;
  const orgInputUsagePct = (cur.input_tokens / limits.org_monthly_input) * 100;
  const orgOutputUsagePct = (cur.output_tokens / limits.org_monthly_output) * 100;
  const costChange = prev.estimated_cost_usd > 0
    ? ((cur.estimated_cost_usd - prev.estimated_cost_usd) / prev.estimated_cost_usd) * 100
    : 0;

  // Compute org averages for anomaly highlighting
  const avgUserTokens = users.length > 0
    ? users.reduce((sum, u) => sum + u.input_tokens + u.output_tokens, 0) / users.length
    : 0;

  return (
    <PageLayout title="DeepBlue Usage">
      <div className="space-y-4">
        {/* Current month summary */}
        <div className="grid gap-3 md:grid-cols-4">
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Messages</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{cur.message_count.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground">this month</p>
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Input Tokens</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{formatNumber(cur.input_tokens)}</p>
              <div className="w-full bg-muted rounded-full h-1 mt-2">
                <div
                  className={`h-1 rounded-full ${orgInputUsagePct > 80 ? "bg-red-500" : orgInputUsagePct > 50 ? "bg-amber-500" : "bg-green-500"}`}
                  style={{ width: `${Math.min(100, orgInputUsagePct)}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">{orgInputUsagePct.toFixed(1)}% of org limit</p>
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Output Tokens</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{formatNumber(cur.output_tokens)}</p>
              <div className="w-full bg-muted rounded-full h-1 mt-2">
                <div
                  className={`h-1 rounded-full ${orgOutputUsagePct > 80 ? "bg-red-500" : orgOutputUsagePct > 50 ? "bg-amber-500" : "bg-green-500"}`}
                  style={{ width: `${Math.min(100, orgOutputUsagePct)}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">{orgOutputUsagePct.toFixed(1)}% of org limit</p>
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Estimated Cost</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">${cur.estimated_cost_usd.toFixed(2)}</p>
              {prev.estimated_cost_usd > 0 && (
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  {costChange >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                  {Math.abs(costChange).toFixed(0)}% vs last month (${prev.estimated_cost_usd.toFixed(2)})
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Per-user breakdown */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              Usage by User
            </CardTitle>
          </CardHeader>
          <CardContent>
            {users.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">No usage this month yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-100 dark:bg-slate-800 text-xs font-medium uppercase tracking-wide">
                      <th className="text-left px-3 py-2">User</th>
                      <th className="text-right px-3 py-2">Messages</th>
                      <th className="text-right px-3 py-2">Tokens In</th>
                      <th className="text-right px-3 py-2">Tokens Out</th>
                      <th className="text-right px-3 py-2">Cost</th>
                      <th className="text-right px-3 py-2">Off-topic</th>
                      <th className="text-left px-3 py-2">Last Active</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => {
                      const totalTokens = u.input_tokens + u.output_tokens;
                      const isOutlier = avgUserTokens > 0 && totalTokens > avgUserTokens * 3;
                      const isOffTopicHeavy = u.off_topic_pct > 20;
                      return (
                        <tr key={u.user_id} className={`border-b hover:bg-blue-50 dark:hover:bg-blue-950 ${isOutlier ? "bg-red-50/50" : ""}`}>
                          <td className="px-3 py-2 font-medium">
                            {u.name}
                            {isOutlier && <Badge variant="destructive" className="ml-2 text-[10px]">Outlier</Badge>}
                          </td>
                          <td className="text-right px-3 py-2">{u.message_count}</td>
                          <td className="text-right px-3 py-2">{formatNumber(u.input_tokens)}</td>
                          <td className="text-right px-3 py-2">{formatNumber(u.output_tokens)}</td>
                          <td className="text-right px-3 py-2">${u.estimated_cost_usd.toFixed(2)}</td>
                          <td className="text-right px-3 py-2">
                            <span className={isOffTopicHeavy ? "text-amber-600 font-medium" : ""}>
                              {u.off_topic_count} ({u.off_topic_pct}%)
                            </span>
                          </td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">
                            {u.last_active ? new Date(u.last_active).toLocaleDateString() : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Limits */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Current Limits</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 md:grid-cols-2 text-sm">
              <div><span className="text-muted-foreground">Daily per user (input):</span> {formatNumber(limits.user_daily_input)}</div>
              <div><span className="text-muted-foreground">Daily per user (output):</span> {formatNumber(limits.user_daily_output)}</div>
              <div><span className="text-muted-foreground">Monthly per user (input):</span> {formatNumber(limits.user_monthly_input)}</div>
              <div><span className="text-muted-foreground">Monthly per user (output):</span> {formatNumber(limits.user_monthly_output)}</div>
              <div><span className="text-muted-foreground">Monthly org (input):</span> {formatNumber(limits.org_monthly_input)}</div>
              <div><span className="text-muted-foreground">Monthly org (output):</span> {formatNumber(limits.org_monthly_output)}</div>
              <div><span className="text-muted-foreground">Rate limit:</span> {limits.rate_limit_per_minute} messages/min</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
