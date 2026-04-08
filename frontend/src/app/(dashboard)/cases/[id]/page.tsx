"use client";

import { useState, useEffect, useCallback, useMemo, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowLeft,
  FolderOpen,
  Mail,
  ClipboardList,
  FileText,
  MessageSquare,
  Loader2,
  Pencil,
  Check,
  CheckCircle2,
  X,
  Circle,
  Clock,
  Trash2,
  Plus,
  Sparkles,
  Send,
  Inbox,
  DollarSign,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ComposeMessage } from "@/components/messages/compose-message";
import { useCompose } from "@/components/email/compose-provider";
import { CaseDeepBlueCard } from "@/components/deepblue/case-deepblue-card";
import { useDeepBlueContext } from "@/components/deepblue/deepblue-provider";
import { useTeamMembers } from "@/hooks/use-team-members";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CaseStatusBadge,
  JobCard,
  InvoiceCard,
  formatTime,
  JOB_TYPES,
} from "@/components/cases/case-components";
import type {
  CaseDetail,
  CaseJob,
  CaseInvoice,
  TimelineEntry,
} from "@/components/cases/case-components";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";

// --- Selected item tracking ---

interface SelectedItem {
  type: string;
  id: string;
}

// --- Timeline Row (compact, clickable) ---

function TimelineRow({
  entry,
  isSelected,
  onSelect,
}: {
  entry: TimelineEntry;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const isEmail = entry.type === "email";
  const isOutbound = entry.metadata?.direction === "outbound";
  const isInbound = entry.metadata?.direction === "inbound";
  const isJobEvent = entry.type === "job_event";
  const isCompleted = isJobEvent && entry.metadata?.event === "completed";
  const isCancelled = isJobEvent && entry.metadata?.event === "cancelled";
  const isInvoiceEvent = entry.type === "invoice_event";
  const isInternal = entry.type === "internal_message";
  const isDeepBlue = entry.type === "deepblue_chat";
  const isComment = entry.type === "comment";

  const iconColor = isDeepBlue
    ? "text-primary"
    : isEmail
      ? isOutbound
        ? "text-green-500"
        : "text-blue-500"
      : isInvoiceEvent
        ? "text-emerald-500"
        : isJobEvent
          ? isCompleted
            ? "text-green-500"
            : isCancelled
              ? "text-slate-300"
              : "text-amber-500"
          : isInternal
            ? "text-purple-500"
            : isComment
              ? "text-slate-400"
              : "text-amber-500";

  const Icon = isDeepBlue
    ? Sparkles
    : isEmail
      ? isOutbound
        ? Send
        : Inbox
      : isInvoiceEvent
        ? DollarSign
        : isJobEvent
          ? isCompleted
            ? CheckCircle2
            : isCancelled
              ? X
              : ClipboardList
          : isInternal
            ? MessageSquare
            : MessageSquare;

  const preview = entry.body ? entry.body.slice(0, 80) : null;

  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2.5 flex gap-3 items-start transition-colors ${
        isSelected
          ? "bg-blue-50 dark:bg-blue-950/40 border-l-2 border-primary"
          : "hover:bg-muted/50 border-l-2 border-transparent"
      }`}
    >
      <div className={`mt-0.5 shrink-0 ${iconColor}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p
            className={`text-sm truncate ${isEmail ? "font-medium" : ""} ${isCancelled ? "line-through text-muted-foreground" : ""}`}
          >
            {entry.title}
          </p>
          <span className="text-[10px] text-muted-foreground shrink-0 whitespace-nowrap">
            {formatTime(entry.timestamp)}
          </span>
        </div>
        {preview && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {preview}
          </p>
        )}
      </div>
    </button>
  );
}

// --- Detail Panel: Email ---

