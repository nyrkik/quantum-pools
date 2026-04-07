"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowLeft,
  FolderOpen,
  Mail,
  Send,
  Inbox,
  ClipboardList,
  FileText,
  DollarSign,
  MessageSquare,
  Loader2,
  Pencil,
  Check,
  CheckCircle2,
  X,
  ChevronDown,
  ChevronUp,
  Circle,
  Clock,
  ExternalLink,
  Trash2,
  Plus,
} from "lucide-react";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
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

// --- Types ---

interface CaseJob {
  id: string;
  description: string;
  action_type: string;
  status: string;
  assigned_to: string | null;
  due_date: string | null;
  completed_at: string | null;
  created_at: string;
  notes: string | null;
  tasks: { id: string; title: string; status: string; assigned_to: string | null; sort_order: number }[];
  comments: { id: string; author: string; text: string; created_at: string }[];
}

interface CaseMessage {
  id: string;
  direction: string;
  from_email: string;
  to_email: string;
  subject: string | null;
  body: string | null;
  status: string;
  received_at: string | null;
  sent_at: string | null;
}

interface CaseThread {
  id: string;
  subject: string | null;
  contact_email: string;
  status: string;
  message_count: number;
  messages: CaseMessage[];
}

interface CaseInvoice {
  id: string;
  invoice_number: string | null;
  document_type: string;
  subject: string | null;
  status: string;
  total: number;
  balance: number;
  created_at: string;
  line_items: { description: string; quantity: number; unit_price: number; amount: number }[];
}

interface TimelineEntry {
  id: string;
  type: string;
  timestamp: string;
  title: string;
  body: string | null;
  actor: string | null;
  metadata: Record<string, unknown>;
}

interface DeepBlueConversation {
  id: string;
  title: string;
  user_id: string;
  message_count: number;
  messages: { role: string; content: string; timestamp: string }[];
  created_at: string;
  updated_at: string;
}

interface CaseDetail {
  id: string;
  case_number: string;
  title: string;
  customer_id: string | null;
  customer_name: string | null;
  status: string;
  priority: string;
  assigned_to_name: string | null;
  source: string;
  job_count: number;
  open_job_count: number;
  total_invoiced: number;
  total_paid: number;
  created_at: string;
  updated_at: string;
  jobs: CaseJob[];
  threads: CaseThread[];
  invoices: CaseInvoice[];
  deepblue_conversations: DeepBlueConversation[];
  timeline: TimelineEntry[];
}

// --- Helpers ---

// Action types that render as full job cards (field work with scope)
const JOB_TYPES = new Set(["repair", "site_visit", "bid", "equipment"]);

const STATUS_LABELS: Record<string, string> = {
  new: "New", triaging: "Triaging", scoping: "Scoping",
  pending_approval: "Pending Approval", approved: "Approved",
  in_progress: "In Progress", pending_payment: "Pending Payment",
  closed: "Closed", cancelled: "Cancelled",
};

function CaseStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    new: "bg-blue-100 text-blue-800", in_progress: "bg-blue-100 text-blue-800",
    scoping: "bg-amber-100 text-amber-800", pending_approval: "border-amber-400 text-amber-600",
    approved: "bg-green-100 text-green-800", pending_payment: "border-orange-400 text-orange-600",
    closed: "bg-slate-100 text-slate-600", cancelled: "bg-red-100 text-red-600",
  };
  return (
    <Badge variant={status.startsWith("pending") ? "outline" : "secondary"} className={colors[status] || ""}>
      {STATUS_LABELS[status] || status.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
    </Badge>
  );
}

