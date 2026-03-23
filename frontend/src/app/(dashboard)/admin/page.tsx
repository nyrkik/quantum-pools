"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { Loader2, Database, Clock, FileText, AlertTriangle, Link2, Search, Check, X } from "lucide-react";

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
  draft_response: string | null;
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
      await api.post("/v1/admin/emd-match", { facility_id: facility.id, property_id: propertyId });
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

export default function AdminPage() {
  const [runs, setRuns] = useState<ScraperRun[]>([]);
  const [stats, setStats] = useState<EmdStats | null>(null);
  const [unmatched, setUnmatched] = useState<UnmatchedFacility[]>([]);
  const [agentMsgs, setAgentMsgs] = useState<AgentMsg[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    Promise.all([
      api.get<ScraperRun[]>("/v1/admin/scraper-runs"),
      api.get<EmdStats>("/v1/admin/emd-stats"),
      api.get<UnmatchedFacility[]>("/v1/admin/emd-unmatched"),
      api.get<AgentMsg[]>("/v1/admin/agent-messages").catch(() => []),
    ])
      .then(([r, s, u, a]) => { setRuns(r); setStats(s); setUnmatched(u); setAgentMsgs(a); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Admin Dashboard</h1>

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
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Unmatched EMD Facilities ({unmatched.length})</CardTitle>
            </div>
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

      {/* Agent Message Log */}
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

      {/* Scraper Run History */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">EMD Scraper Runs</CardTitle>
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
    </div>
  );
}