function EmailDetailPanel({
  entry,
  detail,
  onReply,
}: {
  entry: TimelineEntry;
  detail: CaseDetail;
  onReply: () => void;
}) {
  const isOutbound = entry.metadata?.direction === "outbound";
  const isInbound = entry.metadata?.direction === "inbound";
  const threadId = entry.metadata?.thread_id as string | undefined;
  const thread = threadId
    ? detail.threads.find((t) => t.id === threadId)
    : null;
  const messageId = entry.metadata?.message_id as string | undefined;
  const message = thread?.messages.find((m) => m.id === messageId);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isOutbound ? (
            <Send className="h-4 w-4 text-green-500" />
          ) : (
            <Inbox className="h-4 w-4 text-blue-500" />
          )}
          <span className="text-sm font-medium">
            {isOutbound ? "Sent" : "Received"}
          </span>
        </div>
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onReply}>
          <Send className="h-3 w-3 mr-1" /> Reply
        </Button>
      </div>

      {message && (
        <div className="text-xs text-muted-foreground space-y-0.5">
          <p>
            <span className="font-medium">From:</span> {message.from_email}
          </p>
          <p>
            <span className="font-medium">To:</span> {message.to_email}
          </p>
          {message.subject && (
            <p>
              <span className="font-medium">Subject:</span> {message.subject}
            </p>
          )}
          <p>
            <span className="font-medium">Date:</span>{" "}
            {formatTime(message.received_at || message.sent_at)}
          </p>
        </div>
      )}

      <div
        className={`text-sm whitespace-pre-wrap rounded-md p-4 ${
          isOutbound
            ? "bg-green-50 dark:bg-green-950/30 border-l-2 border-green-400"
            : isInbound
              ? "bg-blue-50 dark:bg-blue-950/30 border-l-2 border-blue-400"
              : "bg-muted/50"
        }`}
      >
        {entry.body || "(no body)"}
      </div>

      {/* Show other messages in the same thread */}
      {thread && thread.messages.length > 1 && (
        <div className="space-y-2 pt-2 border-t">
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Thread ({thread.messages.length} messages)
          </p>
          {thread.messages
            .filter((m) => m.id !== messageId)
            .map((m) => (
              <div
                key={m.id}
                className={`text-xs rounded-md p-2 ${
                  m.direction === "outbound"
                    ? "bg-green-50/50 dark:bg-green-950/20"
                    : "bg-blue-50/50 dark:bg-blue-950/20"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">
                    {m.direction === "outbound" ? "Sent" : "Received"}
                  </span>
                  <span className="text-muted-foreground">
                    {formatTime(m.received_at || m.sent_at)}
                  </span>
                </div>
                <p className="text-muted-foreground line-clamp-3 whitespace-pre-wrap">
                  {m.body?.slice(0, 300) || "(no body)"}
                </p>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

// --- Detail Panel: Job Event ---

function JobEventDetailPanel({
  entry,
  detail,
}: {
  entry: TimelineEntry;
  detail: CaseDetail;
}) {
  const linkedJob = detail.jobs.find(
    (j) => j.id === entry.metadata?.action_id
  );

  if (!linkedJob) {
    return (
      <div className="text-sm text-muted-foreground">Job details not found</div>
    );
  }

  const isCompleted = entry.metadata?.event === "completed";
  const isCancelled = entry.metadata?.event === "cancelled";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <ActionStatusIcon status={linkedJob.status} />
        <ActionTypeBadge type={linkedJob.action_type} />
        {linkedJob.assigned_to && (
          <span className="text-xs text-muted-foreground">
            {linkedJob.assigned_to}
          </span>
        )}
        {linkedJob.due_date && (
          <span className="text-xs text-muted-foreground ml-auto">
            Due{" "}
            {new Date(linkedJob.due_date).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}
          </span>
        )}
      </div>

      <p
        className={`text-sm ${linkedJob.status === "done" ? "line-through text-muted-foreground" : "font-medium"}`}
      >
        {linkedJob.description}
      </p>

      {linkedJob.notes && (
        <p className="text-xs text-muted-foreground bg-muted/50 rounded-md p-3">
          {linkedJob.notes}
        </p>
      )}

      {linkedJob.tasks.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Tasks
          </p>
          {linkedJob.tasks
            .sort((a, b) => a.sort_order - b.sort_order)
            .map((t) => (
              <div key={t.id} className="flex items-center gap-2 text-xs">
                {t.status === "done" ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                ) : (
                  <Circle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                )}
                <span
                  className={
                    t.status === "done"
                      ? "line-through text-muted-foreground"
                      : ""
                  }
                >
                  {t.title}
                </span>
              </div>
            ))}
        </div>
      )}

      {linkedJob.comments.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Notes
          </p>
          {linkedJob.comments.slice(-10).map((c) => (
            <div key={c.id} className="text-xs">
              <span className="font-medium">{c.author}:</span>{" "}
              <span className="text-muted-foreground">
                {c.text.slice(0, 500)}
              </span>
            </div>
          ))}
        </div>
      )}

      {isCompleted && linkedJob.completed_at && (
        <p className="text-xs text-green-600">
          Completed {formatTime(linkedJob.completed_at)}
        </p>
      )}
      {isCancelled && (
        <p className="text-xs text-muted-foreground">Cancelled</p>
      )}
    </div>
  );
}

// --- Detail Panel: Invoice Event ---

function InvoiceEventDetailPanel({
  entry,
  detail,
}: {
  entry: TimelineEntry;
  detail: CaseDetail;
}) {
  const router = useRouter();
  const linkedInvoice = detail.invoices.find(
    (i) => i.id === entry.metadata?.invoice_id
  );

  if (!linkedInvoice) {
    return (
      <div className="text-sm text-muted-foreground">
        Invoice details not found
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DollarSign className="h-4 w-4 text-emerald-600" />
          <span className="text-sm font-medium">
            {linkedInvoice.invoice_number || "Draft"}
          </span>
          <span className="text-xs text-muted-foreground">
            {linkedInvoice.document_type === "estimate"
              ? "Estimate"
              : "Invoice"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-[10px] h-5 px-1.5">
            {linkedInvoice.status
              .replace(/_/g, " ")
              .replace(/\b\w/g, (c) => c.toUpperCase())}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => router.push(`/invoices/${linkedInvoice.id}`)}
          >
            Open
          </Button>
        </div>
      </div>

      {linkedInvoice.subject && (
        <p className="text-xs text-muted-foreground">
          {linkedInvoice.subject}
        </p>
      )}

      {linkedInvoice.line_items.length > 0 && (
        <div className="space-y-1 border rounded-md p-3 bg-muted/20">
          {linkedInvoice.line_items.map((li, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <span className="truncate flex-1">{li.description}</span>
              <span className="text-muted-foreground ml-2 shrink-0">
                {li.quantity > 1 ? `${li.quantity} x ` : ""}$
                {li.unit_price.toFixed(2)}
              </span>
              <span className="font-medium ml-2 shrink-0">
                ${li.amount.toFixed(2)}
              </span>
            </div>
          ))}
          <div className="flex justify-between text-xs font-medium border-t pt-1.5 mt-1.5">
            <span>Total</span>
            <span>${linkedInvoice.total.toFixed(2)}</span>
          </div>
          {linkedInvoice.balance > 0 &&
            linkedInvoice.balance !== linkedInvoice.total && (
              <div className="flex justify-between text-xs text-amber-600">
                <span>Balance Due</span>
                <span>${linkedInvoice.balance.toFixed(2)}</span>
              </div>
            )}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground">
        Created {formatTime(linkedInvoice.created_at)}
      </p>
    </div>
  );
}

// --- Detail Panel: Comment ---

function CommentDetailPanel({ entry }: { entry: TimelineEntry }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-slate-400" />
        <span className="text-sm font-medium">Comment</span>
        {entry.actor && (
          <span className="text-xs text-muted-foreground">
            by {entry.actor}
          </span>
        )}
      </div>

      <div className="text-sm whitespace-pre-wrap rounded-md p-4 bg-muted/50">
        {entry.body || "(empty)"}
      </div>

      {typeof entry.metadata?.job_description === "string" && (
        <p className="text-[10px] text-muted-foreground">
          on: {entry.metadata.job_description}
        </p>
      )}

      <p className="text-[10px] text-muted-foreground">
        {formatTime(entry.timestamp)}
      </p>
    </div>
  );
}

// --- Detail Panel: Internal Message ---

function InternalMessageDetailPanel({ entry }: { entry: TimelineEntry }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-purple-500" />
        <span className="text-sm font-medium">Internal Message</span>
        {entry.actor && (
          <span className="text-xs text-muted-foreground">
            by {entry.actor}
          </span>
        )}
      </div>

      <div className="text-sm whitespace-pre-wrap rounded-md p-4 bg-purple-50 dark:bg-purple-950/30 border-l-2 border-purple-400">
        {entry.body || "(empty)"}
      </div>

      <p className="text-[10px] text-muted-foreground">
        {formatTime(entry.timestamp)}
      </p>
    </div>
  );
}

// --- Detail Panel: DeepBlue Chat ---

function DeepBlueDetailPanel({
  entry,
  detail,
  caseId,
  onUpdate,
}: {
  entry: TimelineEntry;
  detail: CaseDetail;
  caseId: string;
  onUpdate: () => void;
}) {
  const conversationId = entry.metadata?.conversation_id as string | undefined;
  const conversations = detail.deepblue_conversations || [];
  // Filter to just the selected conversation, or empty for new chat
  const filtered = conversationId
    ? conversations.filter((c) => c.id === conversationId)
    : entry.id === "new" ? [] : conversations;

  return (
    <div className="space-y-3 min-w-0 overflow-hidden">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">DeepBlue Conversation</span>
      </div>
      <CaseDeepBlueCard
        caseId={caseId}
        customerId={detail.customer_id}
        conversations={filtered}
        onUpdate={onUpdate}
      />
    </div>
  );
}

// --- Detail Panel Router ---

function DetailPanel({
  selectedItem,
  mergedTimeline,
  detail,
  caseId,
  onReplyEmail,
  onUpdate,
}: {
  selectedItem: SelectedItem | null;
  mergedTimeline: TimelineEntry[];
  detail: CaseDetail;
  caseId: string;
  onReplyEmail: () => void;
  onUpdate: () => void;
}) {
  if (!selectedItem) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Clock className="h-8 w-8 mb-2 opacity-40" />
        <p className="text-sm">Select an item from the timeline</p>
      </div>
    );
  }

  // New DeepBlue chat — no existing conversation
  if (selectedItem.type === "deepblue_chat" && selectedItem.id === "new") {
    return (
      <DeepBlueDetailPanel
        entry={{ id: "new", type: "deepblue_chat", timestamp: new Date().toISOString(), title: "New Conversation", body: null, actor: null, metadata: {} }}
        detail={detail}
        caseId={caseId}
        onUpdate={onUpdate}
      />
    );
  }

  const entry = mergedTimeline.find(
    (e) => e.id === selectedItem.id && e.type === selectedItem.type
  );
  if (!entry) {
    return (
      <div className="text-sm text-muted-foreground py-8 text-center">
        Item not found
      </div>
    );
  }

  switch (entry.type) {
    case "email":
      return (
        <EmailDetailPanel
          entry={entry}
          detail={detail}
          onReply={onReplyEmail}
        />
      );
    case "job_event":
      return <JobEventDetailPanel entry={entry} detail={detail} />;
    case "invoice_event":
      return <InvoiceEventDetailPanel entry={entry} detail={detail} />;
    case "comment":
      return <CommentDetailPanel entry={entry} />;
    case "internal_message":
      return <InternalMessageDetailPanel entry={entry} />;
    case "deepblue_chat":
      return (
        <DeepBlueDetailPanel
          entry={entry}
          detail={detail}
          caseId={caseId}
          onUpdate={onUpdate}
        />
      );
    default:
      return (
        <div className="space-y-2">
          <p className="text-sm font-medium">{entry.title}</p>
          {entry.body && (
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">
              {entry.body}
            </p>
          )}
        </div>
      );
  }
}

// --- Main Page ---

export default function CaseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { openCompose } = useCompose();
  const teamMembers = useTeamMembers();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  useDeepBlueContext({
    caseId: id,
    customerId: detail?.customer_id || undefined,
  });
  const [loading, setLoading] = useState(true);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleInput, setTitleInput] = useState("");
  const [addingJob, setAddingJob] = useState(false);
  const [newJobDesc, setNewJobDesc] = useState("");
  const [newJobAssignee, setNewJobAssignee] = useState("");
  const [newJobDue, setNewJobDue] = useState("");
  const [newJobNotes, setNewJobNotes] = useState("");
  const [addingTask, setAddingTask] = useState(false);
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [newTaskAssignee, setNewTaskAssignee] = useState("");
  const [newTaskDue, setNewTaskDue] = useState("");
  const [composeOpen, setComposeOpen] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editTaskDesc, setEditTaskDesc] = useState("");
  const [editTaskAssignee, setEditTaskAssignee] = useState("");
  const [editTaskDue, setEditTaskDue] = useState("");
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null);
  const [tasksCollapsed, setTasksCollapsed] = useState(false);

  // Merge DeepBlue conversations into the timeline
  const mergedTimeline = useMemo(() => {
    if (!detail) return [];
    const timeline = [...detail.timeline];

    // Add deepblue_chat entries from conversations
    const deepblueEntries: TimelineEntry[] = (
      detail.deepblue_conversations || []
    ).map((conv) => ({
      id: `deepblue-${conv.id}`,
      type: "deepblue_chat",
      timestamp: conv.created_at,
      title: conv.title || "DeepBlue conversation",
      body:
        conv.messages.length > 0
          ? conv.messages[conv.messages.length - 1].content?.slice(0, 120) ||
            null
          : null,
      actor: null,
      metadata: { conversation_id: conv.id },
    }));

    timeline.push(...deepblueEntries);

    // Sort chronologically, newest first
    timeline.sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );

    return timeline;
  }, [detail]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<CaseDetail>(`/v1/cases/${id}`);
      setDetail(data);
      setTitleInput(data.title);
    } catch {
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-select most recent timeline item on first load
  useEffect(() => {
    if (mergedTimeline.length > 0 && !selectedItem) {
      const first = mergedTimeline[0];
      setSelectedItem({ type: first.type, id: first.id });
    }
  }, [mergedTimeline, selectedItem]);

  const handleAddJob = async () => {
    if (!newJobDesc.trim()) return;
    try {
      await api.post(`/v1/cases/${id}/jobs`, {
        description: newJobDesc.trim(),
        action_type: "repair",
        assigned_to: newJobAssignee || undefined,
        due_date: newJobDue || undefined,
      });
      setNewJobDesc("");
      setNewJobAssignee("");
      setNewJobDue("");
      setNewJobNotes("");
      setAddingJob(false);
      load();
    } catch {
      /* ignore */
    }
  };

  const handleAddTask = async () => {
    if (!newTaskDesc.trim()) return;
    try {
      await api.post(`/v1/cases/${id}/jobs`, {
        description: newTaskDesc.trim(),
        action_type: "follow_up",
        assigned_to: newTaskAssignee || undefined,
        due_date: newTaskDue || undefined,
      });
      setNewTaskDesc("");
      setNewTaskAssignee("");
      setNewTaskDue("");
      setAddingTask(false);
      load();
    } catch {
      /* ignore */
    }
  };

  const handleToggleTask = async (jobId: string, currentStatus: string) => {
    try {
      const newStatus = currentStatus === "done" ? "open" : "done";
      await api.put(`/v1/admin/agent-actions/${jobId}`, {
        status: newStatus,
      });
      load();
    } catch {
      /* ignore */
    }
  };

  const handleUpdateTask = async (
    jobId: string,
    updates: {
      description?: string;
      assigned_to?: string;
      due_date?: string;
    }
  ) => {
    try {
      await api.put(`/v1/admin/agent-actions/${jobId}`, updates);
      setEditingTaskId(null);
      load();
    } catch {
      /* ignore */
    }
  };

  const handleDeleteTask = async (jobId: string) => {
    try {
      await api.put(`/v1/admin/agent-actions/${jobId}`, {
        status: "cancelled",
      });
      load();
    } catch {
      /* ignore */
    }
  };

  const handleSaveTitle = async () => {
    if (!titleInput.trim() || !detail) return;
    try {
      await api.put(`/v1/cases/${id}`, { title: titleInput.trim() });
      setEditingTitle(false);
      load();
    } catch {
      /* ignore */
    }
  };

  const handleReplyEmail = () => {
    if (!detail) return;
    openCompose({
      customerId: detail.customer_id || undefined,
      customerName: detail.customer_name || undefined,
      subject: detail.title,
      caseId: id,
      onSent: load,
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">Case not found</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => router.push("/cases")}
        >
          Back to Cases
        </Button>
      </div>
    );
  }

  const tasks = detail.jobs.filter(
    (j) => !JOB_TYPES.has(j.action_type) && j.status !== "cancelled"
  );
  const doneTasks = tasks.filter((t) => t.status === "done").length;

  return (
    <div className="space-y-4 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 mt-0.5 shrink-0"
          onClick={() => router.push("/cases")}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1"></div>
        {detail.status !== "closed" ? (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 border-amber-300 text-amber-700 hover:bg-amber-50 hover:text-amber-800 shrink-0"
            onClick={async () => {
              try {
                await api.put(`/v1/cases/${id}`, { status: "closed" });
                toast.success("Case closed");
                load();
              } catch (_) {
                toast.error("Failed to close case");
              }
            }}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Close Case
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 shrink-0"
            onClick={async () => {
              try {
                await api.put(`/v1/cases/${id}`, { status: "open" });
                toast.success("Case reopened");
                load();
              } catch (_) {
                toast.error("Failed to reopen case");
              }
            }}
          >
            <FolderOpen className="h-3.5 w-3.5" />
            Reopen
          </Button>
        )}
      </div>
      <div className="flex items-start gap-3">
        <div className="w-8 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-mono text-muted-foreground">
            {detail.case_number}
          </p>
          {editingTitle ? (
            <div className="flex items-center gap-1 mt-0.5">
              <Input
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveTitle();
                  if (e.key === "Escape") setEditingTitle(false);
                }}
                className="h-8 text-lg font-bold max-w-sm"
                autoFocus
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={handleSaveTitle}
              >
                <Check className="h-3.5 w-3.5 text-muted-foreground hover:text-green-600" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => {
                  setEditingTitle(false);
                  setTitleInput(detail.title);
                }}
              >
                <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold">{detail.title}</h1>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setEditingTitle(true)}
              >
                <Pencil className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          )}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <CaseStatusBadge status={detail.status} />
            {detail.customer_name && (
              <Link
                href={`/customers/${detail.customer_id}`}
                className="text-sm text-muted-foreground hover:underline"
              >
                {detail.customer_name}
              </Link>
            )}
            {detail.total_invoiced > 0 && (
              <span className="text-xs text-muted-foreground">
                $
                {detail.total_invoiced.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
                {detail.total_paid > 0 && (
                  <span className="text-green-600 ml-1">
                    (${detail.total_paid.toFixed(2)} paid)
                  </span>
                )}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Tasks — collapsible section between header and columns */}
      {(tasks.length > 0 || addingTask) && (
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setTasksCollapsed(!tasksCollapsed)}
                className="flex items-center gap-1.5 hover:opacity-80"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">
                  Tasks
                  {tasks.length > 0 && (
                    <span className="text-muted-foreground font-normal ml-1.5">
                      {doneTasks}/{tasks.length}
                    </span>
                  )}
                </CardTitle>
                {tasksCollapsed ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                )}
              </button>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[10px] px-1.5"
                onClick={() => setAddingTask(!addingTask)}
              >
                + Add
              </Button>
            </div>
          </CardHeader>
          {!tasksCollapsed && (
            <CardContent className="space-y-1">
              {addingTask && (
                <div className="space-y-1.5 p-2 border rounded-md bg-background">
                  <Input
                    value={newTaskDesc}
                    onChange={(e) => setNewTaskDesc(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && newTaskDesc.trim())
                        handleAddTask();
                      if (e.key === "Escape") setAddingTask(false);
                    }}
                    placeholder="What needs to be done?"
                    className="h-7 text-xs"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <Select
                      value={newTaskAssignee}
                      onValueChange={setNewTaskAssignee}
                    >
                      <SelectTrigger className="h-7 text-xs flex-1">
                        <SelectValue placeholder="Assign to..." />
                      </SelectTrigger>
                      <SelectContent>
                        {teamMembers.map((name) => (
                          <SelectItem key={name} value={name} className="text-xs">
                            {name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      type="date"
                      value={newTaskDue}
                      onChange={(e) => setNewTaskDue(e.target.value)}
                      className="h-7 text-xs w-[130px]"
                    />
                  </div>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={() => {
                        setAddingTask(false);
                        setNewTaskDesc("");
                        setNewTaskAssignee("");
                        setNewTaskDue("");
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={handleAddTask}
                      disabled={!newTaskDesc.trim()}
                    >
                      Add Task
                    </Button>
                  </div>
                </div>
              )}
              {tasks.map((t) => {
                const isOverdue =
                  t.due_date &&
                  new Date(t.due_date) < new Date() &&
                  t.status !== "done";
                const isEditing = editingTaskId === t.id;
                if (isEditing) {
                  return (
                    <div
                      key={t.id}
                      className="space-y-1.5 p-2 border rounded-md bg-background"
                    >
                      <Input
                        value={editTaskDesc}
                        onChange={(e) => setEditTaskDesc(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") setEditingTaskId(null);
                        }}
                        className="h-7 text-xs"
                        autoFocus
                      />
                      <div className="flex gap-1.5">
                        <Select
                          value={editTaskAssignee}
                          onValueChange={setEditTaskAssignee}
                        >
                          <SelectTrigger className="h-7 text-xs flex-1">
                            <SelectValue placeholder="Assign to..." />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem
                              value="__none__"
                              className="text-xs text-muted-foreground"
                            >
                              Unassigned
                            </SelectItem>
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
                        <Input
                          type="date"
                          value={editTaskDue}
                          onChange={(e) => setEditTaskDue(e.target.value)}
                          className="h-7 text-xs w-[130px]"
                        />
                      </div>
                      <div className="flex justify-between">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[10px] text-destructive"
                          onClick={() => {
                            handleDeleteTask(t.id);
                            setEditingTaskId(null);
                          }}
                        >
                          <Trash2 className="h-3 w-3 mr-1" /> Delete
                        </Button>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 text-[10px]"
                            onClick={() => setEditingTaskId(null)}
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            className="h-6 text-[10px]"
                            onClick={() =>
                              handleUpdateTask(t.id, {
                                description:
                                  editTaskDesc.trim() || undefined,
                                assigned_to:
                                  editTaskAssignee === "__none__"
                                    ? ""
                                    : editTaskAssignee || undefined,
                                due_date: editTaskDue || undefined,
                              })
                            }
                          >
                            Save
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                }
                return (
                  <div
                    key={t.id}
                    className="flex items-start gap-2 py-1.5 group"
                  >
                    <button
                      onClick={() => handleToggleTask(t.id, t.status)}
                      className="shrink-0 mt-0.5"
                    >
                      {t.status === "done" ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : (
                        <Circle className="h-4 w-4 text-muted-foreground hover:text-green-500 transition-colors" />
                      )}
                    </button>
                    <div
                      className="flex-1 min-w-0 cursor-pointer"
                      onClick={() => {
                        setEditingTaskId(t.id);
                        setEditTaskDesc(t.description);
                        setEditTaskAssignee(t.assigned_to || "");
                        setEditTaskDue(
                          t.due_date ? t.due_date.split("T")[0] : ""
                        );
                      }}
                    >
                      <span
                        className={`text-xs ${t.status === "done" ? "line-through text-muted-foreground" : ""}`}
                      >
                        {t.description}
                      </span>
                      <div className="flex items-center gap-2 mt-0.5">
                        {t.assigned_to && (
                          <span className="text-[10px] text-muted-foreground">
                            {t.assigned_to}
                          </span>
                        )}
                        {t.due_date && (
                          <span
                            className={`text-[10px] ${isOverdue ? "text-red-500 font-medium" : "text-muted-foreground"}`}
                          >
                            {new Date(t.due_date).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                            })}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          )}
        </Card>
      )}

      {/* Two-column layout: timeline left, detail right */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Timeline — left column (60%) */}
        <div className="w-full lg:w-[60%] min-w-0">
          <Card className="shadow-sm">
            <CardHeader className="pb-0">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" />
                  Timeline
                  {mergedTimeline.length > 0 && (
                    <span className="text-xs font-normal ml-1">
                      ({mergedTimeline.length})
                    </span>
                  )}
                </CardTitle>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] px-1.5"
                    onClick={() =>
                      openCompose({
                        customerId: detail.customer_id || undefined,
                        customerName: detail.customer_name || undefined,
                        subject: detail.title,
                        caseId: id,
                        onSent: load,
                      })
                    }
                  >
                    <Mail className="h-3 w-3 mr-0.5" /> Email
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] px-1.5"
                    onClick={() => setAddingTask(true)}
                  >
                    <CheckCircle2 className="h-3 w-3 mr-0.5" /> Task
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] px-1.5"
                    onClick={() =>
                      router.push(
                        `/invoices/new?type=estimate&customer=${detail.customer_id}&case=${id}`
                      )
                    }
                  >
                    <FileText className="h-3 w-3 mr-0.5" /> Estimate
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] px-1.5"
                    onClick={() => setAddingJob(true)}
                  >
                    <ClipboardList className="h-3 w-3 mr-0.5" /> Job
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] px-1.5"
                    onClick={() => setSelectedItem({ type: "deepblue_chat", id: "new" })}
                  >
                    <Sparkles className="h-3 w-3 mr-0.5" /> DeepBlue
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {/* Add Job form (inline at top of timeline when active) */}
              {addingJob && (
                <div className="space-y-1.5 p-3 border-b bg-muted/30">
                  <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                    New Job
                  </p>
                  <Input
                    value={newJobDesc}
                    onChange={(e) => setNewJobDesc(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        setAddingJob(false);
                        setNewJobDesc("");
                      }
                    }}
                    placeholder="What needs to be done?"
                    className="h-7 text-xs"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <Select
                      value={newJobAssignee}
                      onValueChange={setNewJobAssignee}
                    >
                      <SelectTrigger className="h-7 text-xs flex-1">
                        <SelectValue placeholder="Assign to..." />
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
                    <Input
                      type="date"
                      value={newJobDue}
                      onChange={(e) => setNewJobDue(e.target.value)}
                      className="h-7 text-xs w-[130px]"
                    />
                  </div>
                  <Input
                    value={newJobNotes}
                    onChange={(e) => setNewJobNotes(e.target.value)}
                    placeholder="Description / notes (optional)"
                    className="h-7 text-xs"
                  />
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={() => {
                        setAddingJob(false);
                        setNewJobDesc("");
                        setNewJobAssignee("");
                        setNewJobDue("");
                        setNewJobNotes("");
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      className="h-6 text-[10px]"
                      onClick={handleAddJob}
                      disabled={!newJobDesc.trim()}
                    >
                      Add Job
                    </Button>
                  </div>
                </div>
              )}

              {mergedTimeline.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">
                  No activity yet
                </p>
              ) : (
                <div className="divide-y max-h-[calc(100vh-340px)] overflow-y-auto">
                  {mergedTimeline.map((entry) => (
                    <TimelineRow
                      key={`${entry.type}-${entry.id}`}
                      entry={entry}
                      isSelected={
                        selectedItem?.id === entry.id &&
                        selectedItem?.type === entry.type
                      }
                      onSelect={() =>
                        setSelectedItem({ type: entry.type, id: entry.id })
                      }
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Detail panel — right column (40%) */}
        <div className="w-full lg:w-[40%] min-w-0 overflow-hidden">
          <Card className="shadow-sm lg:sticky lg:top-4">
            <CardContent className="p-4 overflow-x-hidden">
              <DetailPanel
                selectedItem={selectedItem}
                mergedTimeline={mergedTimeline}
                detail={detail}
                caseId={id}
                onReplyEmail={handleReplyEmail}
                onUpdate={load}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <ComposeMessage
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSent={() => {
          setComposeOpen(false);
          load();
        }}
        defaultCaseId={id}
        defaultCustomerId={detail.customer_id || undefined}
      />
    </div>
  );
}
