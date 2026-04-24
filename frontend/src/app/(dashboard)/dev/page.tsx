"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import {
  Loader2, Activity, Check, DollarSign, Zap, Bot, AlertTriangle, Play, Code2, Database, Sparkles,
  FileText, Clock, Link2, Search, X, HelpCircle, ChevronDown, ChevronUp,
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
  id?: string;
  prompt_key?: string;
  prompt: string;
  tools_called?: string[];
  text_response?: string;
  passed: boolean;
  reason: string;
  source?: string;
  max_turns?: number;
}

interface EvalRunSummary {
  id: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  model_used: string | null;
  system_prompt_hash: string | null;
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_cost_usd?: number;
  duration_seconds?: number | null;
  created_at: string;
}

interface ScraperRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  days_scraped: number;
  inspections_found: number;
  inspections_new: number;
  pdfs_downloaded: number;
  errors: string | null;
  duration_seconds: number | null;
  email_sent: boolean;
}

interface EmdStats {
  facilities: number;
  inspections: number;
  violations: number;
  latest_inspection_date: string | null;
  last_successful_run: string | null;
  matched: number;
  unmatched: number;
}

interface UnmatchedFacility {
  id: string;
  name: string;
  street_address: string;
  city: string;
  facility_type: string | null;
  inspections: number;
}

interface PropertyOption {
  property_id: string;
  address: string;
  customer_name: string;
  emd_fa_number: string | null;
}

interface AgentMsg {
  id: string;
  direction: string;
  from_email: string;
  subject: string | null;
  category: string | null;
  urgency: string | null;
  status: string;
  customer_name: string | null;
  received_at: string | null;
  sent_at: string | null;
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function MatchRow({ facility, onMatched }: { facility: UnmatchedFacility; onMatched: () => void }) {
  const [matching, setMatching] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<PropertyOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return; }
    setSearching(true);
    try {
      const data = await api.get<PropertyOption[]>(`/v1/admin/properties-for-match?search=${encodeURIComponent(q)}`);
      setResults(data);
    } catch { setResults([]); }
    finally { setSearching(false); }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => doSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search, doSearch]);

  const handleMatch = async (propertyId: string) => {
    setSaving(true);
    try {
      await api.post("/v1/admin/inspection-match", { facility_id: facility.id, property_id: propertyId });
      toast.success(`Matched ${facility.name}`);
      setMatching(false);
      onMatched();
    } catch {
      toast.error("Failed to match");
    } finally { setSaving(false); }
  };

  if (!matching) {
    return (
      <TableRow>
        <TableCell className="text-sm font-medium">{facility.name}</TableCell>
        <TableCell className="text-sm text-muted-foreground">{facility.street_address}, {facility.city}</TableCell>
        <TableCell className="text-sm text-right">{facility.inspections}</TableCell>
        <TableCell>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setMatching(true)}>
            <Link2 className="h-3 w-3 mr-1" />Match
          </Button>
        </TableCell>
      </TableRow>
    );
  }

  return (
    <>
      <TableRow className="bg-primary/5">
        <TableCell className="text-sm font-medium">{facility.name}</TableCell>
        <TableCell className="text-sm text-muted-foreground">{facility.street_address}, {facility.city}</TableCell>
        <TableCell className="text-sm text-right">{facility.inspections}</TableCell>
        <TableCell>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setMatching(false)}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </TableCell>
      </TableRow>
      <TableRow className="bg-primary/5">
        <TableCell colSpan={4} className="pt-0">
          <div className="flex items-center gap-2 mb-2">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search properties by address or client name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 text-sm"
              autoFocus
            />
            {searching && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          </div>
          {results.length > 0 && (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {results.map((p) => (
                <div key={p.property_id} className="flex items-center justify-between px-2 py-1.5 rounded hover:bg-muted/50 text-sm">
                  <div>
                    <span className="font-medium">{p.customer_name}</span>
                    <span className="text-muted-foreground ml-2">{p.address}</span>
                  </div>
                  <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-green-600" onClick={() => handleMatch(p.property_id)} disabled={saving}>
                    {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              ))}
            </div>
          )}
          {search && !searching && results.length === 0 && (
            <p className="text-xs text-muted-foreground py-2">No matching properties found</p>
          )}
        </TableCell>
      </TableRow>
    </>
  );
}

