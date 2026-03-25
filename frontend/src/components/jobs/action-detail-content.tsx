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
} from "lucide-react";
import { useRouter } from "next/navigation";
import { formatTime, formatDueDate, isOverdue } from "@/lib/format";
import { ActionTypeBadge, ActionStatusIcon } from "@/components/jobs/job-badges";
import { TasksSection } from "@/components/jobs/tasks-section";
import type { ActionDetail } from "@/types/agent";

function ExpandableCard({ label, title, children, variant }: { label?: string; title?: string; children?: string | null; variant?: "green" }) {
  const [expanded, setExpanded] = useState(false);
  if (!children) return null;
  const bg = variant === "green" ? "bg-green-50 dark:bg-green-950/20" : "bg-muted/50";
  return (
    <div className={`${bg} rounded-md p-3 text-sm space-y-1 cursor-pointer`} onClick={() => setExpanded(!expanded)}>
      {label && <p className="text-xs text-muted-foreground">{label}</p>}
      {title && <p className="font-medium">{title}</p>}
      <p className={`text-xs text-muted-foreground whitespace-pre-wrap ${expanded ? "" : "line-clamp-4"}`}>
        {children}
      </p>
      <p className="text-[10px] text-muted-foreground/50">{expanded ? "Click to collapse" : "Click to expand"}</p>
    </div>
  );
}

interface ActionDetailContentProps {
  actionId: string;
  onClose: () => void;
  onUpdate: () => void;
}

