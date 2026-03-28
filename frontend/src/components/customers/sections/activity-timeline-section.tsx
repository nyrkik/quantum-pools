"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, ClipboardCheck, Mail, Wrench, Clock, CheckSquare, Plus } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { formatTime } from "@/lib/format";
import { useCompose } from "@/components/email/compose-provider";
import { usePermissions } from "@/lib/permissions";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";
import { StatusBadge, UrgencyBadge } from "@/components/inbox/inbox-badges";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
import { ActionDetailContent } from "@/components/jobs/action-detail-content";
import type { Thread, AgentAction } from "@/types/agent";
import type { Property } from "../customer-types";

interface VisitHistoryItem {
  id: string;
  scheduled_date: string | null;
  status: string;
  duration_minutes: number | null;
  tech_name: string | null;
  notes: string | null;
  photo_count: number;
  reading_count: number;
  checklist_total: number;
  checklist_completed: number;
}

type TimelineItem =
  | { kind: "visit"; date: string; data: VisitHistoryItem }
  | { kind: "email"; date: string; data: Thread }
  | { kind: "job"; date: string; data: AgentAction };

interface ActivityTimelineSectionProps {
  customerId: string;
  customerEmail?: string;
  customerName?: string;
  properties: Property[];
}

const MAX_ITEMS = 15;

