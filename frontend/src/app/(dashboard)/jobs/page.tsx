"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import { toast } from "sonner";
import {
  Loader2,
  ClipboardList,
  FolderOpen,
} from "lucide-react";
import { useTeamMembers } from "@/hooks/use-team-members";
import { ActionDetailContent } from "@/components/jobs/action-detail-content";
import { NewJobForm } from "@/components/jobs/new-job-form";
import { JobFilterBar } from "@/components/jobs/job-filter-bar";
import { JobGroupList } from "@/components/jobs/job-group-list";
import { PageLayout } from "@/components/layout/page-layout";
import type { AgentAction, AgentStats } from "@/types/agent";

// ─── Main Page ──────────────────────────────────────────────────────

export default function JobsPage() {
  const router = useRouter();
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
  const [newActionOpen, setNewActionOpen] = useState(false);
  const [jobFilter, setJobFilter] = useState<string>(
    // Deep-link support: UnassignedPoolStep sends ?assigned=unassigned.
    searchParams.get("assigned") === "unassigned" ? "unassigned" : "mine",
  );
  const [showCompleted, setShowCompleted] = useState(false);

  const handleToggleAction = async (
    actionId: string,
    currentStatus: string
  ) => {
    const newStatus = currentStatus === "done" ? "open" : "done";
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}`, { status: newStatus });
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

  return (
    <PageLayout
      title="Jobs"
      icon={<ClipboardList className="h-5 w-5 text-primary" />}
      action={
        <Button onClick={() => router.push("/cases")}>
          <FolderOpen className="h-4 w-4 mr-2" />
          Cases
        </Button>
      }
      context={
        <div className="space-y-6">
          {/* Open Jobs tile */}
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
        </div>
      }
    >

      {/* Job filters */}
      <JobFilterBar
        jobFilter={jobFilter}
        onFilterChange={setJobFilter}
        showCompleted={showCompleted}
        onShowCompletedChange={setShowCompleted}
        teamMembers={teamMembers}
      />

      {/* New Job form */}
      <NewJobForm
        open={newActionOpen}
        onCreated={() => {
          setNewActionOpen(false);
          load();
        }}
        onClose={() => setNewActionOpen(false)}
      />

      {/* Grouped jobs list */}
      <JobGroupList
        actions={actions}
        teamMembers={teamMembers}
        onSelectAction={setSelectedActionId}
        onRefresh={load}
      />

      {/* Action detail overlay */}
      <Overlay
        open={!!selectedActionId}
        onOpenChange={(open) => {
          if (!open) setSelectedActionId(null);
        }}
      >
        <OverlayContent>
          <OverlayHeader>
            <OverlayTitle>Job Detail</OverlayTitle>
          </OverlayHeader>
          <OverlayBody>
            {selectedActionId && (
              <ActionDetailContent
                actionId={selectedActionId}
                onClose={() => setSelectedActionId(null)}
                onUpdate={load}
              />
            )}
          </OverlayBody>
        </OverlayContent>
      </Overlay>
    </PageLayout>
  );
}
