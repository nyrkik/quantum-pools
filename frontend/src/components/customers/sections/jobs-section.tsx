"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, Plus, ChevronDown, ChevronUp } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { formatTime, formatDueDate, isOverdue } from "@/lib/format";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
import { ActionDetailContent } from "@/components/jobs/action-detail-content";
import type { AgentAction } from "@/types/agent";

interface JobsSectionProps {
  customerId: string;
}

export function JobsSection({ customerId }: JobsSectionProps) {
  const [jobs, setJobs] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);

  const loadJobs = useCallback(() => {
    setLoading(true);
    api.get<{ items: AgentAction[] }>(`/v1/admin/agent-actions?customer_id=${customerId}&limit=20`)
      .then((data) => setJobs(data.items ?? []))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, [customerId]);

  useEffect(() => { loadJobs(); }, [loadJobs]);

  const activeJobs = jobs.filter((j) => j.status === "open" || j.status === "in_progress");
  const completedJobs = jobs.filter((j) => j.status === "done" || j.status === "cancelled");

  const handleJobAction = () => {
    loadJobs();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Active jobs */}
      {activeJobs.length === 0 && completedJobs.length === 0 ? (
        <div className="text-center py-6">
          <p className="text-sm text-muted-foreground">No jobs for this customer</p>
        </div>
      ) : activeJobs.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">No active jobs</p>
      ) : (
        <div className="space-y-1">
          {activeJobs.map((job) => (
            <JobRow key={job.id} job={job} onClick={() => setSelectedJobId(job.id)} />
          ))}
        </div>
      )}

      {/* Completed jobs — collapsed */}
      {completedJobs.length > 0 && (
        <div>
          <button
            onClick={() => setShowCompleted(!showCompleted)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
          >
            {showCompleted ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {completedJobs.length} completed
          </button>
          {showCompleted && (
            <div className="space-y-1 mt-1">
              {completedJobs.map((job) => (
                <JobRow key={job.id} job={job} onClick={() => setSelectedJobId(job.id)} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Job detail sheet */}
      <Sheet open={!!selectedJobId} onOpenChange={(open) => { if (!open) setSelectedJobId(null); }}>
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Job Details</SheetTitle>
          </SheetHeader>
          {selectedJobId && (
            <ActionDetailContent
              actionId={selectedJobId}
              onClose={() => setSelectedJobId(null)}
              onUpdate={handleJobAction}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function JobRow({ job, onClick }: { job: AgentAction; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors text-left border"
    >
      <ActionStatusIcon status={job.status} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <ActionTypeBadge type={job.action_type} />
          {job.due_date && isOverdue(job.due_date) && job.status !== "done" && (
            <Badge variant="destructive" className="text-[10px] px-1.5">Overdue</Badge>
          )}
        </div>
        <p className="text-sm truncate">{job.description}</p>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-0.5">
          {job.assigned_to && <span>{job.assigned_to}</span>}
          {job.due_date && <span>{formatDueDate(job.due_date)}</span>}
          <span>{formatTime(job.created_at)}</span>
        </div>
      </div>
    </button>
  );
}