function formatTime(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " " +
         d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

// --- Expandable Timeline Entry ---

function TimelineItem({ entry, jobs, invoices }: { entry: TimelineEntry; jobs: CaseJob[]; invoices: CaseInvoice[] }) {
  const [expanded, setExpanded] = useState(false);
  const isEmail = entry.type === "email";
  const isOutbound = entry.metadata?.direction === "outbound";
  const isInbound = entry.metadata?.direction === "inbound";
  const isJobEvent = entry.type === "job_event";
  const isCompleted = isJobEvent && entry.metadata?.event === "completed";
  const isCancelled = isJobEvent && entry.metadata?.event === "cancelled";
  const isInvoiceEvent = entry.type === "invoice_event";
  const isInternal = entry.type === "internal_message";

  const iconColor = isEmail
    ? (isOutbound ? "text-green-500" : "text-blue-500")
    : isInvoiceEvent ? "text-emerald-500"
    : isJobEvent ? (isCompleted ? "text-green-500" : isCancelled ? "text-slate-300" : "text-amber-500")
    : isInternal ? "text-purple-500"
    : entry.type === "comment" ? "text-slate-400"
    : "text-amber-500";

  const Icon = isEmail ? (isOutbound ? Send : Inbox)
    : isInvoiceEvent ? DollarSign
    : isJobEvent ? (isCompleted ? CheckCircle2 : isCancelled ? X : ClipboardList)
    : isInternal ? MessageSquare
    : MessageSquare;

  // Resolve linked objects for rich expand
  const linkedJob = isJobEvent ? jobs.find(j => j.id === entry.metadata?.action_id) : null;
  const linkedInvoice = isInvoiceEvent ? invoices.find(i => i.id === entry.metadata?.invoice_id) : null;
  const hasExpandable = !!(entry.body) || !!linkedJob || !!linkedInvoice;

  return (
    <div
      className={`py-2 ${hasExpandable ? "cursor-pointer" : ""}`}
      onClick={() => hasExpandable && setExpanded(!expanded)}
    >
      <div className="flex gap-3">
        <div className={`mt-0.5 shrink-0 ${iconColor}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <p className={`text-sm truncate ${isEmail ? "font-medium" : ""} ${isCancelled ? "line-through text-muted-foreground" : ""}`}>{entry.title}</p>
              {hasExpandable && (
                expanded ? <ChevronUp className="h-3 w-3 text-muted-foreground shrink-0" /> : <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
              )}
            </div>
            <span className="text-[10px] text-muted-foreground shrink-0">{formatTime(entry.timestamp)}</span>
          </div>

          {/* Collapsed preview */}
          {!expanded && (
            <>
              {entry.body && <p className="text-xs text-muted-foreground truncate mt-0.5">{entry.body.slice(0, 120)}</p>}
              {linkedJob && !entry.body && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {linkedJob.assigned_to && <span>{linkedJob.assigned_to}</span>}
                  {linkedJob.tasks.length > 0 && <span> — {linkedJob.tasks.filter(t => t.status === "done").length}/{linkedJob.tasks.length} tasks</span>}
                </p>
              )}
            </>
          )}

          {/* Expanded detail */}
          {expanded && (
            <div className="mt-2">
              {/* Email body */}
              {isEmail && entry.body && (
                <div className={`text-sm whitespace-pre-wrap rounded-md p-3 ${
                  isOutbound ? "bg-green-50 dark:bg-green-950/30 border-l-2 border-green-400" :
                  isInbound ? "bg-blue-50 dark:bg-blue-950/30 border-l-2 border-blue-400" :
                  "bg-muted/50"
                }`}>
                  {entry.body}
                </div>
              )}

              {/* Comment body */}
              {entry.type === "comment" && entry.body && (
                <div className="text-sm whitespace-pre-wrap rounded-md p-3 bg-muted/50">
                  {entry.body}
                  {typeof entry.metadata?.job_description === "string" && (
                    <p className="text-[10px] text-muted-foreground mt-2">on: {entry.metadata.job_description}</p>
                  )}
                </div>
              )}

              {/* Internal team message */}
              {isInternal && entry.body && (
                <div className="text-sm whitespace-pre-wrap rounded-md p-3 bg-purple-50 dark:bg-purple-950/30 border-l-2 border-purple-400">
                  {entry.body}
                </div>
              )}

              {/* Job detail — matches JobCard sidebar expand */}
              {linkedJob && (
                <div className={`rounded-md border bg-muted/20 ${linkedJob.status === "done" ? "opacity-60" : ""}`}>
                  <div className="px-3 py-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <ActionStatusIcon status={linkedJob.status} />
                        <ActionTypeBadge type={linkedJob.action_type} />
                        {linkedJob.assigned_to && <span className="text-xs text-muted-foreground">→ {linkedJob.assigned_to}</span>}
                      </div>
                      {linkedJob.due_date && (
                        <span className="text-[10px] text-muted-foreground">{new Date(linkedJob.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
                      )}
                    </div>
                    <p className={`text-sm ${linkedJob.status === "done" ? "line-through text-muted-foreground" : ""}`}>{linkedJob.description}</p>
                  </div>
                  {(linkedJob.tasks.length > 0 || linkedJob.comments.length > 0 || linkedJob.notes) && (
                    <div className="border-t px-3 py-2 space-y-3">
                      {linkedJob.tasks.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Tasks</p>
                          {linkedJob.tasks.sort((a, b) => a.sort_order - b.sort_order).map((t) => (
                            <div key={t.id} className="flex items-center gap-2 text-xs">
                              {t.status === "done" ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                              ) : (
                                <Circle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                              )}
                              <span className={t.status === "done" ? "line-through text-muted-foreground" : ""}>{t.title}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {linkedJob.comments.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Notes</p>
                          {linkedJob.comments.slice(-5).map((c) => (
                            <div key={c.id} className="text-xs">
                              <span className="font-medium">{c.author}:</span>{" "}
                              <span className="text-muted-foreground">{c.text.slice(0, 200)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {linkedJob.notes && (
                        <p className="text-xs text-muted-foreground">{linkedJob.notes}</p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Invoice detail */}
              {linkedInvoice && (
                <div className="rounded-md p-3 bg-muted/50 space-y-1.5">
                  {linkedInvoice.subject && <p className="text-xs text-muted-foreground">{linkedInvoice.subject}</p>}
                  <Badge variant="outline" className="text-[9px] h-4 px-1">
                    {linkedInvoice.status.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                  </Badge>
                  {linkedInvoice.line_items.length > 0 && (
                    <div className="space-y-0.5 pt-1">
                      {linkedInvoice.line_items.map((li, i) => (
                        <div key={i} className="flex justify-between text-xs">
                          <span className="truncate flex-1">{li.description}</span>
                          <span className="font-medium ml-2">${li.amount.toFixed(2)}</span>
                        </div>
                      ))}
                      <div className="flex justify-between text-xs font-medium border-t pt-1">
                        <span>Total</span>
                        <span>${linkedInvoice.total.toFixed(2)}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Inline Job Card ---

function JobCard({ job }: { job: CaseJob }) {
  const [expanded, setExpanded] = useState(false);
  const doneTasks = job.tasks.filter(t => t.status === "done").length;
  const totalTasks = job.tasks.length;

  return (
    <div className={`border rounded-lg ${job.status === "done" ? "opacity-60" : ""}`}>
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <ActionStatusIcon status={job.status} />
          <div className="min-w-0">
            <p className={`text-sm truncate ${job.status === "done" ? "line-through text-muted-foreground" : "font-medium"}`}>
              {job.description}
            </p>
            <div className="flex items-center gap-2 mt-0.5">
              <ActionTypeBadge type={job.action_type} />
              {job.assigned_to && <span className="text-[10px] text-muted-foreground">{job.assigned_to}</span>}
              {totalTasks > 0 && (
                <span className="text-[10px] text-muted-foreground">{doneTasks}/{totalTasks} tasks</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {job.due_date && (
            <span className="text-[10px] text-muted-foreground">{new Date(job.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
          )}
          {expanded ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t px-3 py-2 space-y-3 bg-muted/20">
          {/* Tasks checklist */}
          {job.tasks.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Tasks</p>
              {job.tasks.sort((a, b) => a.sort_order - b.sort_order).map((t) => (
                <div key={t.id} className="flex items-center gap-2 text-xs">
                  {t.status === "done" ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  )}
                  <span className={t.status === "done" ? "line-through text-muted-foreground" : ""}>{t.title}</span>
                </div>
              ))}
            </div>
          )}

          {/* Work notes (comments) */}
          {job.comments.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Notes</p>
              {job.comments.slice(-5).map((c) => (
                <div key={c.id} className="text-xs">
                  <span className="font-medium">{c.author}:</span>{" "}
                  <span className="text-muted-foreground">{c.text.slice(0, 200)}</span>
                </div>
              ))}
            </div>
          )}

          {job.notes && (
            <p className="text-xs text-muted-foreground">{job.notes}</p>
          )}
        </div>
      )}
    </div>
  );
}

// --- Inline Invoice Card ---

function InvoiceCard({ invoice, router }: { invoice: CaseInvoice; router: ReturnType<typeof useRouter> }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border rounded-lg">
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <DollarSign className="h-3.5 w-3.5 text-emerald-600" />
          <div>
            <span className="text-sm font-medium">{invoice.invoice_number || "Draft"}</span>
            <span className="text-xs text-muted-foreground ml-2">
              {invoice.document_type === "estimate" ? "Estimate" : "Invoice"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-sm font-medium">${invoice.total.toFixed(2)}</span>
          <Badge variant="outline" className="text-[9px] h-4 px-1">
            {invoice.status.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
          </Badge>
          {expanded ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t px-3 py-2 bg-muted/20 space-y-2">
          {invoice.subject && <p className="text-xs text-muted-foreground">{invoice.subject}</p>}
          {invoice.line_items.length > 0 && (
            <div className="space-y-1">
              {invoice.line_items.map((li, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="truncate flex-1">{li.description}</span>
                  <span className="text-muted-foreground ml-2 shrink-0">
                    {li.quantity > 1 ? `${li.quantity} x ` : ""}${li.unit_price.toFixed(2)}
                  </span>
                  <span className="font-medium ml-2 shrink-0">${li.amount.toFixed(2)}</span>
                </div>
              ))}
              <div className="flex justify-between text-xs font-medium border-t pt-1">
                <span>Total</span>
                <span>${invoice.total.toFixed(2)}</span>
              </div>
            </div>
          )}
          <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={(e) => { e.stopPropagation(); router.push(`/invoices/${invoice.id}`); }}>
            <ExternalLink className="h-3 w-3 mr-1" /> Open Full View
          </Button>
        </div>
      )}
    </div>
  );
}

// --- Main Page ---

export default function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { openCompose } = useCompose();
  const teamMembers = useTeamMembers();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  useDeepBlueContext({ caseId: id, customerId: detail?.customer_id || undefined });
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

  useEffect(() => { load(); }, [load]);

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
    } catch { /* ignore */ }
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
    } catch { /* ignore */ }
  };

  const handleToggleTask = async (jobId: string, currentStatus: string) => {
    try {
      const newStatus = currentStatus === "done" ? "open" : "done";
      await api.put(`/v1/admin/agent-actions/${jobId}`, { status: newStatus });
      load();
    } catch { /* ignore */ }
  };

  const handleUpdateTask = async (jobId: string, updates: { description?: string; assigned_to?: string; due_date?: string }) => {
    try {
      await api.put(`/v1/admin/agent-actions/${jobId}`, updates);
      setEditingTaskId(null);
      load();
    } catch { /* ignore */ }
  };

  const handleDeleteTask = async (jobId: string) => {
    try {
      await api.put(`/v1/admin/agent-actions/${jobId}`, { status: "cancelled" });
      load();
    } catch { /* ignore */ }
  };

  const handleSaveTitle = async () => {
    if (!titleInput.trim() || !detail) return;
    try {
      await api.put(`/v1/cases/${id}`, { title: titleInput.trim() });
      setEditingTitle(false);
      load();
    } catch { /* ignore */ }
  };

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  if (!detail) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">Case not found</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => router.push("/cases")}>Back to Cases</Button>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8 mt-0.5 shrink-0" onClick={() => router.push("/cases")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-mono text-muted-foreground">{detail.case_number}</p>
          {editingTitle ? (
            <div className="flex items-center gap-1 mt-0.5">
              <Input
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSaveTitle(); if (e.key === "Escape") setEditingTitle(false); }}
                className="h-8 text-lg font-bold max-w-sm"
                autoFocus
              />
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleSaveTitle}>
                <Check className="h-3.5 w-3.5 text-muted-foreground hover:text-green-600" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setEditingTitle(false); setTitleInput(detail.title); }}>
                <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold">{detail.title}</h1>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingTitle(true)}>
                <Pencil className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          )}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <CaseStatusBadge status={detail.status} />
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-xs gap-1"
              onClick={() => openCompose({
                customerId: detail.customer_id || undefined,
                customerName: detail.customer_name || undefined,
                subject: detail.title,
                caseId: id,
                onSent: load,
              })}
            >
              <Mail className="h-3 w-3" />
              Send Email
            </Button>
            {detail.customer_name && (
              <Link href={`/customers/${detail.customer_id}`} className="text-sm text-muted-foreground hover:underline">
                {detail.customer_name}
              </Link>
            )}
            {detail.total_invoiced > 0 && (
              <span className="text-xs text-muted-foreground">
                ${detail.total_invoiced.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                {detail.total_paid > 0 && <span className="text-green-600 ml-1">(${detail.total_paid.toFixed(2)} paid)</span>}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Two-column layout: timeline left, panels right */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Timeline — left / full on mobile */}
        <div className="flex-1 min-w-0 order-2 lg:order-1">
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              {detail.timeline.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">No activity yet</p>
              ) : (
                <div className="divide-y">
                  {detail.timeline.map((entry) => (
                    <TimelineItem key={entry.id} entry={entry} jobs={detail.jobs} invoices={detail.invoices} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Side panels — right / top on mobile */}
        <div className="lg:w-80 xl:w-96 shrink-0 space-y-4 order-1 lg:order-2">
          {/* Tasks */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />
                  Tasks
                </CardTitle>
                <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setAddingTask(!addingTask)}>
                  + Add
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-1">
              {addingTask && (
                <div className="space-y-1.5 p-2 border rounded-md bg-background">
                  <Input
                    value={newTaskDesc}
                    onChange={(e) => setNewTaskDesc(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && newTaskDesc.trim()) handleAddTask(); if (e.key === "Escape") setAddingTask(false); }}
                    placeholder="What needs to be done?"
                    className="h-7 text-xs"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <Select value={newTaskAssignee} onValueChange={setNewTaskAssignee}>
                      <SelectTrigger className="h-7 text-xs flex-1">
                        <SelectValue placeholder="Assign to..." />
                      </SelectTrigger>
                      <SelectContent>
                        {teamMembers.map((name) => (
                          <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
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
                    <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => { setAddingTask(false); setNewTaskDesc(""); setNewTaskAssignee(""); setNewTaskDue(""); }}>
                      Cancel
                    </Button>
                    <Button size="sm" className="h-6 text-[10px]" onClick={handleAddTask} disabled={!newTaskDesc.trim()}>
                      Add Task
                    </Button>
                  </div>
                </div>
              )}
              {detail.jobs.filter(j => !JOB_TYPES.has(j.action_type) && j.status !== "cancelled").map((t) => {
                const isOverdue = t.due_date && new Date(t.due_date) < new Date() && t.status !== "done";
                const isEditing = editingTaskId === t.id;
                if (isEditing) {
                  return (
                    <div key={t.id} className="space-y-1.5 p-2 border rounded-md bg-background">
                      <Input value={editTaskDesc} onChange={(e) => setEditTaskDesc(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setEditingTaskId(null); }} className="h-7 text-xs" autoFocus />
                      <div className="flex gap-1.5">
                        <Select value={editTaskAssignee} onValueChange={setEditTaskAssignee}>
                          <SelectTrigger className="h-7 text-xs flex-1"><SelectValue placeholder="Assign to..." /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__" className="text-xs text-muted-foreground">Unassigned</SelectItem>
                            {teamMembers.map((name) => (<SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>))}
                          </SelectContent>
                        </Select>
                        <Input type="date" value={editTaskDue} onChange={(e) => setEditTaskDue(e.target.value)} className="h-7 text-xs w-[130px]" />
                      </div>
                      <div className="flex justify-between">
                        <Button variant="ghost" size="sm" className="h-6 text-[10px] text-destructive" onClick={() => { handleDeleteTask(t.id); setEditingTaskId(null); }}><Trash2 className="h-3 w-3 mr-1" /> Delete</Button>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => setEditingTaskId(null)}>Cancel</Button>
                          <Button size="sm" className="h-6 text-[10px]" onClick={() => handleUpdateTask(t.id, { description: editTaskDesc.trim() || undefined, assigned_to: editTaskAssignee === "__none__" ? "" : editTaskAssignee || undefined, due_date: editTaskDue || undefined })}>Save</Button>
                        </div>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={t.id} className="flex items-start gap-2 py-1.5 group">
                    <button onClick={() => handleToggleTask(t.id, t.status)} className="shrink-0 mt-0.5">
                      {t.status === "done" ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <Circle className="h-4 w-4 text-muted-foreground hover:text-green-500 transition-colors" />}
                    </button>
                    <div className="flex-1 min-w-0 cursor-pointer" onClick={() => { setEditingTaskId(t.id); setEditTaskDesc(t.description); setEditTaskAssignee(t.assigned_to || ""); setEditTaskDue(t.due_date ? t.due_date.split("T")[0] : ""); }}>
                      <span className={`text-xs ${t.status === "done" ? "line-through text-muted-foreground" : ""}`}>{t.description}</span>
                      <div className="flex items-center gap-2 mt-0.5">
                        {t.assigned_to && <span className="text-[10px] text-muted-foreground">{t.assigned_to}</span>}
                        {t.due_date && <span className={`text-[10px] ${isOverdue ? "text-red-500 font-medium" : "text-muted-foreground"}`}>{new Date(t.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Jobs */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <ClipboardList className="h-3.5 w-3.5 text-muted-foreground" />
                  Jobs
                </CardTitle>
                <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setAddingJob(!addingJob)}>
                  + Add
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {addingJob && (
                <div className="space-y-1.5 p-2 border rounded-md bg-background">
                  <Input
                    value={newJobDesc}
                    onChange={(e) => setNewJobDesc(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Escape") { setAddingJob(false); setNewJobDesc(""); } }}
                    placeholder="What needs to be done?"
                    className="h-7 text-xs"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <Select value={newJobAssignee} onValueChange={setNewJobAssignee}>
                      <SelectTrigger className="h-7 text-xs flex-1">
                        <SelectValue placeholder="Assign to..." />
                      </SelectTrigger>
                      <SelectContent>
                        {teamMembers.map((name) => (
                          <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
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
                    <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => { setAddingJob(false); setNewJobDesc(""); setNewJobAssignee(""); setNewJobDue(""); setNewJobNotes(""); }}>
                      Cancel
                    </Button>
                    <Button size="sm" className="h-6 text-[10px]" onClick={handleAddJob} disabled={!newJobDesc.trim()}>
                      Add Job
                    </Button>
                  </div>
                </div>
              )}
              {detail.jobs.filter(j => JOB_TYPES.has(j.action_type)).map((j) => (
                <JobCard key={j.id} job={j} />
              ))}
            </CardContent>
          </Card>

          {/* Messages */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                  Messages
                </CardTitle>
                <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setComposeOpen(true)}>
                  + New
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {((detail as any).internal_threads || []).map((it: any) => (
                <div key={it.id} className="py-1 px-2 rounded-md bg-muted/30 text-xs">
                  <p className="font-medium truncate">{it.subject || "Team discussion"}</p>
                  <span className="text-muted-foreground">{it.message_count} message{it.message_count !== 1 ? "s" : ""}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Emails */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                Emails
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {detail.threads.map((t) => (
                <div key={t.id} className="py-1 px-2 rounded-md bg-muted/30 text-xs">
                  <p className="font-medium truncate">{t.subject || "(no subject)"}</p>
                  <span className="text-muted-foreground">{t.contact_email} — {t.message_count} message{t.message_count !== 1 ? "s" : ""}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Documents */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  Documents
                </CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px] px-1.5"
                  onClick={() => router.push(`/invoices/new?type=estimate&customer=${detail.customer_id}&case=${id}`)}
                >
                  <Plus className="h-3 w-3 mr-0.5" /> Estimate
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {detail.invoices.map((inv) => (
                <InvoiceCard key={inv.id} invoice={inv} router={router} />
              ))}
            </CardContent>
          </Card>

          {/* DeepBlue */}
          <CaseDeepBlueCard
            caseId={id}
            customerId={detail.customer_id}
            conversations={detail.deepblue_conversations || []}
            onUpdate={load}
          />
        </div>
      </div>

      <ComposeMessage
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSent={() => { setComposeOpen(false); load(); }}
        defaultCaseId={id}
        defaultCustomerId={detail.customer_id || undefined}
      />
    </div>
  );
}
