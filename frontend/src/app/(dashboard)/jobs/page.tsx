"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Loader2,
  Bot,
  CheckCircle2,
  Plus,
  ClipboardList,
  Lightbulb,
  Check,
  X,
} from "lucide-react";
import { formatDueDate, isOverdue } from "@/lib/format";
import { useTeamMembers } from "@/hooks/use-team-members";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
import { ActionDetailContent } from "@/components/jobs/action-detail-content";
import { NewJobForm } from "@/components/jobs/new-job-form";
import type { AgentAction, AgentStats } from "@/types/agent";

// ─── Main Page ──────────────────────────────────────────────────────

export default function JobsPage() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const myName = user?.first_name || "";
  const teamMembers = useTeamMembers();
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(
    searchParams.get("action")
  );
  const [suggestion, setSuggestion] = useState<{
    id: string;
    action_type: string;
    description: string;
    reasoning: string;
  } | null>(null);
  const [newActionOpen, setNewActionOpen] = useState(false);
  const [jobFilter, setJobFilter] = useState<string>("mine");
  const [showCompleted, setShowCompleted] = useState(false);

  const handleToggleAction = async (
    actionId: string,
    currentStatus: string
  ) => {
    const newStatus = currentStatus === "done" ? "open" : "done";
    try {
      const result = await api.put<{
        suggestion?: {
          id: string;
          action_type: string;
          description: string;
          reasoning: string;
        };
      }>(`/v1/admin/agent-actions/${actionId}`, { status: newStatus });
      if (result.suggestion) {
        setSuggestion(result.suggestion);
      }
      load();
    } catch {
      toast.error("Failed to update");
    }
  };

  const load = useCallback(async () => {
    try {
      const assigneeParam =
        jobFilter === "mine" && myName
          ? `&assigned_to=${encodeURIComponent(myName)}`
          : jobFilter !== "mine" && jobFilter !== "all"
            ? `&assigned_to=${encodeURIComponent(jobFilter)}`
            : "";
      const statuses = showCompleted
        ? ["open", "in_progress", "done"]
        : ["open", "in_progress"];
      const [st, ...actionResults] = await Promise.all([
        api.get<AgentStats>("/v1/admin/agent-stats"),
        ...statuses.map((s) =>
          api
            .get<AgentAction[]>(
              `/v1/admin/agent-actions?status=${s}${assigneeParam}`
            )
            .catch(() => [] as AgentAction[])
        ),
      ]);
      setStats(st);
      setActions(actionResults.flat());
    } catch {
      toast.error("Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [jobFilter, showCompleted, myName]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll every 30s
  useEffect(() => {
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Group actions by parent message (event) or standalone
  const grouped = new Map<
    string,
    { label: string; from: string; actions: AgentAction[] }
  >();
  for (const a of actions) {
    const key = a.agent_message_id || `standalone-${a.id}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        label: a.subject || "Unknown",
        from: a.customer_name || a.from_email || "",
        actions: [],
      });
    }
    grouped.get(key)!.actions.push(a);
  }
  const groups = Array.from(grouped.entries());

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ClipboardList className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Jobs</h1>
      </div>

      {/* Open Jobs tile + New Job */}
      <div className="flex items-center justify-between gap-4">
        {stats && (
          <Card className={`shadow-sm py-3 px-4 ${stats.overdue_actions > 0 ? "border-l-4 border-red-500" : ""}`}>
            <div className="flex items-center gap-3">
              <ClipboardList className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-medium">Open Jobs</span>
              <span className="text-2xl font-bold">{stats.open_actions}</span>
              {stats.overdue_actions > 0 && (
                <Badge variant="destructive" className="text-[10px]">{stats.overdue_actions} overdue</Badge>
              )}
            </div>
          </Card>
        )}
        <Button onClick={() => setNewActionOpen(!newActionOpen)}>
          <Plus className="h-4 w-4 mr-2" />
          New Job
        </Button>
      </div>

      {/* AI Suggestion banner */}
      {suggestion && (
        <Card className="shadow-sm border-l-4 border-blue-500 bg-blue-50/50 dark:bg-blue-950/20">
          <CardContent className="py-3 px-4">
            <div className="flex items-start gap-3">
              <Bot className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">
                  Suggested next step
                </p>
                <p className="text-sm mt-0.5">
                  {suggestion.description}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {suggestion.reasoning}
                </p>
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
                <Button
                  size="sm"
                  className="h-7"
                  onClick={async () => {
                    try {
                      await api.put(
                        `/v1/admin/agent-actions/${suggestion.id}`,
                        { status: "open" }
                      );
                      toast.success("Action accepted");
                      setSuggestion(null);
                      load();
                    } catch {
                      toast.error("Failed");
                    }
                  }}
                >
                  Accept
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7"
                  onClick={async () => {
                    try {
                      await api.put(
                        `/v1/admin/agent-actions/${suggestion.id}`,
                        { status: "cancelled" }
                      );
                      setSuggestion(null);
                      load();
                    } catch {
                      toast.error("Failed");
                    }
                  }}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Job filters */}
      <div className="flex flex-col sm:flex-row gap-3 justify-between">
        <div className="flex gap-2 items-center">
          <Button
            variant={jobFilter === "mine" ? "default" : "outline"}
            size="sm"
            className="h-7"
            onClick={() => setJobFilter("mine")}
          >
            My Jobs
          </Button>
          <Button
            variant={jobFilter === "all" ? "default" : "outline"}
            size="sm"
            className="h-7"
            onClick={() => setJobFilter("all")}
          >
            All
          </Button>
          {teamMembers.length > 0 && (
            <Select
              value={teamMembers.includes(jobFilter) ? jobFilter : ""}
              onValueChange={(v) => setJobFilter(v)}
            >
              <SelectTrigger className="h-7 w-40 text-xs">
                <SelectValue placeholder="Team member..." />
              </SelectTrigger>
              <SelectContent>
                {teamMembers.map((name) => (
                  <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={showCompleted}
              onChange={(e) => setShowCompleted(e.target.checked)}
              className="rounded"
            />
            Done
          </label>
        </div>
      </div>

      {/* New Job form */}
      {newActionOpen && (
        <NewJobForm
          onCreated={() => {
            setNewActionOpen(false);
            load();
          }}
          onClose={() => setNewActionOpen(false)}
        />
      )}

      {/* Grouped jobs list */}
      <Card className="shadow-sm">
        <CardContent className="p-0">
          {actions.length === 0 && !newActionOpen ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <CheckCircle2 className="h-10 w-10 mb-3 opacity-40" />
              <p className="text-sm">All caught up — no open jobs</p>
            </div>
          ) : (
            <div className="divide-y">
              {groups.map(([msgId, group]) => {
                const hasOverdue = group.actions.some(
                  (a) =>
                    a.status !== "done" &&
                    a.status !== "cancelled" &&
                    isOverdue(a.due_date)
                );
                return (
                  <div
                    key={msgId}
                    className={
                      hasOverdue
                        ? "bg-red-50/50 dark:bg-red-950/10"
                        : ""
                    }
                  >
                    {/* Event header */}
                    <div className="flex items-center justify-between px-4 pt-3 pb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {group.from}
                        </p>
                        <span className="text-xs text-muted-foreground truncate hidden sm:inline">
                          — {group.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                      </div>
                    </div>
                    {/* Actions under this event */}
                    <div className="px-4 pb-3 space-y-1">
                      {group.actions.map((a) => {
                        const overdue =
                          a.status !== "done" &&
                          a.status !== "cancelled" &&
                          isOverdue(a.due_date);
                        const isSuggested = a.is_suggested === true;
                        return (
                          <div
                            key={a.id}
                            className={`flex items-start gap-2 py-1.5 pl-2 rounded cursor-pointer ${
                              isSuggested
                                ? "border border-dashed border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-950/10"
                                : overdue
                                  ? "bg-red-50 dark:bg-red-950/20"
                                  : "hover:bg-muted/50"
                            }`}
                            onClick={() => setSelectedActionId(a.id)}
                          >
                            {isSuggested ? (
                              <Lightbulb className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                            ) : (
                              <ActionStatusIcon status={a.status} />
                            )}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <ActionTypeBadge
                                  type={a.action_type}
                                />
                                {isSuggested && (
                                  <Badge
                                    variant="outline"
                                    className="text-[10px] px-1.5 border-amber-400 text-amber-600"
                                  >
                                    Suggested{a.suggestion_confidence === "low" ? " (low)" : ""}
                                  </Badge>
                                )}
                                {overdue && !isSuggested && (
                                  <Badge
                                    variant="destructive"
                                    className="text-[10px] px-1.5"
                                  >
                                    Overdue
                                  </Badge>
                                )}
                                {a.due_date && (
                                  <span
                                    className={`text-[10px] ${
                                      overdue && !isSuggested
                                        ? "text-red-600 font-medium"
                                        : "text-muted-foreground"
                                    }`}
                                  >
                                    {formatDueDate(a.due_date)}
                                  </span>
                                )}
                              </div>
                              <p
                                className={`text-sm mt-0.5 ${
                                  a.status === "done"
                                    ? "line-through text-muted-foreground"
                                    : isSuggested
                                      ? "text-muted-foreground"
                                      : ""
                                }`}
                              >
                                {a.description}
                              </p>
                              {!isSuggested && (
                                <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                                  <Select
                                    value={a.assigned_to || ""}
                                    onValueChange={async (v) => {
                                      try {
                                        await api.put(
                                          `/v1/admin/agent-actions/${a.id}`,
                                          { assigned_to: v }
                                        );
                                        load();
                                      } catch {
                                        toast.error(
                                          "Failed to assign"
                                        );
                                      }
                                    }}
                                  >
                                    <SelectTrigger className="h-5 w-auto border-none bg-transparent p-0 text-xs gap-1 shadow-none">
                                      <SelectValue placeholder="Assign..." />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {teamMembers.map((name) => (
                                        <SelectItem
                                          key={name}
                                          value={name}
                                          className="text-xs"
                                        >
                                          {name}
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </div>
                              )}
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              {isSuggested && (
                                <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-muted-foreground hover:text-green-600"
                                    onClick={async () => {
                                      try {
                                        await api.post(`/v1/admin/agent-actions/${a.id}/approve-suggestion`, {});
                                        toast.success("Suggestion approved");
                                        load();
                                      } catch { toast.error("Failed"); }
                                    }}
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-muted-foreground hover:text-destructive"
                                    onClick={async () => {
                                      try {
                                        await api.post(`/v1/admin/agent-actions/${a.id}/dismiss-suggestion`, {});
                                        toast.success("Suggestion dismissed");
                                        load();
                                      } catch { toast.error("Failed"); }
                                    }}
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              )}
                              {!isSuggested && (a.task_count || 0) > 0 && (
                                <span className="text-[10px] text-muted-foreground">
                                  {a.tasks_completed || 0}/{a.task_count} tasks
                                </span>
                              )}
                              {!isSuggested && a.assigned_to && (
                                <span className="text-[10px] text-muted-foreground">{a.assigned_to}</span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action detail sheet */}
      <Sheet
        open={!!selectedActionId}
        onOpenChange={(open) => {
          if (!open) setSelectedActionId(null);
        }}
      >
        <SheetContent className="w-full sm:max-w-md flex flex-col h-full">
          <SheetHeader className="px-4 sm:px-6 flex-shrink-0">
            <SheetTitle className="text-lg">Job Detail</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 pb-6">
            {selectedActionId && (
              <ActionDetailContent
                actionId={selectedActionId}
                onClose={() => setSelectedActionId(null)}
                onUpdate={load}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
