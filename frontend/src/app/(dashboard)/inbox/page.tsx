"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  DollarSign,
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

const STATUS_FILTERS = ["all", "clients", "pending", "sent", "auto_sent", "ignored"] as const;
const ACTION_TYPES = ["follow_up", "bid", "schedule_change", "site_visit", "callback", "repair", "equipment", "other"];
// Dynamic team member list
let _cachedTeam: string[] | null = null;
function useTeamMembers() {
  const [members, setMembers] = useState<string[]>(_cachedTeam || []);
  useEffect(() => {
    if (_cachedTeam) return;
    api.get<{ first_name: string; is_verified: boolean; is_active: boolean }[]>("/v1/team")
      .then((data) => {
        const names = data.filter((m) => m.is_verified && m.is_active).map((m) => m.first_name);
        _cachedTeam = names;
        setMembers(names);
      })
      .catch(() => {});
  }, []);
  return members;
}

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
    invoice: "border-emerald-400 text-emerald-600",
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
  const teamMembers = useTeamMembers();
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
              {teamMembers.map((name) => (
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
  const teamMembers = useTeamMembers();
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
  const [reviseInstruction, setReviseInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [draftReviseInstruction, setDraftReviseInstruction] = useState("");
  const [draftRevising, setDraftRevising] = useState(false);

  const handleReviseDraft = async () => {
    if (!draftReviseInstruction.trim()) return;
    const currentDraft = editText || msg?.draft_response || "";
    if (!currentDraft) return;
    setDraftRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-messages/${messageId}/revise-draft`, {
        draft: currentDraft,
        instruction: draftReviseInstruction,
      });
      setEditText(result.draft);
      setEditing(true);
      setDraftReviseInstruction("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setDraftRevising(false);
    }
  };

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
      const result = await api.post<{ sent: boolean; closed_actions: { description: string }[]; ask_actions: { id: string; description: string; reason: string }[] }>(`/v1/admin/agent-messages/${messageId}/send-followup`, { response_text: followUpText });
      if (result.closed_actions?.length) {
        toast.success(`Follow-up sent. Completed: ${result.closed_actions.map(a => a.description.slice(0, 40)).join(", ")}`);
      } else {
        toast.success("Follow-up sent");
      }
      if (result.ask_actions?.length) {
        for (const a of result.ask_actions) {
          toast(`Does this close "${a.description.slice(0, 50)}"? ${a.reason}`, { duration: 10000 });
        }
      }
      setFollowUp(null);
      setFollowUpText("");
      setReviseInstruction("");
      onAction();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const handleRevise = async () => {
    if (!reviseInstruction.trim() || !followUpText) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-messages/${messageId}/revise-draft`, {
        draft: followUpText,
        instruction: reviseInstruction,
      });
      setFollowUpText(result.draft);
      setReviseInstruction("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setRevising(false);
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
            <div className="space-y-2">
              <Textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={5}
                className="text-sm"
              />
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Input
                    value={draftReviseInstruction}
                    onChange={(e) => setDraftReviseInstruction(e.target.value)}
                    placeholder="Tell AI how to change it..."
                    className="text-sm h-8"
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleReviseDraft(); } }}
                  />
                </div>
                <Button variant="outline" size="sm" className="h-8" onClick={handleReviseDraft} disabled={draftRevising || !draftReviseInstruction.trim()}>
                  {draftRevising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
                </Button>
              </div>
            </div>
          ) : (
            <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-md p-3 text-sm whitespace-pre-wrap">
              {msg.draft_response}
            </div>
          )}
          {msg.status === "pending" && !editing && (
            <div className="flex gap-2 items-end mt-2">
              <div className="flex-1">
                <Input
                  value={draftReviseInstruction}
                  onChange={(e) => setDraftReviseInstruction(e.target.value)}
                  placeholder="Tell AI how to change it..."
                  className="text-sm h-8"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      if (!editing) { setEditing(true); setEditText(msg.draft_response || ""); }
                      handleReviseDraft();
                    }
                  }}
                />
              </div>
              <Button variant="outline" size="sm" className="h-8" onClick={() => {
                if (!editing) { setEditing(true); setEditText(msg.draft_response || ""); }
                handleReviseDraft();
              }} disabled={draftRevising || !draftReviseInstruction.trim()}>
                {draftRevising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
              </Button>
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

      {/* Jobs */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-1">
            <ClipboardList className="h-3 w-3" />Jobs
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
                  {teamMembers.map((name) => (
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
          <p className="text-xs text-muted-foreground py-2">No jobs</p>
        ) : null}
      </div>

      {/* Approve/Send button */}
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
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                value={reviseInstruction}
                onChange={(e) => setReviseInstruction(e.target.value)}
                placeholder="Tell AI how to change it..."
                className="text-sm h-8"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleRevise(); } }}
              />
            </div>
            <Button variant="outline" size="sm" className="h-8" onClick={handleRevise} disabled={revising || !reviseInstruction.trim()}>
              {revising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
            </Button>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}>
              {sendingFollowUp ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              Send Follow-up
            </Button>
            <Button variant="ghost" onClick={() => { setFollowUp(null); setFollowUpText(""); setReviseInstruction(""); }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Dismiss + Delete — bottom, behind confirmations */}
      <div className="pt-2 border-t flex justify-between">
        {msg.status === "pending" && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground" disabled={sending}>
                Dismiss
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Dismiss this message?</AlertDialogTitle>
                <AlertDialogDescription>
                  No reply will be sent. Action items will remain open.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleDismiss}>Dismiss</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-destructive" disabled={sending}>
              <Trash2 className="h-3 w-3 mr-1" />Delete
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete this message?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently remove the message and all associated jobs. This cannot be undone.
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

interface RelatedJob {
  id: string;
  action_type: string;
  description: string;
  status: string;
  comments: { author: string; text: string }[];
}

interface ActionDetail extends AgentAction {
  comments?: ActionComment[];
  notes?: string | null;
  from_email?: string;
  customer_name?: string;
  subject?: string;
  email_body?: string;
  our_response?: string;
  related_jobs?: RelatedJob[];
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
  const teamMembers = useTeamMembers();
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
  const [invoiceDraft, setInvoiceDraft] = useState<{ customer_id: string | null; customer_name: string; subject: string; line_items: { description: string; quantity: number; unit_price: number }[]; notes: string } | null>(null);
  const [draftingInvoice, setDraftingInvoice] = useState(false);
  const [creatingInvoice, setCreatingInvoice] = useState(false);

  const handleDraftInvoice = async () => {
    setDraftingInvoice(true);
    try {
      const result = await api.post<{ customer_id: string | null; customer_name: string; subject: string; line_items: { description: string; quantity: number; unit_price: number }[]; notes: string }>(`/v1/admin/agent-actions/${actionId}/draft-invoice`, {});
      setInvoiceDraft(result);
    } catch {
      toast.error("Failed to draft invoice");
    } finally {
      setDraftingInvoice(false);
    }
  };

  const handleCreateInvoice = async () => {
    if (!invoiceDraft || !invoiceDraft.customer_id) {
      toast.error("No customer matched — can't create invoice");
      return;
    }
    setCreatingInvoice(true);
    try {
      const today = new Date().toISOString().split("T")[0];
      const due = new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0];
      await api.post("/v1/invoices", {
        customer_id: invoiceDraft.customer_id,
        subject: invoiceDraft.subject,
        issue_date: today,
        due_date: due,
        notes: invoiceDraft.notes,
        line_items: invoiceDraft.line_items.map((li, i) => ({
          description: li.description,
          quantity: li.quantity,
          unit_price: li.unit_price,
          is_taxed: false,
          sort_order: i,
        })),
      });
      toast.success("Invoice created");
      setInvoiceDraft(null);
      onUpdate();
    } catch (err: unknown) {
      toast.error((err as { message?: string })?.message || "Failed to create invoice");
    } finally {
      setCreatingInvoice(false);
    }
  };

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
      const result = await api.post<{ sent: boolean; closed_actions: { description: string }[]; ask_actions: { id: string; description: string; reason: string }[] }>(`/v1/admin/agent-messages/${detail.agent_message_id}/send-followup`, { response_text: followUpText });
      if (result.closed_actions?.length) {
        toast.success(`Follow-up sent. Completed: ${result.closed_actions.map(a => a.description.slice(0, 40)).join(", ")}`);
      } else {
        toast.success("Follow-up sent");
      }
      if (result.ask_actions?.length) {
        for (const a of result.ask_actions) {
          toast(`Does this close "${a.description.slice(0, 50)}"? ${a.reason}`, { duration: 10000 });
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
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-messages/${detail.agent_message_id}/revise-draft`, {
        draft: followUpText,
        instruction: reviseInstruction,
      });
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
      const result = await api.post<{ action_resolved?: boolean; action_updated?: boolean; new_description?: string }>(`/v1/admin/agent-actions/${actionId}/comments`, { text: comment });
      setComment("");
      if (result.action_resolved) {
        toast.success("Job marked complete — your comment resolved it");
      } else if (result.action_updated && result.new_description) {
        toast.success(`Job updated: ${result.new_description.slice(0, 60)}`);
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

      {/* Context trail */}
      {(detail.subject || detail.related_jobs) && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Context</p>

          {detail.subject && (
            <div className="bg-muted/50 rounded-md p-3 text-sm space-y-1">
              <p className="text-xs text-muted-foreground">Email: {detail.from_email}</p>
              <p className="font-medium">{detail.subject}</p>
              {detail.email_body && (
                <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-4">{detail.email_body}</p>
              )}
            </div>
          )}

          {detail.our_response && (
            <div className="bg-green-50 dark:bg-green-950/20 rounded-md p-3 text-sm">
              <p className="text-xs text-muted-foreground mb-1">Our reply</p>
              <p className="text-xs whitespace-pre-wrap line-clamp-3">{detail.our_response}</p>
            </div>
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
        <div className="flex gap-2 items-end">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment..."
            className="text-sm min-h-[2.5rem] resize-none flex-1"
            rows={2}
          />
          <Button size="sm" className="h-9 flex-shrink-0" onClick={handleAddComment} disabled={posting || !comment.trim()}>
            {posting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Post"}
          </Button>
        </div>
      </div>

      {/* Actions row */}
      {!followUp && !invoiceDraft && (
        <div className="pt-2 border-t flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftFollowUp}
            disabled={draftingFollowUp}
          >
            {draftingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
            Draft Follow-up
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftInvoice}
            disabled={draftingInvoice}
          >
            {draftingInvoice ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <DollarSign className="h-3.5 w-3.5 mr-1.5" />}
            Create Invoice
          </Button>
        </div>
      )}

      {/* Invoice draft */}
      {invoiceDraft && (
        <div className="pt-2 border-t space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Invoice Draft</p>
          <div className="space-y-2">
            <div className="text-sm">
              <span className="text-muted-foreground">Customer: </span>
              <span className="font-medium">{invoiceDraft.customer_name}</span>
              {!invoiceDraft.customer_id && <span className="text-red-600 text-xs ml-2">(no match)</span>}
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Subject</Label>
              <Input
                value={invoiceDraft.subject}
                onChange={(e) => setInvoiceDraft({ ...invoiceDraft, subject: e.target.value })}
                className="h-8 text-sm"
              />
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Line Items</p>
            {invoiceDraft.line_items.map((li, i) => (
              <div key={i} className="flex gap-2 items-start bg-muted/50 rounded-md p-2">
                <div className="flex-1 space-y-1">
                  <Input
                    value={li.description}
                    onChange={(e) => {
                      const items = [...invoiceDraft.line_items];
                      items[i] = { ...items[i], description: e.target.value };
                      setInvoiceDraft({ ...invoiceDraft, line_items: items });
                    }}
                    className="h-7 text-sm"
                    placeholder="Description"
                  />
                  <div className="flex gap-2">
                    <Input
                      type="number"
                      value={li.quantity}
                      onChange={(e) => {
                        const items = [...invoiceDraft.line_items];
                        items[i] = { ...items[i], quantity: parseFloat(e.target.value) || 0 };
                        setInvoiceDraft({ ...invoiceDraft, line_items: items });
                      }}
                      className="h-7 text-sm w-16"
                      placeholder="Qty"
                    />
                    <Input
                      type="number"
                      value={li.unit_price}
                      onChange={(e) => {
                        const items = [...invoiceDraft.line_items];
                        items[i] = { ...items[i], unit_price: parseFloat(e.target.value) || 0 };
                        setInvoiceDraft({ ...invoiceDraft, line_items: items });
                      }}
                      className="h-7 text-sm w-24"
                      placeholder="Price"
                      step="0.01"
                    />
                    <span className="text-sm text-muted-foreground self-center w-20 text-right">
                      ${(li.quantity * li.unit_price).toFixed(2)}
                    </span>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive mt-1"
                  onClick={() => {
                    const items = invoiceDraft.line_items.filter((_, j) => j !== i);
                    setInvoiceDraft({ ...invoiceDraft, line_items: items });
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={() => setInvoiceDraft({
                ...invoiceDraft,
                line_items: [...invoiceDraft.line_items, { description: "", quantity: 1, unit_price: 0 }],
              })}
            >
              <Plus className="h-3 w-3 mr-1" />Add Line
            </Button>
          </div>

          <div className="flex items-center justify-between text-sm font-medium pt-1 border-t">
            <span>Total</span>
            <span>${invoiceDraft.line_items.reduce((sum, li) => sum + li.quantity * li.unit_price, 0).toFixed(2)}</span>
          </div>

          <div className="flex gap-2">
            <Button onClick={handleCreateInvoice} disabled={creatingInvoice || !invoiceDraft.customer_id}>
              {creatingInvoice ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <DollarSign className="h-4 w-4 mr-2" />}
              Create Invoice
            </Button>
            <Button variant="ghost" onClick={() => setInvoiceDraft(null)}>Cancel</Button>
          </div>
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
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                value={reviseInstruction}
                onChange={(e) => setReviseInstruction(e.target.value)}
                placeholder="Tell AI how to change it..."
                className="text-sm h-8"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleRevise(); } }}
              />
            </div>
            <Button variant="outline" size="sm" className="h-8" onClick={handleRevise} disabled={revising || !reviseInstruction.trim()}>
              {revising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
            </Button>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}>
              {sendingFollowUp ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              Send
            </Button>
            <Button variant="ghost" onClick={() => { setFollowUp(null); setFollowUpText(""); setReviseInstruction(""); }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Delete action */}
      {detail.status !== "cancelled" && (
        <div className="pt-3 border-t flex justify-end">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-destructive">
                <Trash2 className="h-3 w-3 mr-1" />Delete Job
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this job?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove the action and all its comments. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={async () => {
                  try {
                    await api.put(`/v1/admin/agent-actions/${actionId}`, { status: "cancelled" });
                    toast.success("Action deleted");
                    onClose();
                    onUpdate();
                  } catch { toast.error("Failed"); }
                }}>Delete</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
}

function ClientPropertySearch({
  customerName,
  propertyAddress,
  onChange,
}: {
  customerName: string;
  propertyAddress: string;
  onChange: (name: string, address: string) => void;
}) {
  const [query, setQuery] = useState(customerName);
  const [results, setResults] = useState<{ customer_name: string; property_address: string; property_name: string | null }[]>([]);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    if (query.length < 2) { setResults([]); return; }
    const timer = setTimeout(async () => {
      try {
        const data = await api.get<{ customer_name: string; property_address: string; property_name: string | null }[]>(`/v1/admin/client-search?q=${encodeURIComponent(query)}`);
        setResults(data);
        setShowResults(true);
      } catch { setResults([]); }
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div className="space-y-2">
      <div className="relative">
        <Input
          value={query}
          onChange={(e) => { setQuery(e.target.value); onChange(e.target.value, propertyAddress); }}
          placeholder="Search client or address..."
          className="text-sm h-8"
          onFocus={() => results.length > 0 && setShowResults(true)}
        />
        {showResults && results.length > 0 && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setShowResults(false)} />
            <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-md border bg-background shadow-lg">
              {results.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  className="w-full px-3 py-2 text-left hover:bg-muted/50 text-sm"
                  onClick={() => {
                    setQuery(r.customer_name);
                    onChange(r.customer_name, r.property_address);
                    setShowResults(false);
                  }}
                >
                  <span className="font-medium">{r.customer_name}</span>
                  {r.property_name && <span className="text-muted-foreground ml-1">({r.property_name})</span>}
                  <span className="text-xs text-muted-foreground block">{r.property_address}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      {propertyAddress && (
        <p className="text-xs text-muted-foreground px-1">{propertyAddress}</p>
      )}
    </div>
  );
}

export default function AgentPage() {
  const { user } = useAuth();
  const myName = user?.first_name || "";
  const teamMembers = useTeamMembers();
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
  const [newActionOpen, setNewActionOpen] = useState(false);
  const [newAction, setNewAction] = useState({ action_type: "follow_up", description: "", assigned_to: "", due_days: "3", customer_name: "", property_address: "" });
  const [jobFilter, setJobFilter] = useState<string>("mine");
  const [showCompleted, setShowCompleted] = useState(false);

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
      if (statusFilter === "clients") {
        params.set("exclude_categories", "spam,auto_reply,no_response");
      } else if (statusFilter !== "all") {
        params.set("status", statusFilter);
      }
      if (searchQuery) params.set("search", searchQuery);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(page * PAGE_SIZE));
      const qs = params.toString();
      const [paginated, st, acts] = await Promise.all([
        api.get<PaginatedMessages>(`/v1/admin/agent-messages?${qs}`),
        api.get<AgentStats>("/v1/admin/agent-stats"),
        (async () => {
              const assigneeParam = jobFilter === "mine" && myName ? `&assigned_to=${encodeURIComponent(myName)}` : jobFilter !== "mine" && jobFilter !== "all" ? `&assigned_to=${encodeURIComponent(jobFilter)}` : "";
              const statuses = showCompleted ? ["open", "in_progress", "done"] : ["open", "in_progress"];
              const results = await Promise.all(
                statuses.map(s => api.get<AgentAction[]>(`/v1/admin/agent-actions?status=${s}${assigneeParam}`).catch(() => []))
              );
              return results.flat();
            })(),
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
  }, [statusFilter, searchQuery, page, jobFilter, showCompleted, myName]);

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
        <div className="grid grid-cols-2 gap-4">
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
            className={`shadow-sm py-4 gap-2 cursor-pointer transition-shadow hover:shadow-md ${stats.overdue_actions > 0 ? "border-l-4 border-red-500" : ""} ${activeTab === "actions" ? "ring-2 ring-primary" : ""}`}
            onClick={() => setActiveTab("actions")}
          >
            <CardHeader className="pb-0">
              <div className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-purple-500" />
                <CardTitle className="text-sm font-medium">Open Jobs</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.open_actions}</p>
              {stats.overdue_actions > 0 && (
                <p className="text-xs text-red-600 font-medium">{stats.overdue_actions} overdue</p>
              )}
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
          Jobs
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
                  {s === "auto_sent" ? "Auto" : s === "clients" ? "Clients" : s}
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
        // Group actions by parent message (event) or standalone
        const grouped = new Map<string, { label: string; from: string; actions: AgentAction[] }>();
        for (const a of actions) {
          const key = a.agent_message_id || `standalone-${a.id}`;
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
          <>
          {/* Job filters + New Job */}
          <div className="flex flex-col sm:flex-row gap-3 justify-between">
            <div className="flex gap-1 flex-wrap items-center">
              {["mine", "all", ...teamMembers].map((f) => (
                <Button
                  key={f}
                  variant={jobFilter === f ? "default" : "outline"}
                  size="sm"
                  className="text-xs capitalize h-7"
                  onClick={() => setJobFilter(f)}
                >
                  {f === "mine" ? "My Jobs" : f === "all" ? "All" : f}
                </Button>
              ))}
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground ml-2 cursor-pointer">
                <input type="checkbox" checked={showCompleted} onChange={(e) => setShowCompleted(e.target.checked)} className="rounded" />
                Done
              </label>
            </div>
            <Button variant="outline" size="sm" className="h-7" onClick={() => setNewActionOpen(!newActionOpen)}>
              <Plus className="h-3.5 w-3.5 mr-1.5" />{newActionOpen ? "Cancel" : "New Job"}
            </Button>
          </div>
          {newActionOpen && (
            <Card className="shadow-sm">
              <CardContent className="py-3 px-4 space-y-3">
                <Input
                  value={newAction.description}
                  onChange={(e) => setNewAction({ ...newAction, description: e.target.value })}
                  placeholder="What needs to be done?"
                  className="text-sm"
                  autoFocus
                />
                <div className="flex flex-wrap gap-2">
                  <div className="flex gap-1 flex-wrap">
                    {ACTION_TYPES.map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setNewAction({ ...newAction, action_type: t })}
                        className={`px-2 py-1 text-[10px] rounded-md border transition-colors capitalize ${
                          newAction.action_type === t
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-background text-muted-foreground border-input hover:bg-accent"
                        }`}
                      >
                        {t.replace("_", " ")}
                      </button>
                    ))}
                  </div>
                </div>
                <ClientPropertySearch
                  customerName={newAction.customer_name}
                  propertyAddress={newAction.property_address}
                  onChange={(name, addr) => setNewAction({ ...newAction, customer_name: name, property_address: addr })}
                />
                <div className="grid grid-cols-3 gap-2">
                  <Select value={newAction.assigned_to || ""} onValueChange={(v) => setNewAction({ ...newAction, assigned_to: v })}>
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue placeholder="Assign..." />
                    </SelectTrigger>
                    <SelectContent>
                      {teamMembers.map((name) => (
                        <SelectItem key={name} value={name} className="text-sm">{name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    value={newAction.due_days}
                    onChange={(e) => setNewAction({ ...newAction, due_days: e.target.value })}
                    className="h-8 text-sm"
                    placeholder="Due in days"
                  />
                  <Button
                    size="sm"
                    className="h-8"
                    disabled={!newAction.description.trim()}
                    onClick={async () => {
                      const dueDate = newAction.due_days
                        ? new Date(Date.now() + parseInt(newAction.due_days) * 86400000).toISOString()
                        : undefined;
                      try {
                        await api.post("/v1/admin/agent-actions", {
                          action_type: newAction.action_type,
                          description: newAction.description,
                          assigned_to: newAction.assigned_to || undefined,
                          due_date: dueDate,
                          customer_name: newAction.customer_name || undefined,
                          property_address: newAction.property_address || undefined,
                        });
                        setNewAction({ action_type: "follow_up", description: "", assigned_to: "", due_days: "3", customer_name: "", property_address: "" });
                        setNewActionOpen(false);
                        load();
                        toast.success("Job created");
                      } catch { toast.error("Failed to create action"); }
                    }}
                  >
                    Create
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="shadow-sm">
            <CardContent className="p-0">
              {actions.length === 0 && !newActionOpen ? (
                <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                  <CheckCircle2 className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm">All caught up — no open jobs</p>
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
                                        {teamMembers.map((name) => (
                                          <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                                  {(a.status === "open" || a.status === "in_progress") && (
                                    <Button
                                      variant="default"
                                      size="sm"
                                      className="h-6 text-[10px] px-2 bg-green-600 hover:bg-green-700"
                                      onClick={() => handleToggleAction(a.id, a.status)}
                                    >
                                      Done
                                    </Button>
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
          </>
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
