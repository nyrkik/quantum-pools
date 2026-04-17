"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Send,
  Inbox,
  ClipboardList,
  DollarSign,
  MessageSquare,
  CheckCircle2,
  X,
  ChevronDown,
  ChevronUp,
  Circle,
  ExternalLink,
  ArrowRightLeft,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";

// --- Types (shared with case detail page) ---

export interface CaseJob {
  id: string;
  description: string;
  action_type: string;
  status: string;
  assigned_to: string | null;
  due_date: string | null;
  completed_at: string | null;
  created_at: string;
  notes: string | null;
  closed_by_case_cascade?: boolean;
  tasks: { id: string; title: string; status: string; assigned_to: string | null; sort_order: number }[];
  comments: { id: string; author: string; text: string; created_at: string }[];
}

export interface CaseMessage {
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

export interface CaseThread {
  id: string;
  subject: string | null;
  contact_email: string;
  status: string;
  message_count: number;
  messages: CaseMessage[];
}

export interface CaseInvoice {
  id: string;
  invoice_number: string | null;
  document_type: string;
  subject: string | null;
  status: string;
  total: number;
  balance: number;
  created_at: string;
  approved_at: string | null;
  line_items: { description: string; quantity: number; unit_price: number; amount: number }[];
}

export interface TimelineEntry {
  id: string;
  type: string;
  timestamp: string;
  title: string;
  body: string | null;
  actor: string | null;
  metadata: Record<string, unknown>;
}

export interface DeepBlueConversation {
  id: string;
  title: string;
  user_id: string;
  message_count: number;
  messages: { role: string; content: string; timestamp: string }[];
  created_at: string;
  updated_at: string;
}

export interface CaseDetail {
  id: string;
  case_number: string;
  title: string;
  customer_id: string | null;
  customer_name: string | null;
  billing_name: string | null;
  status: string;
  priority: string;
  assigned_to_name: string | null;
  manager_name: string | null;
  current_actor_name: string | null;
  source: string;
  job_count: number;
  open_job_count: number;
  total_invoiced: number;
  total_paid: number;
  flags: {
    estimate_approved: boolean;
    estimate_rejected: boolean;
    payment_received: boolean;
    customer_replied: boolean;
    jobs_complete: boolean;
    invoice_overdue: boolean;
    stale: boolean;
  };
  created_at: string;
  updated_at: string;
  jobs: CaseJob[];
  threads: CaseThread[];
  invoices: CaseInvoice[];
  deepblue_conversations: DeepBlueConversation[];
  internal_threads: {
    id: string;
    subject: string | null;
    message_count: number;
    messages: { id: string; from_user_id: string; text: string; created_at: string }[];
  }[];
  timeline: TimelineEntry[];
}

// --- Helpers ---

export const JOB_TYPES = new Set(["repair", "site_visit", "bid", "equipment"]);

const STATUS_LABELS: Record<string, string> = {
  new: "New", triaging: "Triaging", scoping: "Scoping",
  pending_approval: "Pending Approval", approved: "Approved",
  in_progress: "In Progress", pending_payment: "Pending Payment",
  closed: "Closed", cancelled: "Cancelled",
};

export function formatTime(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " " +
         d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

// --- Components ---

export function CaseStatusBadge({ status }: { status: string }) {
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

export function TimelineItem({ entry, jobs, invoices }: { entry: TimelineEntry; jobs: CaseJob[]; invoices: CaseInvoice[] }) {
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

          {expanded && (
            <div className="mt-2">
              {isEmail && entry.body && (
                <div className={`text-sm whitespace-pre-wrap rounded-md p-3 ${
                  isOutbound ? "bg-green-50 dark:bg-green-950/30 border-l-2 border-green-400" :
                  isInbound ? "bg-blue-50 dark:bg-blue-950/30 border-l-2 border-blue-400" :
                  "bg-muted/50"
                }`}>
                  {entry.body}
                </div>
              )}

              {entry.type === "comment" && entry.body && (
                <div className="text-sm whitespace-pre-wrap rounded-md p-3 bg-muted/50">
                  {entry.body}
                  {typeof entry.metadata?.job_description === "string" && (
                    <p className="text-[10px] text-muted-foreground mt-2">on: {entry.metadata.job_description}</p>
                  )}
                </div>
              )}

              {isInternal && entry.body && (
                <div className="text-sm whitespace-pre-wrap rounded-md p-3 bg-purple-50 dark:bg-purple-950/30 border-l-2 border-purple-400">
                  {entry.body}
                </div>
              )}

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

export function JobCard({ job }: { job: CaseJob }) {
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

export function InvoiceCard({ invoice, onUpdate }: { invoice: CaseInvoice; onUpdate?: () => void }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const [converting, setConverting] = useState(false);

  // The backend allows convert only for approved estimates.
  const canConvert = invoice.document_type === "estimate" && !!invoice.approved_at;

  const handleConvert = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (converting) return;
    setConverting(true);
    try {
      await api.post(`/v1/invoices/${invoice.id}/convert-to-invoice`, {});
      toast.success("Estimate converted to invoice");
      onUpdate?.();
    } catch {
      toast.error("Failed to convert to invoice");
    } finally {
      setConverting(false);
    }
  };

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
          <div className="flex items-center gap-1">
            {canConvert && (
              <Button
                size="sm"
                className="h-6 text-[10px] px-1.5"
                onClick={handleConvert}
                disabled={converting}
              >
                {converting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <ArrowRightLeft className="h-3 w-3 mr-1" />}
                Convert to Invoice
              </Button>
            )}
            <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={(e) => { e.stopPropagation(); router.push(`/invoices/${invoice.id}`); }}>
              <ExternalLink className="h-3 w-3 mr-1" /> Open Full View
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