export default function DevPage() {
  const { isDeveloper } = useAuth();
  const router = useRouter();
  const [agentMetrics, setAgentMetrics] = useState<AgentMetrics | null>(null);
  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([]);
  const [runs, setRuns] = useState<ScraperRun[]>([]);
  const [stats, setStats] = useState<EmdStats | null>(null);
  const [unmatched, setUnmatched] = useState<UnmatchedFacility[]>([]);
  const [agentMsgs, setAgentMsgs] = useState<AgentMsg[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningHealthCheck, setRunningHealthCheck] = useState(false);
  const [runningEval, setRunningEval] = useState(false);
  const [evalResults, setEvalResults] = useState<{ total: number; passed: number; failed: number; skipped?: number; results: EvalResult[]; total_cost_usd?: number; total_input_tokens?: number; total_output_tokens?: number; duration_seconds?: number } | null>(null);
  const [evalHistory, setEvalHistory] = useState<EvalRunSummary[]>([]);

  const loadEvalHistory = useCallback(async () => {
    try {
      const data = await api.get<{ runs: EvalRunSummary[] }>("/v1/deepblue/eval-runs?limit=10");
      setEvalHistory(data.runs);
    } catch {}
  }, []);

  useEffect(() => { if (isDeveloper) loadEvalHistory(); }, [isDeveloper, loadEvalHistory]);

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
      api.get<ScraperRun[]>("/v1/admin/scraper-runs"),
      api.get<EmdStats>("/v1/admin/inspection-stats"),
      api.get<UnmatchedFacility[]>("/v1/admin/inspection-unmatched"),
      api.get<AgentMsg[]>("/v1/admin/agent-messages"),
    ]).then(([m, l, r, s, u, a]) => {
      if (m.status === "fulfilled") setAgentMetrics(m.value as AgentMetrics);
      if (l.status === "fulfilled") setAgentLogs((l.value || []) as AgentLogEntry[]);
      if (r.status === "fulfilled") setRuns((r.value || []) as ScraperRun[]);
      if (s.status === "fulfilled") setStats(s.value as EmdStats);
      if (u.status === "fulfilled") setUnmatched((u.value || []) as UnmatchedFacility[]);
      if (a.status === "fulfilled") setAgentMsgs((a.value || []) as AgentMsg[]);
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

  const runEval = async (mode: "full" | "smart" = "full") => {
    setRunningEval(true);
    setEvalResults(null);
    try {
      const result = await api.post<{ id: string; total: number; passed: number; failed: number; skipped?: number; results: EvalResult[] }>(
        `/v1/deepblue/eval-run?mode=${mode}`, {},
      );
      setEvalResults(result);
      const skippedNote = result.skipped ? ` (${result.skipped} skipped)` : "";
      toast.success(`Eval: ${result.passed}/${result.total} passed${skippedNote}`);
      loadEvalHistory();
    } catch {
      toast.error("Eval run failed");
    } finally {
      setRunningEval(false);
    }
  };

  const [generatingPrompts, setGeneratingPrompts] = useState(false);
  const [draftPrompts, setDraftPrompts] = useState<{ prompt: string; expected_tools_any: string[]; max_turns: number; reasoning: string }[]>([]);
  const [showEvalHelp, setShowEvalHelp] = useState(false);
  const [showHealthHelp, setShowHealthHelp] = useState(false);

  const generatePrompts = async () => {
    setGeneratingPrompts(true);
    setDraftPrompts([]);
    try {
      const result = await api.post<{ drafts: typeof draftPrompts }>("/v1/deepblue/eval-prompts/generate", { count: 5 });
      setDraftPrompts(result.drafts || []);
      toast.success(`Generated ${result.drafts?.length || 0} draft prompts`);
    } catch {
      toast.error("Generation failed");
    } finally {
      setGeneratingPrompts(false);
    }
  };

  const approveDraft = async (draft: typeof draftPrompts[0]) => {
    try {
      await api.post("/v1/deepblue/eval-prompts/approve-draft", {
        prompt_text: draft.prompt,
        expected_tools_any: draft.expected_tools_any,
        max_turns: draft.max_turns,
        reasoning: draft.reasoning,
      });
      toast.success("Added to eval suite");
      setDraftPrompts(draftPrompts.filter((d) => d.prompt !== draft.prompt));
    } catch {
      toast.error("Failed to add");
    }
  };

  const loadEvalRun = async (runId: string) => {
    try {
      const data = await api.get<{ total: number; passed: number; failed: number; results: EvalResult[] }>(
        `/v1/deepblue/eval-runs/${runId}`,
      );
      setEvalResults(data);
    } catch {
      toast.error("Failed to load run");
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
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowHealthHelp(!showHealthHelp)} title="Help">
                  <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
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
            {showHealthHelp && (
              <div className="bg-muted/50 rounded-md p-3 text-xs space-y-2 border">
                <p className="font-medium text-sm">What this shows</p>
                <p className="text-muted-foreground">
                  Metrics from every AI agent call across the system (DeepBlue, email classifier, customer matcher, etc.) over the last 24 hours. Source: <code className="bg-background px-1 rounded">agent_logs</code> table.
                </p>

                <p className="font-medium pt-2">Summary tiles</p>
                <ul className="space-y-1.5 text-muted-foreground list-disc pl-4">
                  <li><span className="font-medium text-foreground">Calls</span> — total agent invocations (each is one Claude call)</li>
                  <li><span className="font-medium text-foreground">Success Rate</span> — percent that completed without errors. Turns red below 90%.</li>
                  <li><span className="font-medium text-foreground">Cost</span> — total spend for the 24h window based on model pricing</li>
                  <li><span className="font-medium text-foreground">Avg Speed</span> — average end-to-end latency per call</li>
                </ul>

                <p className="font-medium pt-2">Run Health Check button</p>
                <p className="text-muted-foreground">
                  Evaluates the last 24 hours against thresholds:
                </p>
                <ul className="space-y-1 text-muted-foreground list-disc pl-4">
                  <li>Success rate below 90% → alert</li>
                  <li>Any agent with 3+ failures in the last hour → alert</li>
                  <li>10+ total failures org-wide in the last hour → critical alert</li>
                </ul>
                <p className="text-muted-foreground">
                  Violations create in-app notifications for owners and admins with a 60-minute dedup window (safe to click repeatedly). Manual trigger for now; future: daily cron.
                </p>

                <p className="font-medium pt-2">Per-agent breakdown</p>
                <p className="text-muted-foreground">
                  Shows which agents are doing the most work and costing the most. Sorted by call count descending.
                </p>

                <p className="font-medium pt-2">Recent Failures</p>
                <p className="text-muted-foreground">
                  Last 8 errors with timestamp and error message. Use these to spot patterns — repeated errors from the same agent usually point to a model or prompt issue.
                </p>
              </div>
            )}
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
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowEvalHelp(!showEvalHelp)} title="Help">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={() => runEval("smart")}
                disabled={runningEval}
                title="Skip tests that have passed 5+ consecutive runs within 7 days"
              >
                {runningEval ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                Smart
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={() => runEval("full")}
                disabled={runningEval}
                title="Run all active tests"
              >
                {runningEval ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                Full
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={generatePrompts}
                disabled={generatingPrompts}
                title="Generate new adversarial prompts via Claude"
              >
                {generatingPrompts ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                Generate
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {showEvalHelp && (
            <div className="bg-muted/50 rounded-md p-3 text-xs space-y-2 border">
              <p className="font-medium text-sm">What this does</p>
              <p className="text-muted-foreground">
                Runs a suite of test prompts against DeepBlue to verify it picks the right tools. Each test has an expected tool call (or set of allowed tools), and the runner checks if DeepBlue&apos;s actual behavior matches.
              </p>

              <p className="font-medium pt-2">Three buttons, three modes</p>
              <ul className="space-y-1.5 text-muted-foreground list-disc pl-4">
                <li>
                  <span className="font-medium text-foreground">Smart</span> — Skips tests that have passed 5+ times in a row and were checked within the last 7 days. Use this for routine runs — fast, focuses on unstable or new tests.
                </li>
                <li>
                  <span className="font-medium text-foreground">Full</span> — Runs every active test. Use after big changes (system prompt, new tools, Claude model update) to catch regressions.
                </li>
                <li>
                  <span className="font-medium text-foreground">Generate</span> — Asks Claude (Sonnet) to write 5 new adversarial test prompts based on the current tool list, recent failures, and unresolved knowledge gaps. Drafts appear below for review — click &quot;Add&quot; to activate, &quot;Skip&quot; to discard. Nothing auto-activates.
                </li>
              </ul>

              <p className="font-medium pt-2">How prompts grow over time</p>
              <ul className="space-y-1.5 text-muted-foreground list-disc pl-4">
                <li><span className="font-medium text-foreground">Static seeds</span> — 15 hand-written prompts seeded on first run (baseline regression tests)</li>
                <li><span className="font-medium text-foreground">Knowledge gaps</span> — real user questions DeepBlue couldn&apos;t answer get promoted from the Knowledge Gaps page into the suite</li>
                <li><span className="font-medium text-foreground">AI-generated</span> — Sonnet drafts new adversarial cases based on what&apos;s already covered and what&apos;s failing</li>
              </ul>

              <p className="font-medium pt-2">Multi-turn tests</p>
              <p className="text-muted-foreground">
                Some prompts need multiple tool calls across turns (e.g., &quot;add equipment to Walili pool&quot; requires finding the property first, then adding equipment). These have <code className="bg-background px-1 rounded">max_turns &gt; 1</code> and the runner executes tools and feeds results back until done or max reached.
              </p>

              <p className="font-medium pt-2">Safety</p>
              <p className="text-muted-foreground">
                Write tools (add_equipment, log_reading, update_note) return preview responses only — the eval runner never writes to the DB. Reads hit real data.
              </p>

              <p className="font-medium pt-2">Pass rate colors</p>
              <p className="text-muted-foreground">
                <span className="text-green-600 font-medium">Green ≥90%</span> · <span className="text-amber-600 font-medium">Amber 75-89%</span> · <span className="text-red-600 font-medium">Red &lt;75%</span>
              </p>
            </div>
          )}

          {!evalResults ? (
            <p className="text-sm text-muted-foreground">Tests DeepBlue&apos;s tool selection on a growing corpus of prompts. Click the help icon above for details.</p>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold">{evalResults.passed}/{evalResults.total}</span>
                  <span className="text-sm text-muted-foreground">passed</span>
                  {evalResults.failed > 0 && (
                    <span className="text-xs text-red-600">{evalResults.failed} failed</span>
                  )}
                </div>
                {(evalResults.total_cost_usd !== undefined || evalResults.duration_seconds !== undefined) && (
                  <div className="text-xs text-muted-foreground text-right">
                    {evalResults.total_cost_usd !== undefined && (
                      <div className="font-mono">${evalResults.total_cost_usd.toFixed(4)}</div>
                    )}
                    {evalResults.duration_seconds !== undefined && evalResults.duration_seconds !== null && (
                      <div>{evalResults.duration_seconds.toFixed(1)}s</div>
                    )}
                  </div>
                )}
              </div>
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {evalResults.results.map((r, i) => (
                  <div key={r.prompt_key || r.id || i} className={`rounded p-2 text-xs ${r.passed ? "bg-green-50 dark:bg-green-950/20" : "bg-red-50 dark:bg-red-950/20"}`}>
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

          {/* Draft prompts awaiting review */}
          {draftPrompts.length > 0 && (
            <div className="pt-3 border-t">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">
                Drafts — review before adding ({draftPrompts.length})
              </p>
              <div className="space-y-2">
                {draftPrompts.map((d, i) => (
                  <div key={i} className="bg-muted/50 rounded p-2 text-xs space-y-1">
                    <p className="font-medium">{d.prompt}</p>
                    {d.reasoning && <p className="text-[10px] text-muted-foreground italic">{d.reasoning}</p>}
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-muted-foreground">
                        {d.expected_tools_any.length > 0 ? `Expects: ${d.expected_tools_any.join(", ")}` : "No tool expectation"}
                        {d.max_turns > 1 && ` · ${d.max_turns} turns`}
                      </span>
                      <div className="flex gap-1">
                        <Button size="sm" variant="outline" className="h-6 text-[10px]" onClick={() => approveDraft(d)}>
                          <Check className="h-2.5 w-2.5 mr-0.5" /> Add
                        </Button>
                        <Button size="sm" variant="ghost" className="h-6 text-[10px]" onClick={() => setDraftPrompts(draftPrompts.filter((_, j) => j !== i))}>
                          Skip
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* History of past runs */}
          {evalHistory.length > 0 && (
            <div className="pt-3 border-t">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">Recent runs</p>
              <div className="space-y-1">
                {evalHistory.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => loadEvalRun(r.id)}
                    className="w-full flex items-center justify-between p-2 rounded hover:bg-muted/50 text-xs text-left"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`font-mono font-medium ${r.pass_rate >= 90 ? "text-green-600" : r.pass_rate >= 75 ? "text-amber-600" : "text-red-600"}`}>
                        {r.passed}/{r.total}
                      </span>
                      <span className="text-muted-foreground">({r.pass_rate}%)</span>
                      {r.total_cost_usd !== undefined && r.total_cost_usd > 0 && (
                        <span className="font-mono text-muted-foreground">${r.total_cost_usd.toFixed(4)}</span>
                      )}
                      {r.duration_seconds !== undefined && r.duration_seconds !== null && r.duration_seconds > 0 && (
                        <span className="text-muted-foreground">{r.duration_seconds.toFixed(0)}s</span>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      {new Date(r.created_at).toLocaleString()}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* EMD Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          <Card className="shadow-sm py-4 gap-2">
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Facilities</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.facilities.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground">{stats.matched} matched · {stats.unmatched} unmatched</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm py-4 gap-2">
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Inspections</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.inspections.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm py-4 gap-2">
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Violations</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.violations.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm py-4 gap-2">
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Latest</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-bold">{stats.latest_inspection_date || "—"}</p>
            </CardContent>
          </Card>
          <Card className="shadow-sm py-4 gap-2">
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Last Run</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-bold">{stats.last_successful_run ? formatDate(stats.last_successful_run) : "—"}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Unmatched Facilities */}
      {unmatched.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Unmatched Facilities ({unmatched.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-100 dark:bg-slate-800">
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Facility</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Address</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Inspections</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide w-24"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {unmatched.map((f) => (
                    <MatchRow key={f.id} facility={f} onMatched={load} />
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Customer Agent Activity */}
      {agentMsgs.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Customer Agent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-100 dark:bg-slate-800">
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Time</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">From</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Subject</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Category</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agentMsgs.map((m, i) => (
                    <TableRow key={m.id} className={`${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                      <TableCell className="text-sm">{formatDate(m.received_at)}</TableCell>
                      <TableCell className="text-sm">{m.customer_name || m.from_email}</TableCell>
                      <TableCell className="text-sm text-muted-foreground truncate max-w-48">{m.subject}</TableCell>
                      <TableCell>
                        {m.category && <Badge variant="outline" className="text-xs capitalize">{m.category}</Badge>}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={m.status === "sent" || m.status === "auto_sent" ? "default" : m.status === "pending" ? "outline" : "secondary"}
                          className={m.status === "sent" || m.status === "auto_sent" ? "bg-green-600" : m.status === "pending" ? "border-amber-400 text-amber-600" : ""}
                        >
                          {m.status === "auto_sent" ? "auto" : m.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Inspection Scraper Run History */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Inspection Scraper Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No scraper runs recorded yet</p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-100 dark:bg-slate-800">
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Time</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Found</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide text-right">New</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide text-right">PDFs</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Duration</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Email</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run, i) => (
                    <TableRow key={run.id} className={`${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                      <TableCell className="text-sm">{formatDate(run.started_at)}</TableCell>
                      <TableCell>
                        <Badge variant={run.status === "success" ? "default" : "destructive"} className={run.status === "success" ? "bg-green-600" : ""}>
                          {run.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right text-sm">{run.inspections_found}</TableCell>
                      <TableCell className="text-right text-sm font-medium">{run.inspections_new}</TableCell>
                      <TableCell className="text-right text-sm">{run.pdfs_downloaded}</TableCell>
                      <TableCell className="text-right text-sm text-muted-foreground">
                        {run.duration_seconds ? `${run.duration_seconds.toFixed(0)}s` : "—"}
                      </TableCell>
                      <TableCell>
                        {run.email_sent ? <span className="text-green-600 text-xs">Sent</span> : <span className="text-muted-foreground text-xs">—</span>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
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
        </CardContent>
      </Card>
    </div>
  );
}
