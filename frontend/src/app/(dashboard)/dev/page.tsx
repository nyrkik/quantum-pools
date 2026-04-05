"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import {
  Loader2, Activity, Check, DollarSign, Zap, Bot, AlertTriangle, Play, Code2, Database, Sparkles,
} from "lucide-react";

interface AgentMetrics {
  total_calls: number;
  failures: number;
  success_rate: number;
  total_cost_usd: number;
  avg_duration_ms: number | null;
  by_agent: Record<string, { calls: number; cost: number }>;
}

interface AgentLogEntry {
  id: string;
  agent_name: string;
  action: string;
  success: boolean;
  error: string | null;
  model: string | null;
  cost_usd: number | null;
  duration_ms: number | null;
  created_at: string;
}

interface EvalResult {
  id: string;
  prompt: string;
  tools_called?: string[];
  text_response?: string;
  passed: boolean;
  reason: string;
}

export default function DevPage() {
  const { isDeveloper } = useAuth();
  const router = useRouter();
  const [agentMetrics, setAgentMetrics] = useState<AgentMetrics | null>(null);
  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningHealthCheck, setRunningHealthCheck] = useState(false);
  const [runningEval, setRunningEval] = useState(false);
  const [evalResults, setEvalResults] = useState<{ total: number; passed: number; failed: number; results: EvalResult[] } | null>(null);

  useEffect(() => {
    if (!isDeveloper) {
      router.push("/dashboard");
    }
  }, [isDeveloper, router]);

  const load = useCallback(() => {
    setLoading(true);
    Promise.allSettled([
      api.get<AgentMetrics>("/v1/agent-ops/metrics"),
      api.get<AgentLogEntry[]>("/v1/agent-ops/logs?limit=20&success_only=false"),
    ]).then(([m, l]) => {
      if (m.status === "fulfilled") setAgentMetrics(m.value as AgentMetrics);
      if (l.status === "fulfilled") setAgentLogs((l.value || []) as AgentLogEntry[]);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { if (isDeveloper) load(); }, [load, isDeveloper]);

  const runHealthCheck = async () => {
    setRunningHealthCheck(true);
    try {
      const result = await api.post<{ issues: { title: string; severity: string }[]; notifications_created: number }>(
        "/v1/agent-ops/health-check",
        {},
      );
      const count = result.issues.length;
      if (count === 0) {
        toast.success("Health check passed — no issues");
      } else {
        const critical = result.issues.filter((i) => i.severity === "critical").length;
        toast.warning(`${count} ${critical > 0 ? "critical" : ""} issue${count !== 1 ? "s" : ""} found`, {
          description: `${result.notifications_created} admin notification${result.notifications_created !== 1 ? "s" : ""} created`,
        });
      }
    } catch {
      toast.error("Health check failed");
    } finally {
      setRunningHealthCheck(false);
    }
  };

  const runEval = async () => {
    setRunningEval(true);
    setEvalResults(null);
    try {
      const result = await api.post<{ total: number; passed: number; failed: number; results: EvalResult[] }>(
        "/v1/deepblue/eval-run", {},
      );
      setEvalResults(result);
      toast.success(`Eval: ${result.passed}/${result.total} passed`);
    } catch {
      toast.error("Eval run failed");
    } finally {
      setRunningEval(false);
    }
  };

  if (!isDeveloper) return null;
  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  const failures = agentLogs.filter((l) => !l.success);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Code2 className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold">Dev Tools</h1>
      </div>

      {/* Agent Health — raw metrics */}
      {agentMetrics && (
        <Card className="shadow-sm">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-primary" />
                <CardTitle className="text-base">Agent Health (24h)</CardTitle>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={runHealthCheck}
                disabled={runningHealthCheck}
                title="Check thresholds and fire dev notifications if issues found"
              >
                {runningHealthCheck ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                Run Health Check
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-muted/50 rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <Activity className="h-3 w-3" />Calls
                </div>
                <p className="text-lg font-bold">{agentMetrics.total_calls}</p>
              </div>
              <div className={`rounded-md p-3 ${agentMetrics.success_rate < 90 ? "bg-red-50 dark:bg-red-950/20" : "bg-muted/50"}`}>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <Check className="h-3 w-3" />Success Rate
                </div>
                <p className={`text-lg font-bold ${agentMetrics.success_rate < 90 ? "text-red-600" : ""}`}>{agentMetrics.success_rate}%</p>
              </div>
              <div className="bg-muted/50 rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <DollarSign className="h-3 w-3" />Cost
                </div>
                <p className="text-lg font-bold">${agentMetrics.total_cost_usd.toFixed(2)}</p>
              </div>
              <div className="bg-muted/50 rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <Zap className="h-3 w-3" />Avg Speed
                </div>
                <p className="text-lg font-bold">{agentMetrics.avg_duration_ms ? `${(agentMetrics.avg_duration_ms / 1000).toFixed(1)}s` : "—"}</p>
              </div>
            </div>

            {Object.keys(agentMetrics.by_agent).length > 0 && (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-100 dark:bg-slate-800">
                      <TableHead className="text-xs font-medium uppercase tracking-wide">Agent</TableHead>
                      <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Calls</TableHead>
                      <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Cost</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(agentMetrics.by_agent)
                      .sort(([, a], [, b]) => b.calls - a.calls)
                      .map(([name, data]) => (
                        <TableRow key={name}>
                          <TableCell className="text-sm font-medium capitalize">{name.replace(/_/g, " ")}</TableCell>
                          <TableCell className="text-sm text-right">{data.calls}</TableCell>
                          <TableCell className="text-sm text-right text-muted-foreground">${data.cost.toFixed(4)}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {failures.length > 0 && (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-red-600 mb-2">
                  <AlertTriangle className="h-3 w-3 inline mr-1" />Recent Failures
                </p>
                <div className="space-y-1">
                  {failures.slice(0, 8).map((l) => (
                    <div key={l.id} className="bg-red-50 dark:bg-red-950/20 rounded p-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium capitalize">{l.agent_name.replace(/_/g, " ")}</span>
                        <span className="text-xs text-muted-foreground">{new Date(l.created_at).toLocaleTimeString()}</span>
                      </div>
                      <p className="text-xs text-red-600 truncate">{l.error || l.action}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* DeepBlue eval harness */}
      <Card className="shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">DeepBlue Eval Suite</CardTitle>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1.5"
              onClick={runEval}
              disabled={runningEval}
            >
              {runningEval ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
              Run Evals
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {!evalResults ? (
            <p className="text-sm text-muted-foreground">Tests DeepBlue's tool selection on ~15 common prompts.</p>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <span className="text-2xl font-bold">{evalResults.passed}/{evalResults.total}</span>
                <span className="text-sm text-muted-foreground">passed</span>
                {evalResults.failed > 0 && (
                  <span className="text-xs text-red-600">{evalResults.failed} failed</span>
                )}
              </div>
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {evalResults.results.map((r) => (
                  <div key={r.id} className={`rounded p-2 text-xs ${r.passed ? "bg-green-50 dark:bg-green-950/20" : "bg-red-50 dark:bg-red-950/20"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">{r.prompt}</span>
                      {r.passed ? <Check className="h-3 w-3 text-green-600 shrink-0" /> : <AlertTriangle className="h-3 w-3 text-red-600 shrink-0" />}
                    </div>
                    {r.tools_called && r.tools_called.length > 0 && (
                      <p className="text-[10px] text-muted-foreground mt-0.5">Tools: {r.tools_called.join(", ")}</p>
                    )}
                    {!r.passed && <p className="text-[10px] text-red-600 mt-0.5">{r.reason}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick links to related dev pages */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Database className="h-4 w-4 text-primary" />
            Related Dev Tools
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button variant="outline" className="w-full justify-start" onClick={() => router.push("/settings/deepblue-gaps")}>
            DeepBlue Knowledge Gaps — promote patterns to tools
          </Button>
          <Button variant="outline" className="w-full justify-start" onClick={() => router.push("/settings/deepblue-usage")}>
            DeepBlue Usage & Quotas — per-user spend
          </Button>
          <Button variant="outline" className="w-full justify-start" onClick={() => router.push("/admin")}>
            Admin Dashboard — business operations
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
