"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  MessageSquare,
  ClipboardList,
  FolderOpen,
  Mail,
  AlertTriangle,
  Clock,
  CheckCircle2,
  ArrowRight,
  Loader2,
  Play,
  CalendarCheck,
  FileText,
  Send,
  Sparkles,
} from "lucide-react";
import { formatTime, formatDueDate, isOverdue } from "@/lib/format";
import type { AgentAction, ServiceCase } from "@/types/agent";
import { CasesAnnouncement } from "@/components/layout/cases-announcement";
import { useDeepBlue } from "@/components/deepblue/deepblue-provider";
import { WorkflowSuggestionsWidget } from "@/components/workflow/WorkflowSuggestionsWidget";
import { AwaitingReplyWidget } from "@/components/dashboard/awaiting-reply-widget";

interface DashboardData {
  // My stuff
  unreadMessages: number;
  latestMessages: { id: string; participants: string[]; subject: string | null; last_message: string; last_message_at: string }[];
  myJobs: AgentAction[];
  todayVisits: number;
  activeVisit: { visit: { id: string; started_at: string }; customer: { name: string }; property: { address: string } } | null;
  // Needs attention
  pendingEmails: number;
  staleEmails: number;
  overdueJobs: number;
  pendingEstimates: number;
  draftEstimates: number;
  // Cases
  openCases: ServiceCase[];
  // Recent
  recentThreads: { id: string; customer_name: string; subject: string; last_message_at: string; status: string }[];
  recentDeepBlueChats: { id: string; title: string; message_count: number; updated_at: string }[];
}

