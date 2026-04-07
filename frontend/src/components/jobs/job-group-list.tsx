"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  CheckCircle2,
  Lightbulb,
  Check,
  X,
} from "lucide-react";
import { formatDueDate, isOverdue } from "@/lib/format";
import {
  ActionTypeBadge,
  ActionStatusIcon,
  JobPathBadge,
} from "@/components/jobs/job-badges";
import type { AgentAction } from "@/types/agent";

interface JobGroup {
  label: string;
  from: string;
  address: string;
  actions: AgentAction[];
}

interface JobGroupListProps {
  actions: AgentAction[];
  teamMembers: string[];
  onSelectAction: (id: string) => void;
  onRefresh: () => void;
}

export function JobGroupList({
  actions,
  teamMembers,
  onSelectAction,
  onRefresh,
}: JobGroupListProps) {
  // Group actions by parent message (event) or standalone
  const grouped = new Map<string, JobGroup>();
  for (const a of actions) {
    const key = a.agent_message_id || `standalone-${a.id}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        label: a.subject || a.description || "",
        from: a.customer_name || a.from_email || "",
        address:
          (a as unknown as Record<string, string>).customer_address || "",
        actions: [],
      });
    }
    grouped.get(key)!.actions.push(a);
  }
  const groups = Array.from(grouped.entries());

  if (actions.length === 0) {
    return (
      <Card className="shadow-sm">
        <CardContent className="p-0">
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <CheckCircle2 className="h-10 w-10 mb-3 opacity-40" />
            <p className="text-sm">All caught up — no open jobs</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="shadow-sm">
      <CardContent className="p-0">
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
                  hasOverdue ? "bg-red-50/50 dark:bg-red-950/10" : ""
                }
              >
                {/* Event header */}
                <div className="flex items-center justify-between px-4 pt-3 pb-1">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {group.from}
                    </p>
                    {group.address && (
                      <p className="text-[10px] text-muted-foreground truncate">
                        {group.address}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0"></div>
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
                        onClick={() => onSelectAction(a.id)}
                      >
                        {isSuggested ? (
                          <Lightbulb className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                        ) : (
                          <ActionStatusIcon status={a.status} />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <ActionTypeBadge type={a.action_type} />
                            <JobPathBadge path={a.job_path} />
                            {isSuggested && (
                              <Badge
                                variant="outline"
                                className="text-[10px] px-1.5 border-amber-400 text-amber-600"
                              >
                                Suggested
                                {a.suggestion_confidence === "low"
                                  ? " (low)"
                                  : ""}
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
                                    onRefresh();
                                  } catch {
                                    toast.error("Failed to assign");
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
                            <div
                              className="flex gap-1"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-muted-foreground hover:text-green-600"
                                onClick={async () => {
                                  try {
                                    await api.post(
                                      `/v1/admin/agent-actions/${a.id}/approve-suggestion`,
                                      {}
                                    );
                                    toast.success("Suggestion approved");
                                    onRefresh();
                                  } catch {
                                    toast.error("Failed");
                                  }
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
                                    await api.post(
                                      `/v1/admin/agent-actions/${a.id}/dismiss-suggestion`,
                                      {}
                                    );
                                    toast.success("Suggestion dismissed");
                                    onRefresh();
                                  } catch {
                                    toast.error("Failed");
                                  }
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
                            <span className="text-[10px] text-muted-foreground">
                              {a.assigned_to}
                            </span>
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
      </CardContent>
    </Card>
  );
}
