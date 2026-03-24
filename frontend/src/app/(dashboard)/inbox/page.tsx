"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  MailCheck,
  MailX,
  Clock,
  Search,
  Send,
  X,
  Pencil,
  Bot,
  Inbox,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Timer,
  ClipboardList,
  Plus,
  Trash2,
  Mail,
} from "lucide-react";

interface AgentAction {
  id: string;
  agent_message_id: string;
  action_type: string;
  description: string;
  assigned_to: string | null;
  due_date: string | null;
  status: string;
  completed_at: string | null;
  created_at: string | null;
  // Joined from message
  from_email?: string;
  customer_name?: string;
  subject?: string;
}

interface AgentMessage {
  id: string;
  direction: string;
  from_email: string;
  to_email: string;
  subject: string | null;
  body?: string;
  category: string | null;
  urgency: string | null;
  status: string;
  matched_customer_id: string | null;
  match_method: string | null;
  customer_name: string | null;
  draft_response: string | null;
  final_response: string | null;
  approved_by: string | null;
  notes: string | null;
  received_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  actions?: AgentAction[];
  response_time_seconds?: number | null;
  waiting_seconds?: number | null;
}

interface PaginatedMessages {
  items: AgentMessage[];
  total: number;
  limit: number;
  offset: number;
}

const PAGE_SIZE = 25;

interface AgentStats {
  total: number;
  pending: number;
  sent: number;
  auto_sent: number;
  rejected: number;
  ignored: number;
  by_category: Record<string, number>;
  by_urgency: Record<string, number>;
  recent_24h: number;
  open_actions: number;
  overdue_actions: number;
  avg_response_seconds: number | null;
  stale_pending: number;
}

const STATUS_FILTERS = ["all", "pending", "sent", "auto_sent", "rejected", "ignored"] as const;
const ACTION_TYPES = ["follow_up", "bid", "schedule_change", "site_visit", "callback", "repair", "equipment", "other"];
const TEAM_MEMBERS = ["Brian", "Chance", "Kim"];

function formatTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatFullDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function formatDuration(seconds: number | null | undefined) {
  if (!seconds) return "—";
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  return remMin > 0 ? `${hr}h ${remMin}m` : `${hr}h`;
}

function formatDueDate(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.ceil((d.getTime() - now.getTime()) / 86400000);
  if (diffDays < 0) return `${Math.abs(diffDays)}d overdue`;
  if (diffDays === 0) return "Due today";
  if (diffDays === 1) return "Due tomorrow";
  return `Due in ${diffDays}d`;
}

function isOverdue(iso: string | null) {
  if (!iso) return false;
  return new Date(iso) < new Date();
}

function isStale(receivedAt: string | null) {
  if (!receivedAt) return false;
  return (Date.now() - new Date(receivedAt).getTime()) > 30 * 60 * 1000;
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Badge variant="outline" className="border-amber-400 text-amber-600">Pending</Badge>;
    case "sent":
      return <Badge variant="default" className="bg-green-600">Sent</Badge>;
    case "auto_sent":
      return <Badge variant="default" className="bg-blue-600">Auto</Badge>;
    case "rejected":
      return <Badge variant="destructive">Rejected</Badge>;
    case "ignored":
      return <Badge variant="secondary">Ignored</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function UrgencyBadge({ urgency }: { urgency: string | null }) {
  if (!urgency) return null;
  switch (urgency) {
    case "high":
      return <Badge variant="destructive" className="text-[10px] px-1.5">High</Badge>;
    case "medium":
      return <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px] px-1.5">Med</Badge>;
    case "low":
      return <Badge variant="secondary" className="text-[10px] px-1.5">Low</Badge>;
    default:
      return null;
  }
}

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const styles: Record<string, string> = {
    schedule: "border-blue-400 text-blue-600",
    complaint: "border-red-400 text-red-600",
    billing: "border-amber-400 text-amber-600",
    gate_code: "border-green-400 text-green-600",
    service_request: "border-purple-400 text-purple-600",
    general: "",
  };
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 capitalize ${styles[category] || ""}`}>
      {category.replace("_", " ")}
    </Badge>
  );
}

function ActionTypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    bid: "border-green-400 text-green-600",
    follow_up: "border-blue-400 text-blue-600",
    schedule_change: "border-purple-400 text-purple-600",
    site_visit: "border-amber-400 text-amber-600",
    callback: "border-cyan-400 text-cyan-600",
    repair: "border-red-400 text-red-600",
    equipment: "border-orange-400 text-orange-600",
    other: "",
  };
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 capitalize ${styles[type] || ""}`}>
      {type.replace("_", " ")}
    </Badge>
  );
}

function ActionStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "open":
      return <Circle className="h-3.5 w-3.5 text-amber-500" />;
    case "in_progress":
      return <Timer className="h-3.5 w-3.5 text-blue-500" />;
    case "done":
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case "cancelled":
      return <X className="h-3.5 w-3.5 text-muted-foreground" />;
    default:
      return <Circle className="h-3.5 w-3.5 text-muted-foreground" />;
  }
}

function ActionItem({ action, onUpdate }: { action: AgentAction; onUpdate: () => void }) {
  const [updating, setUpdating] = useState(false);

  const updateStatus = async (newStatus: string) => {
    setUpdating(true);
    try {
      await api.put(`/v1/admin/agent-actions/${action.id}`, { status: newStatus });
      onUpdate();
    } catch {
      toast.error("Failed to update action");
    } finally {
      setUpdating(false);
    }
  };

  const updateAssignee = async (assignee: string) => {
    try {
      await api.put(`/v1/admin/agent-actions/${action.id}`, { assigned_to: assignee });
      onUpdate();
    } catch {
      toast.error("Failed to assign");
    }
  };

  const overdue = action.status !== "done" && action.status !== "cancelled" && isOverdue(action.due_date);

  return (
    <div className={`flex items-start gap-2 p-2 rounded-md text-sm ${overdue ? "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800" : "bg-muted/50"}`}>
      <button onClick={() => updateStatus(action.status === "done" ? "open" : "done")} disabled={updating} className="mt-0.5">
        {updating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ActionStatusIcon status={action.status} />}
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <ActionTypeBadge type={action.action_type} />
          {overdue && <Badge variant="destructive" className="text-[10px] px-1.5">Overdue</Badge>}
        </div>
        <p className={`mt-0.5 ${action.status === "done" ? "line-through text-muted-foreground" : ""}`}>
          {action.description}
        </p>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          {action.due_date && (
            <span className={overdue ? "text-red-600 font-medium" : ""}>
              {formatDueDate(action.due_date)}
            </span>
          )}
          <Select value={action.assigned_to || ""} onValueChange={updateAssignee}>
            <SelectTrigger className="h-5 w-auto border-none bg-transparent p-0 text-xs gap-1 shadow-none">
              <SelectValue placeholder="Unassigned" />
            </SelectTrigger>
            <SelectContent>
              {TEAM_MEMBERS.map((name) => (
                <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {action.status !== "done" && action.status !== "cancelled" && (
            <button className="hover:text-foreground" onClick={() => updateStatus("in_progress")}>
              {action.status === "open" ? "Start" : ""}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function MessageDetail({
  messageId,
  onClose,
  onAction,
}: {
  messageId: string;
  onClose: () => void;
  onAction: () => void;
}) {
  const [msg, setMsg] = useState<AgentMessage | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [sending, setSending] = useState(false);
  const [addingAction, setAddingAction] = useState(false);
  const [newAction, setNewAction] = useState({ action_type: "follow_up", description: "", assigned_to: "", due_days: "3" });
  const [followUp, setFollowUp] = useState<{ draft: string; to: string; subject: string } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);

  const loadMsg = useCallback(() => {
    setLoading(true);
    api.get<AgentMessage>(`/v1/admin/agent-messages/${messageId}`)
      .then((m) => {
        setMsg(m);
        setEditText(m.draft_response || "");
      })
      .catch(() => toast.error("Failed to load message"))
      .finally(() => setLoading(false));
  }, [messageId]);

  useEffect(() => { loadMsg(); }, [loadMsg]);

  const handleApprove = async (responseText?: string) => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-messages/${messageId}/approve`, {
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

  const handleReject = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-messages/${messageId}/reject`, {});
      toast.success("Message rejected");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to reject");
    } finally {
      setSending(false);
    }
  };

  const handleDismiss = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-messages/${messageId}/dismiss`, {});
      toast.success("Message dismissed");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to dismiss");
    } finally {
      setSending(false);
    }
  };

  const handleDraftFollowUp = async () => {
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{ draft: string; to: string; subject: string }>(`/v1/admin/agent-messages/${messageId}/draft-followup`, {});
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
      await api.post(`/v1/admin/agent-messages/${messageId}/send-followup`, { response_text: followUpText });
      toast.success("Follow-up sent");
      setFollowUp(null);
      setFollowUpText("");
      onAction();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const handleDelete = async () => {
    setSending(true);
    try {
      await api.delete(`/v1/admin/agent-messages/${messageId}`);
      toast.success("Message deleted");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to delete");
    } finally {
      setSending(false);
    }
  };

  const handleAddAction = async () => {
    if (!newAction.description.trim()) return;
    const dueDate = newAction.due_days
      ? new Date(Date.now() + parseInt(newAction.due_days) * 86400000).toISOString()
      : undefined;
    try {
      await api.post("/v1/admin/agent-actions", {
        agent_message_id: messageId,
        action_type: newAction.action_type,
        description: newAction.description,
        assigned_to: newAction.assigned_to || undefined,
        due_date: dueDate,
      });
      setAddingAction(false);
      setNewAction({ action_type: "follow_up", description: "", assigned_to: "", due_days: "3" });
      loadMsg();
      onAction();
    } catch {
      toast.error("Failed to create action");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!msg) return null;

  return (
    <div className="space-y-4">
      {/* Header info */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={msg.status} />
          <UrgencyBadge urgency={msg.urgency} />
          <CategoryBadge category={msg.category} />
          {msg.status === "pending" && isStale(msg.received_at) && (
            <Badge variant="destructive" className="text-[10px] px-1.5">
              <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />Stale
            </Badge>
          )}
        </div>
        <div className="text-sm space-y-1">
          <p><span className="text-muted-foreground">From:</span> {msg.customer_name ? `${msg.customer_name} <${msg.from_email}>` : msg.from_email}</p>
          {msg.matched_customer_id && (
            <p className="flex items-center gap-1">
              <span className="text-muted-foreground">Matched:</span>
              <Badge variant="outline" className="text-[10px] px-1.5 border-green-400 text-green-600 capitalize">
                {(msg.match_method || "unknown").replace("_", " ")}
              </Badge>
            </p>
          )}
          {!msg.matched_customer_id && msg.status === "pending" && (
            <p className="text-amber-600 text-xs font-medium">No customer match found</p>
          )}
          <p><span className="text-muted-foreground">To:</span> {msg.to_email}</p>
          <p><span className="text-muted-foreground">Received:</span> {formatFullDate(msg.received_at)}</p>
          {msg.sent_at && (
            <p>
              <span className="text-muted-foreground">Sent:</span> {formatFullDate(msg.sent_at)}
              {msg.response_time_seconds != null && (
                <span className="ml-2 text-xs text-muted-foreground">
                  (responded in {formatDuration(msg.response_time_seconds)})
                </span>
              )}
            </p>
          )}
          {msg.status === "pending" && msg.waiting_seconds != null && (
            <p className={msg.waiting_seconds > 1800 ? "text-red-600 font-medium" : "text-amber-600"}>
              <Clock className="h-3 w-3 inline mr-1" />
              Waiting {formatDuration(msg.waiting_seconds)}
            </p>
          )}
          {msg.approved_by && <p><span className="text-muted-foreground">Handled by:</span> {msg.approved_by}</p>}
        </div>
      </div>

      {/* Email body */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">Email Body</p>
        <div className="bg-muted/50 rounded-md p-3 text-sm whitespace-pre-wrap max-h-64 overflow-y-auto">
          {msg.body || "No body content"}
        </div>
      </div>

      {/* Draft response */}
      {msg.draft_response && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {msg.status === "pending" ? "Draft Response" : "Draft"}
            </p>
            {msg.status === "pending" && !editing && (
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
            <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-md p-3 text-sm whitespace-pre-wrap">
              {msg.draft_response}
            </div>
          )}
        </div>
      )}

      {/* Final response (if different from draft) */}
      {msg.final_response && msg.final_response !== msg.draft_response && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">Sent Response</p>
          <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-md p-3 text-sm whitespace-pre-wrap">
            {msg.final_response}
          </div>
        </div>
      )}

      {/* Notes */}
      {msg.notes && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">Internal Note</p>
          <p className="text-sm text-muted-foreground">{msg.notes}</p>
        </div>
      )}

      {/* Action Items */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-1">
            <ClipboardList className="h-3 w-3" />Action Items
            {msg.actions && msg.actions.length > 0 && (
              <span className="ml-1 text-[10px] bg-muted rounded-full px-1.5">{msg.actions.filter(a => a.status !== "done" && a.status !== "cancelled").length} open</span>
            )}
          </p>
          <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setAddingAction(!addingAction)}>
            <Plus className="h-3 w-3 mr-1" />Add
          </Button>
        </div>

        {addingAction && (
          <div className="space-y-2 p-3 bg-muted/50 rounded-md mb-2">
            <div className="flex gap-2">
              <Select value={newAction.action_type} onValueChange={(v) => setNewAction({ ...newAction, action_type: v })}>
                <SelectTrigger className="h-8 text-xs w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ACTION_TYPES.map((t) => (
                    <SelectItem key={t} value={t} className="text-xs capitalize">{t.replace("_", " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={newAction.assigned_to} onValueChange={(v) => setNewAction({ ...newAction, assigned_to: v })}>
                <SelectTrigger className="h-8 text-xs w-28">
                  <SelectValue placeholder="Assign..." />
                </SelectTrigger>
                <SelectContent>
                  {TEAM_MEMBERS.map((name) => (
                    <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="number"
                placeholder="Days"
                value={newAction.due_days}
                onChange={(e) => setNewAction({ ...newAction, due_days: e.target.value })}
                className="h-8 text-xs w-16"
              />
            </div>
            <Input
              placeholder="What needs to happen?"
              value={newAction.description}
              onChange={(e) => setNewAction({ ...newAction, description: e.target.value })}
              className="h-8 text-sm"
              autoFocus
            />
            <div className="flex gap-2">
              <Button size="sm" className="h-7 text-xs" onClick={handleAddAction}>Add</Button>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setAddingAction(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {msg.actions && msg.actions.length > 0 ? (
          <div className="space-y-1.5">
            {msg.actions.map((a) => (
              <ActionItem key={a.id} action={a} onUpdate={() => { loadMsg(); onAction(); }} />
            ))}
          </div>
        ) : !addingAction ? (
          <p className="text-xs text-muted-foreground py-2">No action items</p>
        ) : null}
      </div>

      {/* Approve/Reject buttons */}
      {msg.status === "pending" && (
        <div className="flex items-center gap-2 pt-2 border-t">
          <Button
            onClick={() => handleApprove(editing ? editText : undefined)}
            disabled={sending}
            className="flex-1"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            {editing ? "Send Edited" : "Approve & Send"}
          </Button>
          {editing && (
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel Edit
            </Button>
          )}
          <Button variant="secondary" disabled={sending} onClick={handleDismiss}>
            Dismiss
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={sending}>
                <X className="h-4 w-4 mr-1" />Reject
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reject this message?</AlertDialogTitle>
                <AlertDialogDescription>
                  No reply will be sent to {msg.from_email}. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleReject}>Reject</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}

      {/* Follow-up — for sent messages */}
      {(msg.status === "sent" || msg.status === "auto_sent") && !followUp && (
        <div className="pt-2 border-t">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftFollowUp}
            disabled={draftingFollowUp}
          >
            {draftingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
            Draft Follow-up
          </Button>
        </div>
      )}

      {followUp && (
        <div className="pt-2 border-t space-y-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">Follow-up Draft</p>
            <p className="text-xs text-muted-foreground mb-2">To: {followUp.to} — Re: {followUp.subject}</p>
            <Textarea
              value={followUpText}
              onChange={(e) => setFollowUpText(e.target.value)}
              rows={6}
              className="text-sm"
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}>
              {sendingFollowUp ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              Send Follow-up
            </Button>
            <Button variant="ghost" onClick={() => { setFollowUp(null); setFollowUpText(""); }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Delete — available for any status */}
      <div className="pt-2 border-t">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-destructive" disabled={sending}>
              <Trash2 className="h-3 w-3 mr-1" />Delete Message
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete this message?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently remove the message and all associated action items. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}

interface ActionComment {
  id: string;
  author: string;
  text: string;
  created_at: string;
}

interface ActionDetail extends AgentAction {
  comments?: ActionComment[];
  notes?: string | null;
  from_email?: string;
  customer_name?: string;
  subject?: string;
}

function ActionDetailSheet({
  actionId,
  onClose,
  onUpdate,
}: {
  actionId: string;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [followUp, setFollowUp] = useState<{ draft: string; to: string; subject: string } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);

  const handleDraftFollowUp = async () => {
    if (!detail) return;
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{ draft: string; to: string; subject: string }>(`/v1/admin/agent-messages/${detail.agent_message_id}/draft-followup`, {});
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
      await api.post(`/v1/admin/agent-messages/${detail.agent_message_id}/send-followup`, { response_text: followUpText });
      toast.success("Follow-up sent");
      setFollowUp(null);
      setFollowUpText("");
      onUpdate();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const loadDetail = useCallback(() => {
    setLoading(true);
    api.get<ActionDetail>(`/v1/admin/agent-actions/${actionId}`)
      .then((d) => { setDetail(d); })
      .catch(() => toast.error("Failed to load action"))
      .finally(() => setLoading(false));
  }, [actionId]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  const handleAddComment = async () => {
    if (!comment.trim()) return;
    setPosting(true);
    try {
      await api.post(`/v1/admin/agent-actions/${actionId}/comments`, { text: comment });
      setComment("");
      loadDetail();
    } catch {
      toast.error("Failed to add comment");
    } finally {
      setPosting(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }
  if (!detail) return null;

  return (
    <div className="space-y-5 pt-2">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <ActionStatusIcon status={detail.status} />
          <ActionTypeBadge type={detail.action_type} />
          {detail.due_date && isOverdue(detail.due_date) && detail.status !== "done" && (
            <Badge variant="destructive" className="text-[10px] px-1.5">Overdue</Badge>
          )}
        </div>
        <p className="text-sm font-medium">{detail.description}</p>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{detail.customer_name || detail.from_email}</span>
          {detail.assigned_to && <span>Assigned: {detail.assigned_to}</span>}
          {detail.due_date && <span>{formatDueDate(detail.due_date)}</span>}
        </div>
      </div>

      {/* Source email ref */}
      {detail.subject && (
        <div className="bg-muted/50 rounded-md p-3 text-sm">
          <p className="text-xs text-muted-foreground mb-1">From email</p>
          <p className="font-medium">{detail.subject}</p>
        </div>
      )}

      {/* Comments / Activity */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">Activity</p>
        {detail.comments && detail.comments.length > 0 ? (
          <div className="space-y-2 mb-3">
            {detail.comments.map((c) => (
              <div key={c.id} className="bg-muted/50 rounded-md p-2.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium">{c.author}</span>
                  <span className="text-[10px] text-muted-foreground">{formatTime(c.created_at)}</span>
                </div>
                <p className="text-sm">{c.text}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground mb-3">No comments yet</p>
        )}
        <div className="space-y-2">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment..."
            className="text-sm min-h-[2.5rem] resize-none"
            rows={2}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAddComment(); } }}
          />
          <div className="flex justify-end">
            <Button size="sm" className="h-7" onClick={handleAddComment} disabled={posting || !comment.trim()}>
              {posting ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Post
            </Button>
          </div>
        </div>
      </div>

      {/* Draft Follow-up */}
      {!followUp && (
        <div className="pt-2 border-t">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftFollowUp}
            disabled={draftingFollowUp}
          >
            {draftingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
            Draft Follow-up Email
          </Button>
        </div>
      )}

      {followUp && (
        <div className="pt-2 border-t space-y-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">Follow-up Draft</p>
            <p className="text-xs text-muted-foreground mb-2">To: {followUp.to} — Re: {followUp.subject}</p>
            <Textarea
              value={followUpText}
              onChange={(e) => setFollowUpText(e.target.value)}
              rows={6}
              className="text-sm"
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}>
              {sendingFollowUp ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              Send
            </Button>
            <Button variant="ghost" onClick={() => { setFollowUp(null); setFollowUpText(""); }}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [totalMessages, setTotalMessages] = useState(0);
  const [page, setPage] = useState(0);
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"inbox" | "actions">("inbox");
  const [suggestion, setSuggestion] = useState<{ id: string; action_type: string; description: string; reasoning: string } | null>(null);

  const handleToggleAction = async (actionId: string, currentStatus: string) => {
    const newStatus = currentStatus === "done" ? "open" : "done";
    try {
      const result = await api.put<{ suggestion?: { id: string; action_type: string; description: string; reasoning: string } }>(`/v1/admin/agent-actions/${actionId}`, { status: newStatus });
      if (result.suggestion) {
        setSuggestion(result.suggestion);
      }
      load();
    } catch { toast.error("Failed to update"); }
  };

  const totalPages = Math.ceil(totalMessages / PAGE_SIZE);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (searchQuery) params.set("search", searchQuery);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(page * PAGE_SIZE));
      const qs = params.toString();
      const [paginated, st, acts] = await Promise.all([
        api.get<PaginatedMessages>(`/v1/admin/agent-messages?${qs}`),
        api.get<AgentStats>("/v1/admin/agent-stats"),
        Promise.all([
              api.get<AgentAction[]>("/v1/admin/agent-actions?status=open").catch(() => []),
              api.get<AgentAction[]>("/v1/admin/agent-actions?status=in_progress").catch(() => []),
            ]).then(([a, b]) => [...a, ...b]),
      ]);
      setMessages(paginated.items);
      setTotalMessages(paginated.total);
      setStats(st);
      setActions(acts);
    } catch {
      toast.error("Failed to load agent data");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchQuery, page]);

  useEffect(() => { load(); }, [load]);

  // Poll every 30s
  useEffect(() => {
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  // Debounced search — reset to page 0
  const [searchInput, setSearchInput] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => { setSearchQuery(searchInput); setPage(0); }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bot className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Inbox</h1>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <Card
            className={`shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md ${stats.pending > 0 ? "border-l-4 border-amber-400" : ""} ${statusFilter === "pending" && activeTab === "inbox" ? "ring-2 ring-primary" : ""}`}
            onClick={() => { setActiveTab("inbox"); setStatusFilter("pending"); setPage(0); }}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-amber-500" />
                <CardTitle className="text-sm font-medium">Pending</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.pending}</p>
              {stats.stale_pending > 0 && (
                <p className="text-xs text-red-600 font-medium">{stats.stale_pending} stale</p>
              )}
            </CardContent>
          </Card>
          <Card
            className={`shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md ${statusFilter === "sent" && activeTab === "inbox" ? "ring-2 ring-primary" : ""}`}
            onClick={() => { setActiveTab("inbox"); setStatusFilter("sent"); setPage(0); }}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <MailCheck className="h-4 w-4 text-green-500" />
                <CardTitle className="text-sm font-medium">Sent</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.sent}</p>
            </CardContent>
          </Card>
          <Card
            className={`shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md ${statusFilter === "auto_sent" && activeTab === "inbox" ? "ring-2 ring-primary" : ""}`}
            onClick={() => { setActiveTab("inbox"); setStatusFilter("auto_sent"); setPage(0); }}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-blue-500" />
                <CardTitle className="text-sm font-medium">Auto-sent</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.auto_sent}</p>
            </CardContent>
          </Card>
          <Card
            className="shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => { setActiveTab("inbox"); setStatusFilter("all"); setPage(0); }}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Timer className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Avg Response</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{formatDuration(stats.avg_response_seconds)}</p>
            </CardContent>
          </Card>
          <Card
            className={`shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md ${stats.overdue_actions > 0 ? "border-l-4 border-red-500" : ""} ${activeTab === "actions" ? "ring-2 ring-primary" : ""}`}
            onClick={() => setActiveTab("actions")}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-purple-500" />
                <CardTitle className="text-sm font-medium">Open Actions</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.open_actions}</p>
              {stats.overdue_actions > 0 && (
                <p className="text-xs text-red-600 font-medium">{stats.overdue_actions} overdue</p>
              )}
            </CardContent>
          </Card>
          <Card
            className="shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => { setActiveTab("inbox"); setStatusFilter("all"); setPage(0); }}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <Inbox className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Last 24h</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.recent_24h}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* AI Suggestion banner */}
      {suggestion && (
        <Card className="shadow-sm border-l-4 border-blue-500 bg-blue-50/50 dark:bg-blue-950/20">
          <CardContent className="py-3 px-4">
            <div className="flex items-start gap-3">
              <Bot className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">Suggested next step</p>
                <p className="text-sm mt-0.5">{suggestion.description}</p>
                <p className="text-xs text-muted-foreground mt-1">{suggestion.reasoning}</p>
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
                <Button
                  size="sm"
                  className="h-7"
                  onClick={async () => {
                    try {
                      await api.put(`/v1/admin/agent-actions/${suggestion.id}`, { status: "open" });
                      toast.success("Action accepted");
                      setSuggestion(null);
                      load();
                    } catch { toast.error("Failed"); }
                  }}
                >
                  Accept
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7"
                  onClick={async () => {
                    try {
                      await api.put(`/v1/admin/agent-actions/${suggestion.id}`, { status: "cancelled" });
                      setSuggestion(null);
                      load();
                    } catch { toast.error("Failed"); }
                  }}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tab toggle */}
      <div className="flex gap-1 border-b">
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === "inbox" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          onClick={() => setActiveTab("inbox")}
        >
          Inbox
        </button>
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${activeTab === "actions" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          onClick={() => setActiveTab("actions")}
        >
          Action Items
          {actions.length > 0 && (
            <span className="bg-primary text-primary-foreground text-[10px] rounded-full px-1.5 py-0.5 leading-none">
              {actions.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === "inbox" && (
        <>
          {/* Filters */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex gap-1 flex-wrap">
              {STATUS_FILTERS.map((s) => (
                <Button
                  key={s}
                  variant={statusFilter === s ? "default" : "outline"}
                  size="sm"
                  className="text-xs capitalize"
                  onClick={() => { setStatusFilter(s); setPage(0); }}
                >
                  {s === "auto_sent" ? "Auto" : s}
                </Button>
              ))}
            </div>
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search by name, email, subject..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="pl-8 h-9 text-sm"
              />
            </div>
          </div>

          {/* Message table */}
          <Card className="shadow-sm">
            <CardContent className="p-0">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                  <Inbox className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm">No messages found</p>
                </div>
              ) : (
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-100 dark:bg-slate-800">
                        <TableHead className="text-xs font-medium uppercase tracking-wide w-24">Time</TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide">From</TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide">Subject</TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide w-24">Category</TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide w-16">Urgency</TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide w-20">Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {messages.map((m, i) => {
                        const stale = m.status === "pending" && isStale(m.received_at);
                        return (
                          <TableRow
                            key={m.id}
                            className={`cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""} ${m.status === "pending" ? "font-medium" : ""} ${stale ? "!bg-red-50 dark:!bg-red-950/20" : ""}`}
                            onClick={() => setSelectedId(m.id)}
                          >
                            <TableCell className="text-sm text-muted-foreground">
                              {formatTime(m.received_at)}
                              {stale && <AlertTriangle className="h-3 w-3 text-red-500 inline ml-1" />}
                            </TableCell>
                            <TableCell className="text-sm">
                              {m.customer_name || m.from_email}
                            </TableCell>
                            <TableCell className="text-sm text-muted-foreground truncate max-w-64">
                              {m.subject}
                            </TableCell>
                            <TableCell><CategoryBadge category={m.category} /></TableCell>
                            <TableCell><UrgencyBadge urgency={m.urgency} /></TableCell>
                            <TableCell><StatusBadge status={m.status} /></TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
              {/* Pagination */}
              {totalMessages > PAGE_SIZE && (
                <div className="flex items-center justify-between px-4 py-3 border-t">
                  <p className="text-xs text-muted-foreground">
                    {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalMessages)} of {totalMessages}
                  </p>
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      disabled={page === 0}
                      onClick={() => setPage(page - 1)}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      disabled={page >= totalPages - 1}
                      onClick={() => setPage(page + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {activeTab === "actions" && (() => {
        // Group actions by parent message (event)
        const grouped = new Map<string, { label: string; from: string; actions: AgentAction[] }>();
        for (const a of actions) {
          const key = a.agent_message_id;
          if (!grouped.has(key)) {
            grouped.set(key, {
              label: a.subject || "Unknown",
              from: a.customer_name || a.from_email || "",
              actions: [],
            });
          }
          grouped.get(key)!.actions.push(a);
        }
        const groups = Array.from(grouped.entries());

        return (
          <Card className="shadow-sm">
            <CardContent className="p-0">
              {actions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                  <CheckCircle2 className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm">All caught up — no open actions</p>
                </div>
              ) : (
                <div className="divide-y">
                  {groups.map(([msgId, group]) => {
                    const doneCount = group.actions.filter(a => a.status === "done").length;
                    const hasOverdue = group.actions.some(a => a.status !== "done" && a.status !== "cancelled" && isOverdue(a.due_date));
                    return (
                      <div key={msgId} className={hasOverdue ? "bg-red-50/50 dark:bg-red-950/10" : ""}>
                        {/* Event header */}
                        <div className="flex items-center justify-between px-4 pt-3 pb-1">
                          <div className="flex items-center gap-2 min-w-0">
                            <p className="text-sm font-medium truncate">{group.from}</p>
                            <span className="text-xs text-muted-foreground truncate hidden sm:inline">— {group.label}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span className="text-[10px] text-muted-foreground">{doneCount}/{group.actions.length}</span>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-muted-foreground hover:text-primary"
                              title="View message"
                              onClick={() => { setSelectedId(msgId); setActiveTab("inbox"); }}
                            >
                              <Mail className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                        {/* Actions under this event */}
                        <div className="px-4 pb-3 space-y-1">
                          {group.actions.map((a) => {
                            const overdue = a.status !== "done" && a.status !== "cancelled" && isOverdue(a.due_date);
                            return (
                              <div
                                key={a.id}
                                className={`flex items-start gap-2 py-1.5 pl-2 rounded cursor-pointer ${overdue ? "bg-red-50 dark:bg-red-950/20" : "hover:bg-muted/50"}`}
                                onClick={() => setSelectedActionId(a.id)}
                              >
                                <ActionStatusIcon status={a.status} />
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <ActionTypeBadge type={a.action_type} />
                                    {overdue && <Badge variant="destructive" className="text-[10px] px-1.5">Overdue</Badge>}
                                    {a.due_date && (
                                      <span className={`text-[10px] ${overdue ? "text-red-600 font-medium" : "text-muted-foreground"}`}>
                                        {formatDueDate(a.due_date)}
                                      </span>
                                    )}
                                  </div>
                                  <p className={`text-sm mt-0.5 ${a.status === "done" ? "line-through text-muted-foreground" : ""}`}>
                                    {a.description}
                                  </p>
                                  <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                                    <Select
                                      value={a.assigned_to || ""}
                                      onValueChange={async (v) => {
                                        try {
                                          await api.put(`/v1/admin/agent-actions/${a.id}`, { assigned_to: v });
                                          load();
                                        } catch { toast.error("Failed to assign"); }
                                      }}
                                    >
                                      <SelectTrigger className="h-5 w-auto border-none bg-transparent p-0 text-xs gap-1 shadow-none">
                                        <SelectValue placeholder="Assign..." />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {TEAM_MEMBERS.map((name) => (
                                          <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                                  {(a.status === "open" || a.status === "in_progress") && (
                                    <>
                                      <Button
                                        variant="default"
                                        size="sm"
                                        className="h-6 text-[10px] px-2 bg-green-600 hover:bg-green-700"
                                        onClick={() => handleToggleAction(a.id, a.status)}
                                      >
                                        Done
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-5 w-5 text-muted-foreground hover:text-destructive"
                                        title="Cancel"
                                        onClick={async () => {
                                          try {
                                            await api.put(`/v1/admin/agent-actions/${a.id}`, { status: "cancelled" });
                                            load();
                                          } catch { toast.error("Failed"); }
                                        }}
                                      >
                                        <X className="h-3 w-3" />
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })()}

      {/* Detail sheet */}
      <Sheet open={!!selectedId} onOpenChange={(open) => { if (!open) setSelectedId(null); }}>
        <SheetContent className="w-full sm:max-w-lg flex flex-col h-full">
          <SheetHeader className="px-4 sm:px-6 flex-shrink-0">
            <SheetTitle className="text-lg">
              {messages.find((m) => m.id === selectedId)?.subject || "Message Detail"}
            </SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 pb-6">
            {selectedId && (
              <MessageDetail
                messageId={selectedId}
                onClose={() => setSelectedId(null)}
                onAction={load}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>

      {/* Action detail sheet */}
      <Sheet open={!!selectedActionId} onOpenChange={(open) => { if (!open) setSelectedActionId(null); }}>
        <SheetContent className="w-full sm:max-w-md flex flex-col h-full">
          <SheetHeader className="px-4 sm:px-6 flex-shrink-0">
            <SheetTitle className="text-lg">Action Detail</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 pb-6">
            {selectedActionId && (
              <ActionDetailSheet
                actionId={selectedActionId}
                onClose={() => setSelectedActionId(null)}
                onUpdate={load}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