export default function DashboardPage() {
  const { user } = useAuth();
  const perms = usePermissions();
  const router = useRouter();
  const { openDeepBlue, loadConversation } = useDeepBlue();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const resumeDeepBlueChat = async (id: string) => {
    await loadConversation(id);
    openDeepBlue();
  };

  useEffect(() => {
    (async () => {
      try {
        const d: DashboardData = {
          unreadMessages: 0, latestMessages: [], myJobs: [],
          todayVisits: 0, activeVisit: null,
          pendingEmails: 0, staleEmails: 0, overdueJobs: 0, pendingEstimates: 0, draftEstimates: 0,
          openCases: [], recentThreads: [], recentDeepBlueChats: [],
        };

        const results = await Promise.allSettled([
          // Messages
          api.get<{ unread: number }>("/v1/messages/stats"),
          api.get<{ items: DashboardData["latestMessages"] }>("/v1/messages?limit=3"),
          // My jobs
          api.get<AgentAction[]>(`/v1/admin/agent-actions?assigned_to=${user?.first_name}&status=open&limit=5`),
          api.get<AgentAction[]>("/v1/admin/agent-actions?status=open&limit=5"),
          // Visits
          api.get<{ total: number }>(`/v1/visits?scheduled_date=${new Date().toISOString().split("T")[0]}&limit=1`),
          api.get("/v1/visits/active").catch(() => null),
          // Inbox stats
          perms.canViewInbox ? api.get<{ pending: number; stale_pending: number; overdue_actions: number }>("/v1/admin/agent-threads/stats") : null,
          // Recent inbox
          perms.canViewInbox ? api.get<{ items: DashboardData["recentThreads"] }>("/v1/admin/agent-threads?limit=5") : null,
          // Estimate counts
          perms.canViewInvoices ? api.get<{ total: number }>("/v1/invoices?status=sent&limit=1") : null,
          perms.canViewInvoices ? api.get<{ total: number }>("/v1/invoices?status=draft&limit=1") : null,
          // Cases
          api.get<{ items: ServiceCase[] }>("/v1/cases?limit=5"),
          // DeepBlue recent chats
          api.get<{ conversations: DashboardData["recentDeepBlueChats"] }>("/v1/deepblue/conversations?scope=mine&limit=5"),
        ]);

        // Messages
        if (results[0].status === "fulfilled") d.unreadMessages = (results[0].value as { unread: number }).unread;
        if (results[1].status === "fulfilled") d.latestMessages = ((results[1].value as { items: DashboardData["latestMessages"] }).items || []);
        // Jobs — my assigned first, fall back to all open
        if (results[2].status === "fulfilled") d.myJobs = results[2].value as AgentAction[];
        if (d.myJobs.length === 0 && results[3].status === "fulfilled") d.myJobs = (results[3].value as AgentAction[]).slice(0, 5);
        // Visits
        if (results[4].status === "fulfilled") d.todayVisits = (results[4].value as { total: number }).total;
        if (results[5].status === "fulfilled" && results[5].value) d.activeVisit = results[5].value as DashboardData["activeVisit"];
        // Inbox
        if (results[6]?.status === "fulfilled" && results[6].value) {
          const stats = results[6].value as { pending: number; stale_pending: number; overdue_actions: number };
          d.pendingEmails = stats.pending;
          d.staleEmails = stats.stale_pending;
          d.overdueJobs = stats.overdue_actions;
        }
        if (results[7]?.status === "fulfilled" && results[7].value) {
          d.recentThreads = ((results[7].value as { items: DashboardData["recentThreads"] }).items || []);
        }
        if (results[8]?.status === "fulfilled" && results[8].value) {
          d.pendingEstimates = (results[8].value as { total: number }).total;
        }
        if (results[9]?.status === "fulfilled" && results[9].value) {
          d.draftEstimates = (results[9].value as { total: number }).total;
        }
        if (results[10]?.status === "fulfilled" && results[10].value) {
          d.openCases = ((results[10].value as { items: ServiceCase[] }).items || []).filter(c => c.status !== "closed" && c.status !== "cancelled");
        }
        if (results[11]?.status === "fulfilled" && results[11].value) {
          d.recentDeepBlueChats = ((results[11].value as { conversations: DashboardData["recentDeepBlueChats"] }).conversations || []);
        }

        setData(d);
      } catch {
        // defaults
      } finally {
        setLoading(false);
      }
    })();
  }, [user, perms.canViewInbox]);

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  // Recovery surface — without this the user lands on a silent blank
  // page when the parallel fetch chain errors. Same class of bug as
  // FB-53's thread-detail blank.
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
        <p className="text-sm">Couldn&apos;t load the dashboard.</p>
        <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  // Build "needs attention" items
  const alerts: { label: string; count: number; icon: React.ElementType; color: string; href: string }[] = [];
  if (data.pendingEmails > 0) alerts.push({ label: "Pending emails", count: data.pendingEmails, icon: Mail, color: "text-amber-600", href: "/inbox" });
  if (data.staleEmails > 0) alerts.push({ label: "Stale (30+ min)", count: data.staleEmails, icon: AlertTriangle, color: "text-red-600", href: "/inbox" });
  if (data.overdueJobs > 0) alerts.push({ label: "Overdue jobs", count: data.overdueJobs, icon: Clock, color: "text-red-600", href: "/jobs" });
  if (data.pendingEstimates > 0) alerts.push({ label: "Awaiting approval", count: data.pendingEstimates, icon: FileText, color: "text-purple-600", href: "/invoices?tab=estimates" });
  if (data.draftEstimates > 0) alerts.push({ label: "Draft estimates", count: data.draftEstimates, icon: FileText, color: "text-blue-600", href: "/invoices?tab=estimates" });

  return (
    <div className="space-y-4">
      <CasesAnnouncement />
      <div>
        <h1 className="text-xl font-bold">Good {getTimeOfDay()}, {user?.first_name}</h1>
        <p className="text-sm text-muted-foreground">
          {data.todayVisits > 0 ? `${data.todayVisits} visit${data.todayVisits > 1 ? "s" : ""} today` : "No visits scheduled today"}
          {data.openCases.length > 0 ? ` · ${data.openCases.length} open case${data.openCases.length > 1 ? "s" : ""}` : ""}
        </p>
      </div>

      {/* Awaiting customer reply (promise tracker) */}
      <AwaitingReplyWidget />

      {/* Phase 6: workflow_observer suggestions (no-op for users without workflow.review) */}
      <WorkflowSuggestionsWidget />

      {/* Active Visit Banner */}
      {data.activeVisit && (
        <Link href={`/visits/${data.activeVisit.visit.id}`}>
          <Card className="shadow-sm border-l-4 border-green-500 cursor-pointer hover:shadow-md transition-shadow">
            <CardContent className="flex items-center gap-4 py-3">
              <div className="rounded-full bg-green-100 dark:bg-green-950 p-2">
                <Play className="h-5 w-5 text-green-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold">Visit In Progress</p>
                <p className="text-xs text-muted-foreground truncate">
                  {data.activeVisit.customer.name} — {data.activeVisit.property.address}
                </p>
              </div>
              <Button size="sm" className="bg-green-600 hover:bg-green-700 shrink-0">Resume</Button>
            </CardContent>
          </Card>
        </Link>
      )}

      {/* Needs Attention */}
      {alerts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {alerts.map((a) => (
            <Link key={a.label} href={a.href}>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 hover:bg-muted transition-colors cursor-pointer">
                <a.icon className={`h-4 w-4 ${a.color}`} />
                <span className="text-sm font-medium">{a.count}</span>
                <span className="text-xs text-muted-foreground">{a.label}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Messages */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-blue-500" />
                <CardTitle className="text-sm font-semibold">Messages</CardTitle>
                {data.unreadMessages > 0 && (
                  <Badge variant="default" className="text-[10px] px-1.5">{data.unreadMessages}</Badge>
                )}
              </div>
              <Link href="/messages">
                <Button variant="ghost" size="sm" className="text-xs h-7">
                  View All <ArrowRight className="h-3 w-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {data.latestMessages.length === 0 ? (
              <p className="text-sm text-muted-foreground py-3">No messages</p>
            ) : (
              <div className="space-y-1">
                {data.latestMessages.map((m) => (
                  <Link key={m.id} href={`/messages?thread=${m.id}`}>
                    <div className="flex items-center gap-3 py-2 -mx-2 px-2 rounded hover:bg-muted/50 transition-colors cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{m.subject || m.participants?.join(", ") || "Message"}</p>
                        <p className="text-xs text-muted-foreground truncate">{m.last_message}</p>
                      </div>
                      <span className="text-[10px] text-muted-foreground shrink-0">{formatTime(m.last_message_at)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Open Cases */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderOpen className="h-4 w-4 text-blue-500" />
                <CardTitle className="text-sm font-semibold">Open Cases</CardTitle>
              </div>
              <Link href="/cases">
                <Button variant="ghost" size="sm" className="text-xs h-7">
                  View All <ArrowRight className="h-3 w-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {data.openCases.length === 0 ? (
              <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                No open cases
              </div>
            ) : (
              <div className="space-y-1">
                {data.openCases.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center gap-3 py-2 -mx-2 px-2 rounded cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => router.push(`/cases/${c.id}`)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{c.title}</p>
                      <p className="text-xs text-muted-foreground">{c.customer_name}</p>
                    </div>
                    <div className="text-right shrink-0">
                      {c.open_job_count > 0 && <span className="text-[10px] text-muted-foreground">{c.open_job_count} job{c.open_job_count > 1 ? "s" : ""}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Inbox */}
        {perms.canViewInbox && data.recentThreads.length > 0 && (
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <CardTitle className="text-sm font-semibold">Recent Emails</CardTitle>
                </div>
                <Link href="/inbox">
                  <Button variant="ghost" size="sm" className="text-xs h-7">
                    Inbox <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {data.recentThreads.map((t) => (
                  <Link key={t.id} href="/inbox">
                    <div className="flex items-center gap-3 py-1.5 -mx-2 px-2 rounded hover:bg-muted/50 transition-colors cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium">{t.customer_name}</span>
                        <span className="text-xs text-muted-foreground ml-2">{t.subject}</span>
                      </div>
                      <span className="text-[10px] text-muted-foreground shrink-0">{formatTime(t.last_message_at)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Recent DeepBlue Chats */}
        {data.recentDeepBlueChats.length > 0 && (
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  <CardTitle className="text-sm font-semibold">Recent DeepBlue Chats</CardTitle>
                </div>
                <Link href="/deepblue">
                  <Button variant="ghost" size="sm" className="text-xs h-7">
                    Open <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {data.recentDeepBlueChats.map((c) => (
                  <Link
                    key={c.id}
                    href={`/deepblue?id=${c.id}`}
                    className="w-full flex items-center gap-3 py-1.5 -mx-2 px-2 rounded hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium truncate block">{c.title || "Untitled"}</span>
                      <span className="text-[10px] text-muted-foreground">
                        {c.message_count} message{c.message_count !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground shrink-0">{formatTime(c.updated_at)}</span>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Today's Schedule */}
        {data.todayVisits > 0 && (
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CalendarCheck className="h-4 w-4 text-green-500" />
                  <CardTitle className="text-sm font-semibold">Today</CardTitle>
                  <Badge variant="secondary" className="text-[10px] px-1.5">{data.todayVisits} visit{data.todayVisits > 1 ? "s" : ""}</Badge>
                </div>
                <Link href="/routes">
                  <Button variant="ghost" size="sm" className="text-xs h-7">
                    Routes <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {data.todayVisits} visit{data.todayVisits > 1 ? "s" : ""} scheduled. View routes for details.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function getTimeOfDay() {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}
