"use client";

import { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCompose } from "@/components/email/compose-provider";
import { formatTime, formatDueDate, isOverdue } from "@/lib/format";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
import { TasksSection } from "@/components/jobs/tasks-section";
import type { ActionDetail } from "@/types/agent";
import { JobPartsSection } from "@/components/jobs/job-parts-section";

// --- Utility components ---

function StatusBar({ detail, actionId, onUpdate, loadDetail }: {
  detail: ActionDetail; actionId: string; onUpdate: () => void; loadDetail: () => void;
}) {
  const statusColors: Record<string, string> = {
    open: "bg-blue-500",
    in_progress: "bg-amber-500",
    done: "bg-green-500",
    cancelled: "bg-slate-400",
  };

  const handleStatusChange = async (status: string) => {
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}`, { status });
      toast.success(status === "done" ? "Job marked done" : `Status: ${status}`);
      loadDetail();
      onUpdate();
    } catch { toast.error("Failed to update status"); }
  };

  return (
    <div className={`${statusColors[detail.status] || "bg-slate-400"} rounded-lg p-3 text-white`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ActionStatusIcon status={detail.status} />
          <span className="text-sm font-semibold capitalize">{detail.status.replace("_", " ")}</span>
          <ActionTypeBadge type={detail.action_type} />
          {detail.due_date && isOverdue(detail.due_date) && detail.status !== "done" && (
            <Badge variant="destructive" className="text-[10px] px-1.5 bg-red-700">Overdue</Badge>
          )}
        </div>
        {(detail.status === "open" || detail.status === "in_progress") && (
          <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={() => handleStatusChange("done")}>
            <CheckCircle2 className="h-3 w-3 mr-1" /> Done
          </Button>
        )}
      </div>
      <p className="text-sm mt-2 text-white/90">{detail.description}</p>
      <div className="flex items-center gap-4 text-xs text-white/70 mt-1">
        {detail.customer_name && <span>{detail.customer_name}</span>}
        {detail.assigned_to && <span>→ {detail.assigned_to}</span>}
        {detail.due_date && <span>{formatDueDate(detail.due_date)}</span>}
      </div>
    </div>
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
  label?: string; title?: string; children?: string | null; variant?: "green";
}) {
  const [expanded, setExpanded] = useState(false);
  if (!children) return null;
  const bg = variant === "green" ? "bg-green-50 dark:bg-green-950/20" : "bg-muted/50";
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
      <StatusBar detail={detail} actionId={actionId} onUpdate={onUpdate} loadDetail={loadDetail} />

      {/* 2. Action Buttons — grouped by purpose */}
      {isActive && !followUp && (
        <div className="grid grid-cols-1 gap-2">
          {/* Field actions */}
          {detail.action_type === "site_visit" && visitPropertyId && (
            <Button variant="outline" size="sm" className="justify-start" onClick={() => router.push(`/visits/new?property=${visitPropertyId}&job=${actionId}`)}>
              <Play className="h-3.5 w-3.5 mr-2 text-green-600" /> Start Visit
            </Button>
          )}
          {/* Communication */}
          {detail.agent_message_id && (
            <Button variant="outline" size="sm" className="justify-start" onClick={handleDraftFollowUp} disabled={draftingFollowUp}>
              {draftingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" /> : <Mail className="h-3.5 w-3.5 mr-2 text-blue-600" />}
              Draft Follow-up Email
            </Button>
          )}
          {/* Billing */}
          {detail.invoice_id ? (
            <Button variant="outline" size="sm" className="justify-start" onClick={() => router.push(`/invoices/${detail.invoice_id}`)}>
              <DollarSign className="h-3.5 w-3.5 mr-2 text-emerald-600" /> View Estimate
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="justify-start" onClick={() => router.push(`/invoices/new?job=${actionId}&type=estimate`)}>
              <DollarSign className="h-3.5 w-3.5 mr-2 text-emerald-600" /> Create Estimate
            </Button>
          )}
        </div>
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
            <Input value={reviseInstruction} onChange={(e) => setReviseInstruction(e.target.value)}
              placeholder="Tell AI how to change it..." className="text-sm h-8 flex-1"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleRevise(); } }} />
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
        <JobPartsSection jobId={actionId} />
      </CollapsibleSection>

      {/* 5. Context — email thread + related jobs (collapsed by default) */}
      {(detail.subject || detail.related_jobs?.length) && (
        <CollapsibleSection title="Context" icon={ClipboardList} defaultOpen={false} count={detail.related_jobs?.length}>
          <div className="space-y-2">
            {detail.subject && (
              <ExpandableCard label={`Email: ${detail.from_email}`} title={detail.subject}>
                {detail.email_body}
              </ExpandableCard>
            )}
            {detail.our_response && (
              <ExpandableCard label="Our reply" variant="green">{detail.our_response}</ExpandableCard>
            )}
            {detail.related_jobs?.map((job) => (
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
        </CollapsibleSection>
      )}

      {/* 5. Activity — visually distinct from tasks */}
      <CollapsibleSection title="Activity" icon={MessageSquare} count={detail.comments?.length} defaultOpen={true}>
        {detail.comments && detail.comments.length > 0 ? (
          <div className="space-y-2 mb-3">
            {detail.comments.map((c) => {
              const isDraft = c.text.startsWith("[DRAFT_EMAIL]");
              const isSent = c.text.startsWith("[SENT_EMAIL]");
              if (isDraft || isSent) {
                const lines = c.text.replace(/\[(DRAFT|SENT)_EMAIL\]\n/, "").split("\n---\n");
                const header = lines[0] || "";
                const body = lines[1] || "";
                const to = header.match(/To: (.+)/)?.[1] || "";
                const subject = header.match(/Subject: (.+)/)?.[1] || "";
                return (
                  <div key={c.id} className={`rounded-md p-3 border ${isSent ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800" : "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800"}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-xs font-medium ${isSent ? "text-green-700 dark:text-green-400" : "text-blue-700 dark:text-blue-400"}`}>
                        {isSent ? "✓ Email Sent" : "Draft Email"}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{formatTime(c.created_at)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">To: {to}</p>
                    <p className="text-xs font-medium mb-1">Subject: {subject}</p>
                    <p className="text-sm whitespace-pre-wrap line-clamp-6">{body}</p>
                    {!isSent && (
                      <Button size="sm" variant="default" className="mt-2"
                        onClick={() => compose.openCompose({ to, subject, body, jobId: actionId, originalDraft: body, originalSubject: subject, onSent: () => { loadDetail(); onUpdate(); } })}>
                        <Send className="h-3.5 w-3.5 mr-1.5" /> Edit & Send
                      </Button>
                    )}
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
        <div className="flex gap-2 items-end">
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment or give AI a command..." className="text-sm min-h-[2.5rem] resize-none flex-1" rows={2} />
          <Button size="sm" className="h-9 flex-shrink-0" onClick={handleAddComment} disabled={posting || !comment.trim()}>
            {posting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Post"}
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1">
          Try: "draft email to client", "assign to Shane", "mark as done"
        </p>
      </CollapsibleSection>

      {/* 6. Danger zone — bottom, subtle */}
      {detail.status !== "cancelled" && (
        <div className="flex justify-end pt-1">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-destructive">
                <Trash2 className="h-3 w-3 mr-1" /> Cancel Job
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
        </div>
      )}
    </div>
  );
}
