"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Loader2,
  Send,
  CheckCircle2,
  Trash2,
  DollarSign,
  Play,
  ChevronDown,
  ChevronUp,
  Mail,
  MessageSquare,
  ListChecks,
  ClipboardList,
  Package,
  Lightbulb,
  Pencil,
  Link2,
  X,
  Search,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCompose } from "@/components/email/compose-provider";
import { formatTime, formatDueDate, isOverdue } from "@/lib/format";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
import { TasksSection } from "@/components/jobs/tasks-section";
import type { ActionDetail } from "@/types/agent";
import { JobPartsSection } from "@/components/jobs/job-parts-section";
import { useTeamMembers, ACTION_TYPES } from "@/hooks/use-team-members";

// --- Utility components ---

function DraftReplyBlock({ threadId, draft, onAction }: { threadId: string; draft: string; onAction: () => void }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(draft);
  const [reviseInstruction, setReviseInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [sending, setSending] = useState(false);

  const handleRevise = async () => {
    if (!reviseInstruction.trim()) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-threads/${threadId}/revise-draft`, {
        draft: editText, instruction: reviseInstruction,
      });
      setEditText(result.draft);
      setReviseInstruction("");
    } catch { toast.error("Failed to revise"); }
    finally { setRevising(false); }
  };

  const handleSaveDraft = async () => {
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/save-draft`, { response_text: editText });
      toast.success("Draft saved");
      setEditing(false);
      onAction();
    } catch { toast.error("Failed to save"); }
  };

  const handleSend = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/approve`, { response_text: editing ? editText : undefined });
      toast.success("Reply sent");
      setEditing(false);
      onAction();
    } catch { toast.error("Failed to send"); }
    finally { setSending(false); }
  };

  return (
    <>
      {/* Inline draft display */}
      {!editing && (
        <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-amber-700 dark:text-amber-400">Draft reply (not sent)</span>
            <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => { setEditText(draft); setEditing(true); }}>
              <Pencil className="h-3 w-3 mr-1" />Edit
            </Button>
          </div>
          <p className="text-sm whitespace-pre-wrap">{draft}</p>
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Textarea
                value={reviseInstruction}
                onChange={(e) => setReviseInstruction(e.target.value)}
                placeholder="Tell AI how to change it..."
                className="text-sm min-h-[2rem] resize-none"
                rows={1}
                onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleRevise(); } }}
              />
            </div>
            <Button variant="outline" size="sm" className="h-8" onClick={handleRevise} disabled={revising || !reviseInstruction.trim()}>
              {revising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
            </Button>
          </div>
          <Button onClick={handleSend} disabled={sending} size="sm">
            {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
            Approve & Send
          </Button>
        </div>
      )}

      {/* Full-screen editor — bottom sheet mobile, centered desktop */}
      {editing && (
        <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => { setEditing(false); setEditText(draft); }} />
          <div className="relative w-full sm:max-w-lg max-h-[95vh] sm:max-h-[85vh] bg-background border-t sm:border sm:rounded-lg shadow-xl flex flex-col rounded-t-xl sm:rounded-xl animate-in slide-in-from-bottom sm:zoom-in-95 duration-200">
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
              <p className="text-sm font-semibold">Edit Draft</p>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => { setEditing(false); setEditText(draft); }}>Cancel</Button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              <Textarea value={editText} onChange={(e) => setEditText(e.target.value)} className="text-sm min-h-[200px] sm:min-h-[250px]" rows={12} autoFocus />
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Textarea value={reviseInstruction} onChange={(e) => setReviseInstruction(e.target.value)} placeholder="Tell AI how to change it..."
                    className="text-sm min-h-[2rem] resize-none" rows={1}
                    onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleRevise(); } }} />
                </div>
                <Button variant="outline" size="sm" className="h-8" onClick={handleRevise} disabled={revising || !reviseInstruction.trim()}>
                  {revising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
                </Button>
              </div>
            </div>
            <div className="px-4 py-3 border-t shrink-0 flex gap-2">
              <Button variant="outline" onClick={handleSaveDraft} className="flex-1">Save Draft</Button>
              <Button onClick={handleSend} disabled={sending} className="flex-1">
                {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
                Send
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function DraftEmailBlock({ commentId, isSent, to: origTo, subject: origSubject, body: origBody, createdAt, actionId, onSent }: {
  commentId: string; isSent: boolean; to: string; subject: string; body: string; createdAt: string; actionId: string; onSent: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editTo, setEditTo] = useState(origTo);
  const [editSubject, setEditSubject] = useState(origSubject);
  const [editBody, setEditBody] = useState(origBody);
  const [sendingDraft, setSendingDraft] = useState(false);
  const compose = useCompose();

  const handleSend = async () => {
    setSendingDraft(true);
    try {
      await api.post("/v1/email/compose", {
        to: editTo,
        subject: editSubject,
        body: editBody,
        job_id: actionId,
      });
      toast.success("Email sent");
      onSent();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingDraft(false);
    }
  };

  const handleDiscard = () => {
    setEditTo(origTo);
    setEditSubject(origSubject);
    setEditBody(origBody);
    setEditing(false);
  };

  return (
    <div className={`rounded-md p-3 border ${isSent ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800" : "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800"}`}>
      <div className="flex items-center justify-between mb-1">
        <span className={`text-xs font-medium ${isSent ? "text-green-700 dark:text-green-400" : "text-blue-700 dark:text-blue-400"}`}>
          {isSent ? "✓ Email Sent" : editing ? "Editing Draft" : "Draft Email"}
        </span>
        <span className="text-[10px] text-muted-foreground">{formatTime(createdAt)}</span>
      </div>

      {editing ? (
        <div className="space-y-2">
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground">To</label>
            <Input value={editTo} onChange={(e) => setEditTo(e.target.value)} className="h-7 text-xs" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground">Subject</label>
            <Input value={editSubject} onChange={(e) => setEditSubject(e.target.value)} className="h-7 text-xs" />
          </div>
          <Textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} className="text-sm min-h-[120px] resize-none" />
          <div className="flex items-center justify-between">
            <Button size="sm" variant="ghost" className="text-xs" onClick={handleDiscard}>Discard</Button>
            <Button size="sm" variant="default" className="text-xs" onClick={handleSend} disabled={sendingDraft || !editTo.trim()}>
              {sendingDraft ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Send className="h-3 w-3 mr-1" />}
              Send
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="text-xs text-muted-foreground mb-1">To: {origTo}</p>
          <p className="text-xs font-medium mb-1">Subject: {origSubject}</p>
          <p className="text-sm whitespace-pre-wrap">{origBody}</p>
          {!isSent && (
            <div className="flex items-center justify-between mt-3">
              <Button size="sm" variant="outline" className="text-xs" onClick={() => setEditing(true)}>
                <Pencil className="h-3 w-3 mr-1.5" /> Edit
              </Button>
              <Button size="sm" variant="default" className="text-xs" onClick={handleSend} disabled={sendingDraft}>
                {sendingDraft ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Send className="h-3 w-3 mr-1" />}
                Send to {origTo.split("@")[0]}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function EditableTypeBadge({ type, actionId, onUpdate }: { type: string; actionId: string; onUpdate: () => void }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleChange = async (newType: string) => {
    if (newType === type) { setOpen(false); return; }
    setSaving(true);
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}`, { action_type: newType });
      toast.success(`Type changed to ${newType.replace(/_/g, " ")}`);
      setOpen(false);
      onUpdate();
    } catch { toast.error("Failed to update"); }
    finally { setSaving(false); }
  };

  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)}>
        <ActionTypeBadge type={type} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-1 bg-background border rounded-md shadow-lg z-20 py-1 w-36">
            {ACTION_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => handleChange(t)}
                disabled={saving}
                className={`w-full text-left px-3 py-1.5 text-xs capitalize hover:bg-muted transition-colors ${t === type ? "font-medium bg-muted/50" : ""}`}
              >
                {t.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function StatusBar({ detail, actionId, onUpdate, loadDetail, onClose }: {
  detail: ActionDetail; actionId: string; onUpdate: () => void; loadDetail: () => void; onClose: () => void;
}) {
  const statusRouter = useRouter();
  const isSuggested = detail.is_suggested === true;

  const [sending, setSending] = useState(false);
  const isCustomerJob = detail.job_path === "customer";

  const statusColors: Record<string, string> = {
    open: "bg-blue-100 dark:bg-blue-950",
    in_progress: "bg-amber-100 dark:bg-amber-950",
    done: "bg-green-100 dark:bg-green-950",
    cancelled: "bg-slate-100 dark:bg-slate-800",
    pending_approval: "bg-purple-100 dark:bg-purple-950",
    approved: "bg-green-100 dark:bg-green-950",
  };

  const handleSendEstimate = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-actions/${actionId}/send-estimate`);
      toast.success("Estimate sent to customer");
      loadDetail();
      onUpdate();
    } catch (e: unknown) {
      const msg = e && typeof e === "object" && "message" in e ? (e as { message: string }).message : "Failed to send";
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  const handleStatusChange = async (status: string) => {
    try {
      const result = await api.put<Record<string, unknown>>(`/v1/admin/agent-actions/${actionId}`, { status });
      toast.success(status === "done" ? "Job marked done" : `Status: ${status}`);
      loadDetail();
      onUpdate();
      if (status === "done" && result?.created_invoice) {
        const inv = result.created_invoice as { id: string; estimate_number: string; total: number };
        toast.success(`Draft invoice created from ${inv.estimate_number}`, {
          action: { label: "View", onClick: () => statusRouter.push(`/invoices/${inv.id}`) },
          duration: 8000,
        });
      }
    } catch { toast.error("Failed to update status"); }
  };

  if (isSuggested) {
    return (
      <div className="border-2 border-dashed border-amber-400 rounded-lg p-3 bg-amber-50/50 dark:bg-amber-950/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-amber-500" />
            <span className="text-sm font-semibold text-amber-700 dark:text-amber-400">Suggested Job</span>
            <ActionTypeBadge type={detail.action_type} />
            {detail.suggestion_confidence && (
              <Badge variant="outline" className="text-[10px] px-1.5 border-amber-400 text-amber-600">
                {detail.suggestion_confidence} confidence
              </Badge>
            )}
          </div>
        </div>
        <p className="text-sm mt-2">{detail.description}</p>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
          {detail.customer_name && <span>{detail.customer_name}</span>}
          {detail.due_date && <span>{formatDueDate(detail.due_date)}</span>}
        </div>
        <div className="flex gap-2 mt-3">
          <Button size="sm" className="h-7 text-xs" onClick={async () => {
            try {
              await api.post(`/v1/admin/agent-actions/${actionId}/approve-suggestion`, {});
              toast.success("Suggestion approved — now an open job");
              loadDetail(); onUpdate();
            } catch { toast.error("Failed"); }
          }}>
            <CheckCircle2 className="h-3 w-3 mr-1" /> Approve
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={async () => {
            try {
              await api.post(`/v1/admin/agent-actions/${actionId}/dismiss-suggestion`, {});
              toast.success("Suggestion dismissed");
              loadDetail(); onUpdate();
            } catch { toast.error("Failed"); }
          }}>
            Dismiss
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={`${statusColors[detail.status] || "bg-slate-100 dark:bg-slate-800"} rounded-lg p-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ActionStatusIcon status={detail.status} />
          <span className="text-sm font-semibold capitalize">{detail.status.replace("_", " ")}</span>
          <EditableTypeBadge type={detail.action_type} actionId={actionId} onUpdate={() => { loadDetail(); onUpdate(); }} />
          {detail.due_date && isOverdue(detail.due_date) && detail.status !== "done" && (
            <Badge variant="destructive" className="text-[10px] px-1.5 bg-red-700">Overdue</Badge>
          )}
        </div>
        <div className="flex gap-1.5">
          {isCustomerJob && detail.status === "open" && detail.invoice_ids && detail.invoice_ids.length > 0 && (
            <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={handleSendEstimate} disabled={sending}>
              {sending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Send className="h-3 w-3 mr-1" />}
              Send Estimate
            </Button>
          )}
          {isCustomerJob && detail.status === "pending_approval" && (
            <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={handleSendEstimate} disabled={sending}>
              {sending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Send className="h-3 w-3 mr-1" />}
              Resend
            </Button>
          )}
          {(detail.status === "open" || detail.status === "in_progress" || detail.status === "approved") && (
            <Button size="sm" className="h-7 text-xs bg-green-600 hover:bg-green-700 text-white" onClick={() => handleStatusChange("done")}>
              <CheckCircle2 className="h-3 w-3 mr-1" /> Mark Job Done
            </Button>
          )}
        </div>
      </div>
      <p className="text-sm mt-2">{detail.description}</p>
      <div className="flex items-center justify-between mt-1">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          {detail.customer_name && <span>{detail.customer_name}</span>}
          {detail.case_id && (
            <Badge
              variant="outline"
              className="text-[9px] px-1 border-blue-300 text-blue-600 cursor-pointer hover:bg-blue-50"
              onClick={() => statusRouter.push(`/cases/${detail.case_id}`)}
            >
              View Case
            </Badge>
          )}
          {detail.assigned_to && <span>→ {detail.assigned_to}</span>}
          <DueDateEditor actionId={actionId} currentDate={detail.due_date} onUpdate={() => { loadDetail(); onUpdate(); }} />
        </div>
        {detail.status !== "cancelled" && detail.status !== "done" && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" title="Delete Job">
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Cancel this job?</AlertDialogTitle>
                <AlertDialogDescription>This will cancel the job. Comments and history will be preserved.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep Job</AlertDialogCancel>
                <AlertDialogAction onClick={async () => {
                  try { await api.put(`/v1/admin/agent-actions/${actionId}`, { status: "cancelled" }); toast.success("Job cancelled"); onClose(); onUpdate(); }
                  catch { toast.error("Failed"); }
                }}>Cancel Job</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </div>
  );
}

function DueDateEditor({ actionId, currentDate, onUpdate }: { actionId: string; currentDate: string | null; onUpdate: () => void }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleChange = async (newDate: string) => {
    setSaving(true);
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}`, { due_date: newDate || null });
      toast.success("Due date updated");
      setEditing(false);
      onUpdate();
    } catch { toast.error("Failed to update"); }
    finally { setSaving(false); }
  };

  if (editing) {
    return (
      <input
        type="date"
        defaultValue={currentDate ? currentDate.split("T")[0] : ""}
        className="bg-white/20 text-white text-xs rounded px-1.5 py-0.5 border border-white/30"
        autoFocus
        disabled={saving}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={() => setEditing(false)}
      />
    );
  }

  return (
    <button
      className="hover:text-white/90 hover:underline cursor-pointer"
      onClick={() => setEditing(true)}
      title="Click to change due date"
    >
      {currentDate ? formatDueDate(currentDate) : "Set due date"}
    </button>
  );
}

function CollapsibleSection({ title, icon: Icon, children, defaultOpen = true, count }: {
  title: string; icon: React.ElementType; children: React.ReactNode; defaultOpen?: boolean; count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium uppercase tracking-wide">{title}</span>
          {count !== undefined && (
            <span className="text-[10px] text-muted-foreground">({count})</span>
          )}
        </div>
        {open ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
      </button>
      {open && <div className="p-3">{children}</div>}
    </div>
  );
}

function ExpandableCard({ label, title, children, variant }: {
  label?: string; title?: string; children?: string | null; variant?: "green" | "amber";
}) {
  const [expanded, setExpanded] = useState(false);
  if (!children) return null;
  const bg = variant === "green" ? "bg-green-50 dark:bg-green-950/20" : variant === "amber" ? "bg-amber-50 dark:bg-amber-950/20" : "bg-muted/50";
  return (
    <div className={`${bg} rounded-md p-3 text-sm space-y-1 cursor-pointer`} onClick={() => setExpanded(!expanded)}>
      {label && <p className="text-xs text-muted-foreground">{label}</p>}
      {title && <p className="font-medium">{title}</p>}
      <p className={`text-xs text-muted-foreground whitespace-pre-wrap ${expanded ? "" : "line-clamp-4"}`}>{children}</p>
      <p className="text-[10px] text-muted-foreground/50">{expanded ? "Click to collapse" : "Click to expand"}</p>
    </div>
  );
}

// --- Main component ---

interface ActionDetailContentProps {
  actionId: string;
  onClose: () => void;
  onUpdate: () => void;
}

export function ActionDetailContent({ actionId, onClose, onUpdate }: ActionDetailContentProps) {
  const router = useRouter();
  const compose = useCompose();
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const commentRef = useRef<HTMLTextAreaElement>(null);
  const [mentionFilter, setMentionFilter] = useState("");
  const teamMembers = useTeamMembers();
  const [followUp, setFollowUp] = useState<{ draft: string; to: string; subject: string } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const [reviseInstruction, setReviseInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [visitPropertyId, setVisitPropertyId] = useState<string | null>(null);

  // --- Handlers ---

  const loadDetail = useCallback(() => {
    setLoading(true);
    api.get<ActionDetail>(`/v1/admin/agent-actions/${actionId}`)
      .then(setDetail)
      .catch(() => toast.error("Failed to load action"))
      .finally(() => setLoading(false));
  }, [actionId]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  useEffect(() => {
    if (!detail?.matched_customer_id || detail.action_type !== "site_visit") return;
    api.get<{ items: { id: string }[] }>(`/v1/properties?customer_id=${detail.matched_customer_id}&limit=1`)
      .then((res) => { if (res.items?.length > 0) setVisitPropertyId(res.items[0].id); })
      .catch(() => {});
  }, [detail?.matched_customer_id, detail?.action_type]);

  const handleAddComment = async () => {
    if (!comment.trim()) return;
    setPosting(true);
    try {
      const result = await api.post<{
        action_resolved?: boolean; action_updated?: boolean;
        new_description?: string; auto_comment?: { author: string; text: string };
      }>(`/v1/admin/agent-actions/${actionId}/comments`, { text: comment });
      setComment("");
      if (result.auto_comment) toast.success(`DeepBlue: ${result.auto_comment.text.slice(0, 80)}`);
      if (result.action_resolved) toast.success("Job marked complete — your comment resolved it");
      else if (result.action_updated && result.new_description) toast.success(`Job updated: ${result.new_description.slice(0, 60)}`);
      loadDetail(); onUpdate();
    } catch { toast.error("Failed to add comment"); }
    finally { setPosting(false); }
  };

  const handleDraftFollowUp = async () => {
    if (!detail) return;
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{ draft: string; to: string; subject: string }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/draft-followup`, {}
      );
      setFollowUp(result); setFollowUpText(result.draft);
    } catch { toast.error("Failed to draft follow-up"); }
    finally { setDraftingFollowUp(false); }
  };

  const handleSendFollowUp = async () => {
    if (!detail || !followUpText.trim()) return;
    setSendingFollowUp(true);
    try {
      const result = await api.post<{
        sent: boolean; closed_actions: { description: string }[];
        ask_actions: { id: string; description: string; reason: string }[];
      }>(`/v1/admin/agent-messages/${detail.agent_message_id}/send-followup`, { response_text: followUpText });
      if (result.closed_actions?.length) toast.success(`Follow-up sent. Completed: ${result.closed_actions.map(a => a.description.slice(0, 40)).join(", ")}`);
      else toast.success("Follow-up sent");
      setFollowUp(null); setFollowUpText(""); setReviseInstruction("");
      loadDetail(); onUpdate();
    } catch { toast.error("Failed to send"); }
    finally { setSendingFollowUp(false); }
  };

  const handleRevise = async () => {
    if (!detail || !reviseInstruction.trim() || !followUpText) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/revise-draft`,
        { draft: followUpText, instruction: reviseInstruction }
      );
      setFollowUpText(result.draft); setReviseInstruction("");
    } catch { toast.error("Failed to revise"); }
    finally { setRevising(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  if (!detail) return null;

  const isActive = detail.status === "open" || detail.status === "in_progress";

  return (
    <div className="space-y-3 pt-2">
      {/* 1. Status Bar — always on top */}
      <StatusBar detail={detail} actionId={actionId} onUpdate={onUpdate} loadDetail={loadDetail} onClose={onClose} />

      {/* 2. Action Buttons — grouped by purpose */}
      {isActive && !followUp && (
        <div className="grid grid-cols-1 gap-2">
          {/* Field actions */}
          {detail.action_type === "site_visit" && visitPropertyId && (
            <Button variant="outline" size="sm" className="justify-start" onClick={() => router.push(`/visits/new?property=${visitPropertyId}&job=${actionId}`)}>
              <Play className="h-3.5 w-3.5 mr-2 text-green-600" /> Start Visit
            </Button>
          )}
        </div>
      )}

      {/* Linked Documents — always visible regardless of job status */}
      {!followUp && (
        <LinkedDocuments actionId={actionId} invoiceIds={detail.invoice_ids || []} threadId={detail.thread_id} onUpdate={() => { loadDetail(); onUpdate(); }} />
      )}

      {/* Follow-up draft editor (replaces action buttons when active) */}
      {followUp && (
        <div className="border rounded-lg p-3 space-y-3 bg-blue-50/50 dark:bg-blue-950/10">
          <div>
            <p className="text-xs font-medium text-blue-700 dark:text-blue-400 mb-1">Follow-up Draft</p>
            <p className="text-xs text-muted-foreground mb-2">To: {followUp.to} — Re: {followUp.subject}</p>
            <Textarea value={followUpText} onChange={(e) => setFollowUpText(e.target.value)} rows={6} className="text-sm" />
          </div>
          <div className="flex gap-2 items-end">
            <Textarea value={reviseInstruction} onChange={(e) => setReviseInstruction(e.target.value)}
              placeholder="Tell AI how to change it..." className="text-sm min-h-[2rem] resize-none flex-1"
              rows={1}
              onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleRevise(); } }} />
            <Button variant="outline" size="sm" className="h-8" onClick={handleRevise} disabled={revising || !reviseInstruction.trim()}>
              {revising && <Loader2 className="h-3 w-3 animate-spin mr-1" />} Revise
            </Button>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}>
              {sendingFollowUp ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />} Send
            </Button>
            <Button variant="ghost" onClick={() => { setFollowUp(null); setFollowUpText(""); setReviseInstruction(""); }}>Cancel</Button>
          </div>
        </div>
      )}

      {/* 3. Tasks — distinct checklist card */}
      {(detail.tasks?.length ?? 0) > 0 && (
        <CollapsibleSection
          title="Tasks"
          icon={ListChecks}
          count={detail.tasks?.length}
          defaultOpen={true}
        >
          <TasksSection actionId={actionId} tasks={detail.tasks || []} onUpdate={() => { loadDetail(); onUpdate(); }} />
        </CollapsibleSection>
      )}

      {/* 4. Parts — purchased parts for this job */}
      <CollapsibleSection title="Parts" icon={Package} defaultOpen={false}>
        <JobPartsSection jobId={actionId} customerId={detail.matched_customer_id} />
      </CollapsibleSection>

      {/* 5. Timeline — unified: original request, replies, comments, related jobs */}
      <CollapsibleSection title="Timeline" icon={MessageSquare} defaultOpen={true}>
        {/* Thread conversation (manually linked thread) */}
        {detail.thread_messages && detail.thread_messages.length > 0 && (
          <div className="space-y-2 mb-3">
            {detail.thread_messages.map((m, i) => (
              <ExpandableCard
                key={i}
                label={m.direction === "inbound" ? `From: ${m.from_email}` : `To: ${m.to_email}`}
                variant={m.direction === "outbound" ? "green" : undefined}
                title={i === 0 ? m.subject : undefined}
              >
                {m.body}
              </ExpandableCard>
            ))}
          </div>
        )}

        {/* Original request (email, phone, etc.) */}
        {detail.subject && (
          <div className="space-y-2 mb-3">
            <ExpandableCard label={detail.from_email ? `Email: ${detail.from_email}` : "Original Request"} title={detail.subject}>
              {detail.email_body}
            </ExpandableCard>
            {detail.our_response && !detail.response_is_draft && (
              <ExpandableCard label="Our reply" variant="green">{detail.our_response}</ExpandableCard>
            )}
            {detail.our_response && detail.response_is_draft && detail.thread_id && (
              <DraftReplyBlock
                threadId={detail.thread_id}
                draft={detail.our_response}
                onAction={() => { onUpdate(); loadDetail(); }}
              />
            )}
            {detail.our_response && detail.response_is_draft && !detail.thread_id && (
              <ExpandableCard label="Draft reply (not sent)" variant="amber">{detail.our_response}</ExpandableCard>
            )}
          </div>
        )}

        {/* Related jobs */}
        {detail.related_jobs && detail.related_jobs.length > 0 && (
          <div className="space-y-2 mb-3">
            {detail.related_jobs.map((job) => (
              <div key={job.id} className="bg-muted/30 rounded-md p-2.5 text-sm">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <ActionStatusIcon status={job.status} />
                  <ActionTypeBadge type={job.action_type} />
                </div>
                <p className={`text-xs ${job.status === "done" ? "line-through text-muted-foreground" : ""}`}>{job.description}</p>
                {job.comments.length > 0 && (
                  <div className="mt-1 space-y-0.5">
                    {job.comments.map((c, i) => (
                      <p key={i} className="text-[10px] text-muted-foreground">{c.author}: {c.text}</p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Comments / activity */}
        {detail.comments && detail.comments.length > 0 ? (
          <div className="space-y-2 mb-3">
            {detail.comments.map((c) => {
              const isDraft = c.text.startsWith("[DRAFT_EMAIL]");
              const isSent = c.text.startsWith("[SENT_EMAIL]");
              if (isDraft || isSent) {
                const lines = c.text.replace(/\[(DRAFT|SENT)_EMAIL\]\n/, "").split("\n---\n");
                const header = lines[0] || "";
                const origBody = lines[1] || "";
                const origTo = header.match(/To: (.+)/)?.[1] || "";
                const origSubject = header.match(/Subject: (.+)/)?.[1] || "";
                return (
                  <DraftEmailBlock
                    key={c.id}
                    commentId={c.id}
                    isSent={isSent}
                    to={origTo}
                    subject={origSubject}
                    body={origBody}
                    createdAt={c.created_at}
                    actionId={actionId}
                    onSent={() => { loadDetail(); onUpdate(); }}
                  />
                );
              }
              const isActivity = c.text.startsWith("[ACTIVITY]");
              if (isActivity) {
                const activityText = c.text.replace("[ACTIVITY]\n", "");
                return (
                  <div key={c.id} className="flex items-center gap-2 py-1 px-2">
                    <div className="h-1.5 w-1.5 rounded-full bg-blue-400 shrink-0" />
                    <span className="text-xs text-muted-foreground">{activityText}</span>
                    <span className="text-[10px] text-muted-foreground/50 ml-auto shrink-0">{formatTime(c.created_at)}</span>
                  </div>
                );
              }
              const isBot = c.author === "DeepBlue";
              return (
                <div key={c.id} className={`rounded-md p-2.5 ${isBot ? "bg-violet-50 dark:bg-violet-950/20 border border-violet-200 dark:border-violet-800" : "bg-muted/50"}`}>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className={`text-xs font-medium ${isBot ? "text-violet-700 dark:text-violet-400" : ""}`}>
                      {isBot ? "🤖 DeepBlue" : c.author}
                    </span>
                    <span className="text-[10px] text-muted-foreground">{formatTime(c.created_at)}</span>
                  </div>
                  <p className="text-sm">{c.text}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground mb-3">No comments yet</p>
        )}
        {isActive && detail.agent_message_id && (
          <Button variant="outline" size="sm" className="w-full justify-start mb-3" onClick={handleDraftFollowUp} disabled={draftingFollowUp}>
            {draftingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" /> : <Mail className="h-3.5 w-3.5 mr-2 text-blue-600" />}
            Draft Follow-up Email
          </Button>
        )}
        <div className="relative">
          <div className="flex gap-2 items-end">
            <Textarea
              ref={commentRef}
              value={comment}
              onChange={(e) => {
                const val = e.target.value;
                setComment(val);
                // Detect @ trigger
                const lastAt = val.lastIndexOf("@");
                if (lastAt >= 0 && (lastAt === 0 || val[lastAt - 1] === " " || val[lastAt - 1] === "\n")) {
                  const afterAt = val.slice(lastAt + 1);
                  if (!afterAt.includes(" ") || afterAt.split(" ").length <= 1) {
                    setMentionOpen(true);
                    setMentionFilter(afterAt.toLowerCase());
                  } else {
                    setMentionOpen(false);
                  }
                } else {
                  setMentionOpen(false);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") setMentionOpen(false);
              }}
              placeholder="Comment, or type @ to mention..."
              className="text-sm min-h-[2.5rem] resize-none flex-1"
              rows={2}
            />
            <Button size="sm" className="h-9 flex-shrink-0" onClick={() => { handleAddComment(); setMentionOpen(false); }} disabled={posting || !comment.trim()}>
              {posting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Post"}
            </Button>
          </div>

          {/* Mention autocomplete dropdown */}
          {mentionOpen && (
            <div className="fixed bottom-16 left-4 right-4 sm:left-auto sm:right-auto sm:w-48 bg-background border rounded-md shadow-lg z-[100] py-1 max-h-40 overflow-y-auto">
              {[{ name: "DeepBlue", label: "AI Assistant" }, ...teamMembers.map(n => ({ name: n, label: "" }))].filter(
                (m) => m.name.toLowerCase().startsWith(mentionFilter) || !mentionFilter
              ).map((m) => (
                <button
                  key={m.name}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-muted transition-colors flex items-center justify-between"
                  onClick={() => {
                    const lastAt = comment.lastIndexOf("@");
                    const before = comment.slice(0, lastAt);
                    const newVal = `${before}@${m.name} `;
                    setComment(newVal);
                    setMentionOpen(false);
                    // Refocus textarea with cursor at end
                    setTimeout(() => {
                      if (commentRef.current) {
                        commentRef.current.focus();
                        commentRef.current.selectionStart = newVal.length;
                        commentRef.current.selectionEnd = newVal.length;
                      }
                    }, 0);
                  }}
                >
                  <span className={m.name === "DeepBlue" ? "font-medium text-violet-600" : ""}>{m.name}</span>
                  {m.label && <span className="text-[10px] text-muted-foreground">{m.label}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </CollapsibleSection>

    </div>
  );
}


// --- Linked Documents Section ---
interface LinkedDoc {
  id: string;
  invoice_number: string | null;
  document_type: string;
  status: string;
  subject: string | null;
  total: number;
  customer_name: string | null;
}

function LinkedDocuments({ actionId, invoiceIds, threadId, onUpdate }: { actionId: string; invoiceIds: string[]; threadId?: string | null; onUpdate: () => void }) {
  const router = useRouter();
  const [docs, setDocs] = useState<LinkedDoc[]>([]);
  const [linking, setLinking] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<LinkedDoc[]>([]);
  const [searching, setSearching] = useState(false);
  const [linkingThread, setLinkingThread] = useState(false);
  const [threadQuery, setThreadQuery] = useState("");
  const [threadResults, setThreadResults] = useState<{ id: string; subject: string; customer_name: string | null; last_snippet: string | null }[]>([]);
  const [searchingThreads, setSearchingThreads] = useState(false);

  // Load linked document details
  useEffect(() => {
    if (invoiceIds.length === 0) { setDocs([]); return; }
    Promise.all(
      invoiceIds.map((id) =>
        api.get<LinkedDoc>(`/v1/invoices/${id}`).catch(() => null)
      )
    ).then((results) => setDocs(results.filter(Boolean) as LinkedDoc[]));
  }, [invoiceIds]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await api.get<{ items: LinkedDoc[] }>(
        `/v1/invoices?search=${encodeURIComponent(searchQuery)}&limit=10`
      );
      // Filter out already linked
      setSearchResults(data.items.filter((i) => !invoiceIds.includes(i.id)));
    } catch {
      toast.error("Search failed");
    } finally {
      setSearching(false);
    }
  };

  const handleLink = async (invoiceId: string) => {
    try {
      await api.post(`/v1/admin/agent-actions/${actionId}/link-invoice`, { invoice_id: invoiceId });
      toast.success("Document linked");
      setLinking(false);
      setSearchQuery("");
      setSearchResults([]);
      onUpdate();
    } catch {
      toast.error("Failed to link");
    }
  };

  const handleUnlink = async (invoiceId: string) => {
    try {
      await api.delete(`/v1/admin/agent-actions/${actionId}/link-invoice/${invoiceId}`);
      toast.success("Document unlinked");
      onUpdate();
    } catch {
      toast.error("Failed to unlink");
    }
  };

  const handleThreadSearch = async () => {
    if (!threadQuery.trim()) return;
    setSearchingThreads(true);
    try {
      const data = await api.get<{ items: { id: string; subject: string; customer_name: string | null; last_snippet: string | null }[] }>(
        `/v1/admin/agent-threads?search=${encodeURIComponent(threadQuery)}&limit=10`
      );
      setThreadResults(data.items || []);
    } catch {
      toast.error("Search failed");
    } finally {
      setSearchingThreads(false);
    }
  };

  const handleLinkThread = async (tid: string) => {
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}`, { thread_id: tid });
      toast.success("Email linked");
      setLinkingThread(false);
      setThreadQuery("");
      setThreadResults([]);
      onUpdate();
    } catch {
      toast.error("Failed to link");
    }
  };

  const handleUnlinkThread = async () => {
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}`, { thread_id: "" });
      toast.success("Email unlinked");
      onUpdate();
    } catch {
      toast.error("Failed to unlink");
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Documents</span>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setLinking(!linking)}>
            <Link2 className="h-3 w-3 mr-1" /> Link
          </Button>
          <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => router.push(`/invoices/new?job=${actionId}&type=estimate`)}>
            <DollarSign className="h-3 w-3 mr-1" /> New
          </Button>
        </div>
      </div>

      {/* Linked docs */}
      {docs.map((doc) => (
        <div key={doc.id} className="flex items-center justify-between py-1.5 px-2 rounded-md bg-muted/50 group">
          <button
            className="flex items-center gap-2 text-sm hover:underline text-left"
            onClick={() => router.push(`/invoices/${doc.id}`)}
          >
            <DollarSign className="h-3.5 w-3.5 text-emerald-600" />
            <span className="font-medium">{doc.invoice_number || "Draft"}</span>
            <span className="text-muted-foreground text-xs">
              {doc.document_type === "estimate" ? "Est" : "Inv"} · ${doc.total.toFixed(2)}
            </span>
            <Badge variant="outline" className="text-[9px] h-4 px-1">
              {doc.status.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </Badge>
          </button>
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
            onClick={() => handleUnlink(doc.id)}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      ))}

      {docs.length === 0 && !linking && (
        <p className="text-xs text-muted-foreground py-1">No documents linked</p>
      )}

      {/* Link search */}
      {linking && (
        <div className="space-y-2 p-2 border rounded-md bg-background">
          <div className="flex gap-1">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
              placeholder="Search by number, subject, or client..."
              className="h-7 text-xs"
              autoFocus
            />
            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={handleSearch} disabled={searching}>
              {searching ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
            </Button>
          </div>
          {searchResults.length > 0 && (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {searchResults.map((r) => (
                <button
                  key={r.id}
                  className="w-full flex items-center justify-between py-1.5 px-2 rounded hover:bg-muted text-left text-xs"
                  onClick={() => handleLink(r.id)}
                >
                  <span>
                    <span className="font-medium">{r.invoice_number || "Draft"}</span>
                    <span className="text-muted-foreground ml-2">{r.subject || "—"}</span>
                  </span>
                  <span className="text-muted-foreground">${r.total.toFixed(2)}</span>
                </button>
              ))}
            </div>
          )}
          <Button variant="ghost" size="sm" className="h-6 text-[10px] w-full" onClick={() => { setLinking(false); setSearchResults([]); setSearchQuery(""); }}>
            Cancel
          </Button>
        </div>
      )}

      {/* Linked email thread */}
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs font-medium text-muted-foreground">Email</span>
        {!threadId && (
          <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setLinkingThread(!linkingThread)}>
            <Link2 className="h-3 w-3 mr-1" /> Link
          </Button>
        )}
      </div>
      {threadId && (
        <div className="flex items-center justify-between py-1.5 px-2 rounded-md bg-muted/50 group">
          <button
            className="flex items-center gap-2 text-sm hover:underline text-left"
            onClick={() => router.push(`/inbox?thread=${threadId}`)}
          >
            <Mail className="h-3.5 w-3.5 text-blue-600" />
            <span className="text-xs">View linked email</span>
          </button>
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
            onClick={handleUnlinkThread}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}
      {!threadId && !linkingThread && (
        <p className="text-xs text-muted-foreground py-1">No email linked</p>
      )}
      {linkingThread && (
        <div className="space-y-2 p-2 border rounded-md bg-background">
          <div className="flex gap-1">
            <Input
              value={threadQuery}
              onChange={(e) => setThreadQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleThreadSearch(); }}
              placeholder="Search emails by subject or client..."
              className="h-7 text-xs"
              autoFocus
            />
            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={handleThreadSearch} disabled={searchingThreads}>
              {searchingThreads ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
            </Button>
          </div>
          {threadResults.length > 0 && (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {threadResults.map((r) => (
                <button
                  key={r.id}
                  className="w-full flex items-center justify-between py-1.5 px-2 rounded hover:bg-muted text-left text-xs"
                  onClick={() => handleLinkThread(r.id)}
                >
                  <div className="min-w-0">
                    <span className="font-medium truncate block">{r.subject || "No subject"}</span>
                    <span className="text-muted-foreground truncate block">{r.customer_name || r.last_snippet || ""}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
          <Button variant="ghost" size="sm" className="h-6 text-[10px] w-full" onClick={() => { setLinkingThread(false); setThreadResults([]); setThreadQuery(""); }}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
