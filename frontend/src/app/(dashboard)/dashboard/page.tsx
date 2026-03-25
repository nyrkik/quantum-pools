"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { api } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Users,
  MapPin,
  CalendarCheck,
  DollarSign,
  Mail,
  ClipboardList,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Bot,
  ArrowRight,
  Loader2,
} from "lucide-react";
import { formatTime, formatDueDate, isOverdue } from "@/lib/format";
import type { AgentStats, AgentAction, AgentMessage } from "@/types/agent";

interface Stats {
  customers: number;
  properties: number;
  todayVisits: number;
  monthlyRevenue: number;
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-amber-400",
    sent: "bg-green-500",
    auto_sent: "bg-blue-500",
    rejected: "bg-red-500",
    ignored: "bg-gray-300",
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[status] || "bg-gray-300"}`} />;
}

export default function DashboardPage() {
  const { user, organizationName } = useAuth();
  const perms = usePermissions();
  const [stats, setStats] = useState<Stats>({
    customers: 0,
    properties: 0,
    todayVisits: 0,
    monthlyRevenue: 0,
  });
  const [agentStats, setAgentStats] = useState<AgentStats | null>(null);
  const [pendingMessages, setPendingMessages] = useState<AgentMessage[]>([]);
  const [openActions, setOpenActions] = useState<AgentAction[]>([]);
  const [recentMessages, setRecentMessages] = useState<AgentMessage[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const promises: Promise<unknown>[] = [
          api.get<{ total: number }>("/v1/customers?limit=1"),
          api.get<{ total: number }>("/v1/properties?limit=1"),
          api.get<{ total: number }>(
            `/v1/visits?scheduled_date=${new Date().toISOString().split("T")[0]}&limit=1`
          ),
        ];

        if (perms.canViewInbox) {
          promises.push(
            api.get<AgentStats>("/v1/admin/agent-threads/stats"),
            api.get<{ items: AgentMessage[] }>("/v1/admin/agent-threads?status=pending&limit=5"),
            api.get<AgentAction[]>("/v1/admin/agent-actions?status=open&limit=5"),
            api.get<{ items: AgentMessage[] }>("/v1/admin/agent-threads?limit=5&exclude_spam=true"),
          );
        }

        const results = await Promise.all(promises);
        const [customers, properties, visits] = results as [{ total: number }, { total: number }, { total: number }];

        setStats({
          customers: customers.total,
          properties: properties.total,
          todayVisits: visits.total,
          monthlyRevenue: 0,
        });

        if (perms.canViewInbox && results.length > 3) {
          setAgentStats(results[3] as AgentStats);
          setPendingMessages((results[4] as { items: AgentMessage[] }).items || []);
          setOpenActions(results[5] as AgentAction[]);
          setRecentMessages((results[6] as { items: AgentMessage[] }).items || []);
        }
      } catch {
        // Stats will stay at defaults
      } finally {
        setLoading(false);
      }
    })();
  }, [perms.canViewInbox]);

  const statCards = [
    { title: "Clients", value: stats.customers, icon: Users, href: "/customers" },
    { title: "Properties", value: stats.properties, icon: MapPin, href: "/customers" },
    { title: "Today's Visits", value: stats.todayVisits, icon: CalendarCheck, href: "/routes" },
    { title: "Monthly Revenue", value: `$${stats.monthlyRevenue.toLocaleString()}`, icon: DollarSign, href: "/invoices" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Welcome back, {user?.first_name}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((stat) => (
          <Link key={stat.title} href={stat.href}>
            <Card className="shadow-sm cursor-pointer transition-shadow hover:shadow-md">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                <stat.icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{typeof stat.value === "number" ? stat.value.toLocaleString() : stat.value}</div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Inbox + Actions row */}
      {perms.canViewInbox && agentStats && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Pending Messages */}
          <Card className={`shadow-sm ${agentStats.pending > 0 ? "border-l-4 border-amber-400" : ""}`}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-amber-500" />
                  <CardTitle className="text-base">Pending Messages</CardTitle>
                  {agentStats.pending > 0 && (
                    <Badge variant="outline" className="border-amber-400 text-amber-600 text-xs">
                      {agentStats.pending}
                    </Badge>
                  )}
                </div>
                <Link href="/inbox">
                  <Button variant="ghost" size="sm" className="text-xs">
                    View All <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </Link>
              </div>
              {agentStats.stale_pending > 0 && (
                <p className="text-xs text-red-600 flex items-center gap-1 mt-1">
                  <AlertTriangle className="h-3 w-3" />{agentStats.stale_pending} waiting over 30 min
                </p>
              )}
            </CardHeader>
            <CardContent>
              {pendingMessages.length === 0 ? (
                <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  All caught up
                </div>
              ) : (
                <div className="space-y-2">
                  {pendingMessages.map((m) => (
                    <Link key={m.id} href="/inbox" className="flex items-center gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors">
                      <Clock className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{m.customer_name || m.from_email}</p>
                        <p className="text-xs text-muted-foreground truncate">{m.subject}</p>
                      </div>
                      <span className="text-[10px] text-muted-foreground flex-shrink-0">{formatTime(m.received_at)}</span>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Open Jobs */}
          <Card className={`shadow-sm ${agentStats.overdue_actions > 0 ? "border-l-4 border-red-500" : ""}`}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ClipboardList className="h-4 w-4 text-purple-500" />
                  <CardTitle className="text-base">Jobs</CardTitle>
                  {agentStats.open_actions > 0 && (
                    <Badge variant="outline" className="border-purple-400 text-purple-600 text-xs">
                      {agentStats.open_actions}
                    </Badge>
                  )}
                </div>
                <Link href="/jobs">
                  <Button variant="ghost" size="sm" className="text-xs">
                    View All <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </Link>
              </div>
              {agentStats.overdue_actions > 0 && (
                <p className="text-xs text-red-600 flex items-center gap-1 mt-1">
                  <AlertTriangle className="h-3 w-3" />{agentStats.overdue_actions} overdue
                </p>
              )}
            </CardHeader>
            <CardContent>
              {openActions.length === 0 ? (
                <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  No open jobs
                </div>
              ) : (
                <div className="space-y-2">
                  {openActions.map((a) => {
                    const overdue = isOverdue(a.due_date);
                    return (
                      <div key={a.id} className={`flex items-center gap-3 p-2 rounded-md ${overdue ? "bg-red-50 dark:bg-red-950/20" : "hover:bg-muted/50"}`}>
                        <Badge variant="outline" className="text-[10px] px-1.5 capitalize flex-shrink-0">
                          {a.action_type.replace("_", " ")}
                        </Badge>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm truncate">{a.description}</p>
                          <p className="text-xs text-muted-foreground">{a.customer_name || a.from_email}</p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          {a.due_date && (
                            <span className={`text-[10px] ${overdue ? "text-red-600 font-medium" : "text-muted-foreground"}`}>
                              {formatDueDate(a.due_date)}
                            </span>
                          )}
                          {a.assigned_to && (
                            <p className="text-[10px] text-muted-foreground">{a.assigned_to}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recent Activity */}
      {perms.canViewInbox && recentMessages.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-base">Recent Inbox Activity</CardTitle>
              </div>
              <Link href="/inbox">
                <Button variant="ghost" size="sm" className="text-xs">
                  View All <ArrowRight className="h-3 w-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {recentMessages.map((m) => (
                <div key={m.id} className="flex items-center gap-3 py-1.5">
                  <StatusDot status={m.status} />
                  <span className="text-sm flex-1 truncate">
                    <span className="font-medium">{m.customer_name || m.from_email}</span>
                    <span className="text-muted-foreground ml-2">{m.subject}</span>
                  </span>
                  <span className="text-[10px] text-muted-foreground flex-shrink-0">{formatTime(m.received_at)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
