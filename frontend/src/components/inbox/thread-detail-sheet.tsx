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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Loader2,
  Send,
  Pencil,
  AlertTriangle,
  User,
} from "lucide-react";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import { formatTime } from "@/lib/format";
import type { ThreadDetail } from "@/types/agent";
import { StatusBadge, UrgencyBadge, CategoryBadge } from "./inbox-badges";
import { CollapsibleBody } from "./collapsible-body";

function isStale(receivedAt: string | null) {
  if (!receivedAt) return false;
  return (Date.now() - new Date(receivedAt).getTime()) > 30 * 60 * 1000;
}

export function ThreadDetailSheet({
  threadId,
  onClose,
  onAction,
}: {
  threadId: string;
  onClose: () => void;
  onAction: () => void;
}) {
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  // Draft editing (for pending messages)
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [reviseInstruction, setReviseInstruction] = useState("");
  const [revising, setRevising] = useState(false);

  // Follow-up (for handled threads)
  const [followUp, setFollowUp] = useState<{ draft: string; to: string; subject: string } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const [followUpRevise, setFollowUpRevise] = useState("");
  const [followUpRevising, setFollowUpRevising] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const teamMembers = useTeamMembersFull();

  const timelineEndRef = useRef<HTMLDivElement>(null);

  const loadThread = useCallback(() => {
    setLoading(true);
    api.get<ThreadDetail>(`/v1/admin/agent-threads/${threadId}`)
      .then((t) => {
        setThread(t);
        // Find latest pending message draft
        const pendingMsg = t.timeline.find((m) => m.status === "pending" && m.direction === "inbound" && m.draft_response);
        if (pendingMsg) {
          setEditText(pendingMsg.draft_response || "");
        }
      })
      .catch(() => toast.error("Failed to load thread"))
      .finally(() => setLoading(false));
  }, [threadId]);

  useEffect(() => { loadThread(); }, [loadThread]);

  useEffect(() => {
    if (!loading && timelineEndRef.current) {
      timelineEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [loading, thread]);

  const pendingMessage = thread?.timeline.find((m) => m.status === "pending" && m.direction === "inbound");

  const handleApprove = async (responseText?: string) => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/approve`, {
        response_text: responseText || undefined,
      });
      toast.success("Reply sent");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSending(false);
    }
  };

  const handleDismiss = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/dismiss`, {});
      toast.success("Thread dismissed");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to dismiss");
    } finally {
      setSending(false);
    }
  };

  const handleReviseDraft = async () => {
    if (!reviseInstruction.trim()) return;
    const currentDraft = editing ? editText : (pendingMessage?.draft_response || "");
    if (!currentDraft) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-threads/${threadId}/revise-draft`, {
        draft: currentDraft,
        instruction: reviseInstruction,
      });
      setEditText(result.draft);
      setEditing(true);
      setReviseInstruction("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setRevising(false);
    }
  };

  const handleDraftFollowUp = async () => {
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{ draft: string; to: string; subject: string }>(`/v1/admin/agent-threads/${threadId}/draft-followup`, {});
      setFollowUp(result);
      setFollowUpText(result.draft);
    } catch {
      toast.error("Failed to draft follow-up");
    } finally {
      setDraftingFollowUp(false);
    }
  };

  const handleSendFollowUp = async () => {
    if (!followUpText.trim()) return;
    setSendingFollowUp(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/send-followup`, { response_text: followUpText });
      toast.success("Follow-up sent");
      setFollowUp(null);
      setFollowUpText("");
      setFollowUpRevise("");
      onAction();
      loadThread();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const handleReviseFollowUp = async () => {
    if (!followUpRevise.trim() || !followUpText) return;
    setFollowUpRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-threads/${threadId}/revise-draft`, {
        draft: followUpText,
        instruction: followUpRevise,
      });
      setFollowUpText(result.draft);
      setFollowUpRevise("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setFollowUpRevising(false);
    }
  };

  const handleDelete = async () => {
    setSending(true);
    try {
      await api.delete(`/v1/admin/agent-threads/${threadId}`);
      toast.success("Thread deleted");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to delete");
    } finally {
      setSending(false);
    }
  };

  const handleAssign = async (userId: string) => {
    setAssigning(true);
    try {
      const member = userId === "__unassign__" ? null : teamMembers.find((m) => m.user_id === userId);
      const result = await api.post<{ assigned_to_user_id: string | null; assigned_to_name: string | null; assigned_at: string | null }>(
        `/v1/admin/agent-threads/${threadId}/assign`,
        {
          user_id: member ? member.user_id : null,
          user_name: member ? `${member.first_name} ${member.last_name}` : null,
        },
      );
      if (thread) {
        setThread({
          ...thread,
          assigned_to_user_id: result.assigned_to_user_id,
          assigned_to_name: result.assigned_to_name,
          assigned_at: result.assigned_at,
        });
      }
      toast.success(member ? `Assigned to ${member.first_name}` : "Unassigned");
      onAction();
    } catch {
      toast.error("Failed to assign");
    } finally {
      setAssigning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!thread) return null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 space-y-2 pb-4 border-b">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={thread.status} />
          <UrgencyBadge urgency={thread.urgency} />
          <CategoryBadge category={thread.category} />
          {thread.has_pending && isStale(thread.timeline[thread.timeline.length - 1]?.received_at) && (
            <Badge variant="destructive" className="text-[10px] px-1.5">
              <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />Stale
            </Badge>
          )}
        </div>
        {/* Assignment */}
        <div className="flex items-center gap-2">
          <User className="h-3.5 w-3.5 text-muted-foreground" />
          <Select
            value={thread.assigned_to_user_id || "__unassign__"}
            onValueChange={handleAssign}
            disabled={assigning}
          >
            <SelectTrigger className="h-7 text-xs w-40">
              <SelectValue placeholder="Unassigned" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__unassign__">Unassigned</SelectItem>
              {teamMembers.map((m) => (
                <SelectItem key={m.user_id} value={m.user_id}>
                  {m.first_name} {m.last_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {assigning && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        </div>
        <p className="text-sm font-medium">
          {thread.customer_name || thread.contact_email}
        </p>
        <p className="text-xs text-muted-foreground">{thread.contact_email}</p>
        {thread.subject && (
          <p className="text-sm text-muted-foreground">Re: {thread.subject}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {thread.message_count} message{thread.message_count !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Conversation timeline */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {thread.timeline.map((msg) => {
          const isInbound = msg.direction === "inbound";
          const isPending = msg.status === "pending" && isInbound;
          const timestamp = isInbound ? msg.received_at : msg.sent_at;

          return (
            <div key={msg.id} className={`flex ${isInbound ? "justify-start" : "justify-end"}`}>
              <div
                className={`max-w-[85%] rounded-lg p-3 text-sm space-y-1 ${
                  isPending
                    ? "bg-amber-50 dark:bg-amber-950/30 border-l-4 border-amber-400"
                    : isInbound
                    ? "bg-muted/50"
                    : "bg-blue-50 dark:bg-blue-950/30"
                }`}
              >
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium">
                    {isInbound ? (msg.from_email.split("@")[0]) : "Sapphire Pools"}
                  </span>
                  <span>{formatTime(timestamp)}</span>
                  {!isInbound && msg.approved_by && (
                    <span className="text-[10px]">by {msg.approved_by}</span>
                  )}
                </div>
                {msg.subject && (
                  <p className="text-xs font-medium text-muted-foreground">{msg.subject}</p>
                )}
                <CollapsibleBody text={msg.body || "No content"} />
              </div>
            </div>
          );
        })}
        <div ref={timelineEndRef} />
      </div>

      {/* Bottom action area */}
      <div className="flex-shrink-0 border-t pt-4 space-y-3">
        {/* Draft area for pending messages */}
        {pendingMessage && pendingMessage.draft_response && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Draft Response</p>
              {!editing && (
                <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setEditing(true)}>
                  <Pencil className="h-3 w-3 mr-1" />Edit
                </Button>
              )}
            </div>
            {editing ? (
              <Textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={5}
                className="text-sm"
              />
            ) : (
              <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-md p-3 text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">
                {pendingMessage.draft_response}
              </div>
            )}
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input
                  value={reviseInstruction}
                  onChange={(e) => setReviseInstruction(e.target.value)}
                  placeholder="Tell AI how to change it..."
                  className="text-sm h-8"
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleReviseDraft(); } }}
                />
              </div>
              <Button variant="outline" size="sm" className="h-8" onClick={handleReviseDraft} disabled={revising || !reviseInstruction.trim()}>
                {revising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => handleApprove(editing ? editText : undefined)}
                disabled={sending}
                className="flex-1"
              >
                {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
                {editing ? "Send Edited" : "Approve & Send"}
              </Button>
              {editing && (
                <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setEditText(pendingMessage.draft_response || ""); }}>
                  Cancel Edit
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Follow-up area for handled threads */}
        {!thread.has_pending && thread.status === "handled" && !followUp && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftFollowUp}
            disabled={draftingFollowUp}
          >
            {draftingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
            Draft Follow-up
          </Button>
        )}

        {followUp && (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Follow-up Draft</p>
            <p className="text-xs text-muted-foreground">To: {followUp.to} — Re: {followUp.subject}</p>
            <Textarea
              value={followUpText}
              onChange={(e) => setFollowUpText(e.target.value)}
              rows={5}
              className="text-sm"
            />
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input
                  value={followUpRevise}
                  onChange={(e) => setFollowUpRevise(e.target.value)}
                  placeholder="Tell AI how to change it..."
                  className="text-sm h-8"
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleReviseFollowUp(); } }}
                />
              </div>
              <Button variant="outline" size="sm" className="h-8" onClick={handleReviseFollowUp} disabled={followUpRevising || !followUpRevise.trim()}>
                {followUpRevising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
              </Button>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleSendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}>
                {sendingFollowUp ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
                Send Follow-up
              </Button>
              <Button variant="ghost" onClick={() => { setFollowUp(null); setFollowUpText(""); setFollowUpRevise(""); }}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Dismiss + Delete */}
        <div className="flex justify-between pt-2 border-t">
          {thread.has_pending && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="text-xs text-muted-foreground" disabled={sending}>
                  Dismiss
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Dismiss this thread?</AlertDialogTitle>
                  <AlertDialogDescription>
                    No reply will be sent for the pending message.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDismiss}>Dismiss</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>
    </div>
  );
}