export function ActionDetailContent({
  actionId,
  onClose,
  onUpdate,
}: ActionDetailContentProps) {
  const router = useRouter();
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [followUp, setFollowUp] = useState<{
    draft: string;
    to: string;
    subject: string;
  } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const [reviseInstruction, setReviseInstruction] = useState("");
  const [revising, setRevising] = useState(false);

  const handleDraftFollowUp = async () => {
    if (!detail) return;
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{
        draft: string;
        to: string;
        subject: string;
      }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/draft-followup`,
        {}
      );
      setFollowUp(result);
      setFollowUpText(result.draft);
    } catch {
      toast.error("Failed to draft follow-up");
    } finally {
      setDraftingFollowUp(false);
    }
  };

  const handleSendFollowUp = async () => {
    if (!detail || !followUpText.trim()) return;
    setSendingFollowUp(true);
    try {
      const result = await api.post<{
        sent: boolean;
        closed_actions: { description: string }[];
        ask_actions: {
          id: string;
          description: string;
          reason: string;
        }[];
      }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/send-followup`,
        { response_text: followUpText }
      );
      if (result.closed_actions?.length) {
        toast.success(
          `Follow-up sent. Completed: ${result.closed_actions
            .map((a) => a.description.slice(0, 40))
            .join(", ")}`
        );
      } else {
        toast.success("Follow-up sent");
      }
      if (result.ask_actions?.length) {
        for (const a of result.ask_actions) {
          toast(
            `Does this close "${a.description.slice(0, 50)}"? ${a.reason}`,
            { duration: 10000 }
          );
        }
      }
      setFollowUp(null);
      setFollowUpText("");
      setReviseInstruction("");
      loadDetail();
      onUpdate();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const handleRevise = async () => {
    if (!detail || !reviseInstruction.trim() || !followUpText) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/revise-draft`,
        {
          draft: followUpText,
          instruction: reviseInstruction,
        }
      );
      setFollowUpText(result.draft);
      setReviseInstruction("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setRevising(false);
    }
  };

  const loadDetail = useCallback(() => {
    setLoading(true);
    api
      .get<ActionDetail>(`/v1/admin/agent-actions/${actionId}`)
      .then((d) => {
        setDetail(d);
      })
      .catch(() => toast.error("Failed to load action"))
      .finally(() => setLoading(false));
  }, [actionId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleAddComment = async () => {
    if (!comment.trim()) return;
    setPosting(true);
    try {
      const result = await api.post<{
        action_resolved?: boolean;
        action_updated?: boolean;
        new_description?: string;
        auto_comment?: { author: string; text: string };
      }>(`/v1/admin/agent-actions/${actionId}/comments`, { text: comment });
      setComment("");
      if (result.auto_comment) {
        toast.success(`DeepBlue: ${result.auto_comment.text.slice(0, 80)}`);
      }
      if (result.action_resolved) {
        toast.success("Job marked complete — your comment resolved it");
      } else if (result.action_updated && result.new_description) {
        toast.success(
          `Job updated: ${result.new_description.slice(0, 60)}`
        );
      }
      loadDetail();
      onUpdate();
    } catch {
      toast.error("Failed to add comment");
    } finally {
      setPosting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!detail) return null;

  return (
    <div className="space-y-5 pt-2">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <ActionStatusIcon status={detail.status} />
          <ActionTypeBadge type={detail.action_type} />
          {detail.due_date &&
            isOverdue(detail.due_date) &&
            detail.status !== "done" && (
              <Badge
                variant="destructive"
                className="text-[10px] px-1.5"
              >
                Overdue
              </Badge>
            )}
        </div>
        <p className="text-sm font-medium">{detail.description}</p>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{detail.customer_name || detail.from_email}</span>
          {detail.assigned_to && (
            <span>Assigned: {detail.assigned_to}</span>
          )}
          {detail.due_date && <span>{formatDueDate(detail.due_date)}</span>}
        </div>
      </div>

      {/* Context trail */}
      {(detail.subject || detail.related_jobs) && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Context
          </p>

          {detail.subject && (
            <ExpandableCard label={`Email: ${detail.from_email}`} title={detail.subject}>
              {detail.email_body}
            </ExpandableCard>
          )}

          {detail.our_response && (
            <ExpandableCard label="Our reply" variant="green">
              {detail.our_response}
            </ExpandableCard>
          )}

          {detail.related_jobs?.map((job) => (
            <div
              key={job.id}
              className="bg-muted/30 rounded-md p-2.5 text-sm"
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <ActionStatusIcon status={job.status} />
                <ActionTypeBadge type={job.action_type} />
              </div>
              <p
                className={`text-xs ${
                  job.status === "done"
                    ? "line-through text-muted-foreground"
                    : ""
                }`}
              >
                {job.description}
              </p>
              {job.comments.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {job.comments.map((c, i) => (
                    <p
                      key={i}
                      className="text-[10px] text-muted-foreground"
                    >
                      {c.author}: {c.text}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tasks */}
      <TasksSection actionId={actionId} tasks={detail.tasks || []} onUpdate={() => { loadDetail(); onUpdate(); }} />

      {/* Comments / Activity */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          Activity
        </p>
        {detail.comments && detail.comments.length > 0 ? (
          <div className="space-y-2 mb-3">
            {detail.comments.map((c) => (
              <div key={c.id} className="bg-muted/50 rounded-md p-2.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium">{c.author}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {formatTime(c.created_at)}
                  </span>
                </div>
                <p className="text-sm">{c.text}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground mb-3">
            No comments yet
          </p>
        )}
        <div className="flex gap-2 items-end">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment..."
            className="text-sm min-h-[2.5rem] resize-none flex-1"
            rows={2}
          />
          <Button
            size="sm"
            className="h-9 flex-shrink-0"
            onClick={handleAddComment}
            disabled={posting || !comment.trim()}
          >
            {posting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              "Post"
            )}
          </Button>
        </div>
      </div>

      {/* Actions row */}
      {!followUp && (
        <div className="pt-2 border-t flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftFollowUp}
            disabled={draftingFollowUp}
          >
            {draftingFollowUp ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <Send className="h-3.5 w-3.5 mr-1.5" />
            )}
            Draft Follow-up
          </Button>
          {detail.invoice_id ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/invoices/${detail.invoice_id}`)}
            >
              <DollarSign className="h-3.5 w-3.5 mr-1.5" />
              View Estimate
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/invoices/new?job=${actionId}&type=estimate`)}
            >
              <DollarSign className="h-3.5 w-3.5 mr-1.5" />
              Create Estimate
            </Button>
          )}
        </div>
      )}

      {followUp && (
        <div className="pt-2 border-t space-y-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">
              Follow-up Draft
            </p>
            <p className="text-xs text-muted-foreground mb-2">
              To: {followUp.to} — Re: {followUp.subject}
            </p>
            <Textarea
              value={followUpText}
              onChange={(e) => setFollowUpText(e.target.value)}
              rows={6}
              className="text-sm"
            />
          </div>
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                value={reviseInstruction}
                onChange={(e) => setReviseInstruction(e.target.value)}
                placeholder="Tell AI how to change it..."
                className="text-sm h-8"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleRevise();
                  }
                }}
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={handleRevise}
              disabled={revising || !reviseInstruction.trim()}
            >
              {revising ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
              ) : null}
              Revise
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleSendFollowUp}
              disabled={sendingFollowUp || !followUpText.trim()}
            >
              {sendingFollowUp ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Send className="h-4 w-4 mr-2" />
              )}
              Send
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setFollowUp(null);
                setFollowUpText("");
                setReviseInstruction("");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Actions */}
      {(detail.status === "open" || detail.status === "in_progress") && (
        <div className="pt-3 border-t">
          <Button
            className="w-full bg-green-600 hover:bg-green-700"
            onClick={async () => {
              try {
                await api.put(`/v1/admin/agent-actions/${actionId}`, { status: "done" });
                toast.success("Job marked done");
                loadDetail();
                onUpdate();
              } catch { toast.error("Failed"); }
            }}
          >
            <CheckCircle2 className="h-4 w-4 mr-2" />
            Mark Done
          </Button>
        </div>
      )}

      {/* Delete */}
      {detail.status !== "cancelled" && (
        <div className="pt-2 flex justify-end">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-3 w-3 mr-1" />
                Delete Job
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this job?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove the action and all its
                  comments. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={async () => {
                    try {
                      await api.put(
                        `/v1/admin/agent-actions/${actionId}`,
                        { status: "cancelled" }
                      );
                      toast.success("Action deleted");
                      onClose();
                      onUpdate();
                    } catch {
                      toast.error("Failed");
                    }
                  }}
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
}