export function ActivityTimelineSection({
  customerId,
  customerEmail,
  customerName,
  properties,
}: ActivityTimelineSectionProps) {
  const router = useRouter();
  const perms = usePermissions();
  const { openCompose } = useCompose();
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [visitResults, threadResult, jobResult] = await Promise.all([
        // Fetch visits for all properties
        Promise.all(
          properties.map((p) =>
            api
              .get<VisitHistoryItem[]>(`/v1/visits/history/${p.id}?limit=10`)
              .catch(() => [] as VisitHistoryItem[])
          )
        ),
        // Threads (only if user can see inbox)
        perms.canViewInbox
          ? api
              .get<{ items: Thread[] }>(
                `/v1/admin/agent-threads?customer_id=${customerId}&limit=10`
              )
              .catch(() => ({ items: [] as Thread[] }))
          : Promise.resolve({ items: [] as Thread[] }),
        // Jobs
        perms.can("jobs.view")
          ? api
              .get<{ items: AgentAction[] }>(
                `/v1/admin/agent-actions?customer_id=${customerId}&limit=10`
              )
              .catch(() => ({ items: [] as AgentAction[] }))
          : Promise.resolve({ items: [] as AgentAction[] }),
      ]);

      const merged: TimelineItem[] = [];

      for (const visit of visitResults.flat()) {
        merged.push({
          kind: "visit",
          date: visit.scheduled_date
            ? visit.scheduled_date + "T12:00:00Z"
            : "1970-01-01T00:00:00Z",
          data: visit,
        });
      }

      for (const thread of threadResult.items) {
        merged.push({
          kind: "email",
          date: thread.last_message_at || "1970-01-01T00:00:00Z",
          data: thread,
        });
      }

      for (const job of jobResult.items) {
        merged.push({
          kind: "job",
          date: job.created_at || "1970-01-01T00:00:00Z",
          data: job,
        });
      }

      merged.sort(
        (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
      );

      setItems(merged.slice(0, MAX_ITEMS));
    } finally {
      setLoading(false);
    }
  }, [customerId, properties, perms]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleLogVisit = () => {
    const propId = properties[0]?.id;
    if (propId) router.push(`/visits/new?property=${propId}`);
  };

  const handleNewEmail = () => {
    openCompose({ to: customerEmail, customerId, customerName });
  };

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Action buttons */}
      <div className="flex items-center gap-2">
        {properties.length > 0 && (
          <Button variant="outline" size="sm" onClick={handleLogVisit}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            Log Visit
          </Button>
        )}
        {customerEmail && perms.canViewInbox && (
          <Button variant="outline" size="sm" onClick={handleNewEmail}>
            <Mail className="h-3.5 w-3.5 mr-1.5" />
            New Email
          </Button>
        )}
      </div>

      {/* Timeline feed */}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-6">
          No activity yet
        </p>
      ) : (
        <div className="space-y-1">
          {items.map((item) => {
            if (item.kind === "visit") return <VisitRow key={`v-${item.data.id}`} visit={item.data} />;
            if (item.kind === "email") return <EmailRow key={`e-${item.data.id}`} thread={item.data} onClick={() => setSelectedThreadId(item.data.id)} />;
            return <JobRow key={`j-${item.data.id}`} job={item.data} onClick={() => setSelectedJobId(item.data.id)} />;
          })}
        </div>
      )}

      {/* Thread detail sheet */}
      <Sheet
        open={!!selectedThreadId}
        onOpenChange={(open) => {
          if (!open) setSelectedThreadId(null);
        }}
      >
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Thread</SheetTitle>
          </SheetHeader>
          {selectedThreadId && (
            <ThreadDetailSheet
              threadId={selectedThreadId}
              onClose={() => setSelectedThreadId(null)}
              onAction={loadAll}
            />
          )}
        </SheetContent>
      </Sheet>

      {/* Job detail sheet */}
      <Sheet
        open={!!selectedJobId}
        onOpenChange={(open) => {
          if (!open) setSelectedJobId(null);
        }}
      >
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Job Details</SheetTitle>
          </SheetHeader>
          {selectedJobId && (
            <ActionDetailContent
              actionId={selectedJobId}
              onClose={() => setSelectedJobId(null)}
              onUpdate={loadAll}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

/* --- Row components --- */

function VisitRow({ visit }: { visit: VisitHistoryItem }) {
  const dateLabel = visit.scheduled_date
    ? new Date(visit.scheduled_date + "T00:00:00").toLocaleDateString()
    : "No date";

  return (
    <Link
      href={`/visits/${visit.id}`}
      className="flex items-center gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors border"
    >
      <ClipboardCheck className="h-4 w-4 text-emerald-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-sm font-medium">Service visit</span>
          <Badge
            variant={visit.status === "completed" ? "default" : "outline"}
            className="text-[10px] px-1.5"
          >
            {visit.status}
          </Badge>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {visit.tech_name && <span>{visit.tech_name}</span>}
          {visit.duration_minutes != null && (
            <span className="flex items-center gap-0.5">
              <Clock className="h-3 w-3" />
              {visit.duration_minutes}m
            </span>
          )}
          {visit.checklist_total > 0 && (
            <span className="flex items-center gap-0.5">
              <CheckSquare className="h-3 w-3" />
              {visit.checklist_completed}/{visit.checklist_total}
            </span>
          )}
        </div>
      </div>
      <span className="text-[10px] text-muted-foreground shrink-0">
        {dateLabel}
      </span>
    </Link>
  );
}

function EmailRow({
  thread,
  onClick,
}: {
  thread: Thread;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors text-left border"
    >
      <Mail className="h-4 w-4 text-blue-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-sm font-medium truncate">
            {thread.subject || thread.last_snippet || "No subject"}
          </span>
          {thread.is_unread && (
            <span className="h-2 w-2 rounded-full bg-blue-500 shrink-0" />
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate">
          {thread.contact_email}
        </p>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <span className="text-[10px] text-muted-foreground">
          {formatTime(thread.last_message_at)}
        </span>
        <div className="flex items-center gap-1">
          <StatusBadge status={thread.status} />
          <UrgencyBadge urgency={thread.urgency} />
        </div>
      </div>
    </button>
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
        </div>
        <p className="text-sm truncate">{job.description}</p>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-0.5">
          {job.assigned_to && <span>{job.assigned_to}</span>}
          <span>{formatTime(job.created_at)}</span>
        </div>
      </div>
    </button>
  );
}
