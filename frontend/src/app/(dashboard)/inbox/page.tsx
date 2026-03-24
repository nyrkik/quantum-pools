"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
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
  Clock,
  Search,
  Send,
  Pencil,
  Bot,
  AlertTriangle,
  Trash2,
  Mail,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

// --- Types ---

interface Thread {
  id: string;
  contact_email: string;
  subject: string | null;
  customer_name: string | null;
  matched_customer_id: string | null;
  status: string;
  urgency: string | null;
  category: string | null;
  message_count: number;
  last_message_at: string | null;
  last_direction: string;
  last_snippet: string | null;
  has_pending: boolean;
  has_open_actions: boolean;
}

interface TimelineMessage {
  id: string;
  direction: string;
  from_email: string;
  to_email: string;
  subject: string | null;
  body: string | null;
  category: string | null;
  urgency: string | null;
  status: string;
  draft_response: string | null;
  received_at: string | null;
  sent_at: string | null;
  approved_by: string | null;
}

interface ThreadDetail {
  id: string;
  contact_email: string;
  subject: string | null;
  customer_name: string | null;
  status: string;
  urgency: string | null;
  category: string | null;
  message_count: number;
  has_pending: boolean;
  timeline: TimelineMessage[];
  actions: unknown[];
}

interface ThreadStats {
  total: number;
  pending: number;
  stale_pending: number;
  open_actions: number;
}

interface PaginatedThreads {
  items: Thread[];
  total: number;
}

const PAGE_SIZE = 25;

const STATUS_FILTERS = ["clients", "all", "handled"] as const;

// --- Helpers ---

function formatTime(iso: string | null) {
  if (!iso) return "\u2014";
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
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function isStale(receivedAt: string | null) {
  if (!receivedAt) return false;
  return (Date.now() - new Date(receivedAt).getTime()) > 30 * 60 * 1000;
}

// --- Badge components ---

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Badge variant="outline" className="border-amber-400 text-amber-600">Pending</Badge>;
    case "handled":
      return <Badge variant="default" className="bg-green-600">Handled</Badge>;
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

// --- Thread Detail Sheet ---

function ThreadDetailSheet({
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
                <div className="whitespace-pre-wrap text-sm leading-relaxed">
                  {msg.body || "No content"}
                </div>
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
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-destructive" disabled={sending}>
                <Trash2 className="h-3 w-3 mr-1" />Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this thread?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove the thread and all messages. This cannot be undone.
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
    </div>
  );
}

// --- Main Page ---

export default function InboxPage() {
  const { user } = useAuth();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<ThreadStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<typeof STATUS_FILTERS[number]>("clients");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(0);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);

  const loadThreads = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (filter === "clients") {
      params.set("exclude_spam", "true");
      params.set("exclude_ignored", "true");
    } else if (filter === "handled") {
      params.set("status", "handled");
    } else if (filter === "all") {
      params.set("exclude_spam", "false");
    }
    if (search) params.set("search", search);

    api.get<PaginatedThreads>(`/v1/admin/agent-threads?${params}`)
      .then((data) => {
        setThreads(data.items);
        setTotal(data.total);
      })
      .catch(() => toast.error("Failed to load threads"))
      .finally(() => setLoading(false));
  }, [filter, search, page]);

  const loadStats = useCallback(() => {
    api.get<ThreadStats>("/v1/admin/agent-threads/stats")
      .then(setStats)
      .catch(() => {});
  }, []);

  useEffect(() => { loadThreads(); }, [loadThreads]);
  useEffect(() => { loadStats(); }, [loadStats]);

  const handleFilterChange = (f: typeof STATUS_FILTERS[number]) => {
    setFilter(f);
    setPage(0);
  };

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(0);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Pending threads for "Needs Attention"
  const pendingThreads = filter === "clients" ? threads.filter((t) => t.has_pending) : [];

  if (!user) return null;

  return (
    <div className="p-4 sm:p-6 pt-16 sm:pt-6 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Bot className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-xl font-semibold">Inbox</h1>
      </div>

      {/* Stats tile */}
      {stats && (
        <button
          type="button"
          onClick={() => handleFilterChange("clients")}
          className={`w-full text-left rounded-lg border p-3 shadow-sm transition-colors ${
            stats.pending > 0
              ? "border-amber-300 bg-amber-50 dark:bg-amber-950/30 hover:bg-amber-100 dark:hover:bg-amber-950/50"
              : "bg-background hover:bg-muted/50"
          }`}
        >
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">{stats.total}</span>
              <span className="text-muted-foreground">threads</span>
            </div>
            {stats.pending > 0 && (
              <div className="flex items-center gap-1.5">
                <Clock className="h-4 w-4 text-amber-600" />
                <span className="font-medium text-amber-600">{stats.pending} pending</span>
                {stats.stale_pending > 0 && (
                  <span className="text-xs text-red-600">({stats.stale_pending} stale)</span>
                )}
              </div>
            )}
            {stats.open_actions > 0 && (
              <div className="flex items-center gap-1.5">
                <MessageSquare className="h-4 w-4 text-blue-600" />
                <span className="text-blue-600">{stats.open_actions} open jobs</span>
              </div>
            )}
          </div>
        </button>
      )}

      {/* Needs Attention */}
      {filter === "clients" && pendingThreads.length > 0 && (
        <Card className="shadow-sm border-amber-200 dark:border-amber-800">
          <CardHeader className="py-2 px-4">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
              Needs Attention
              <Badge variant="outline" className="border-amber-400 text-amber-600 ml-1 text-[10px] px-1.5">
                {pendingThreads.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 pt-0">
            <div className="space-y-1">
              {pendingThreads.slice(0, 5).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedThreadId(t.id)}
                  className="w-full text-left flex items-center gap-3 py-1.5 px-2 rounded hover:bg-amber-50 dark:hover:bg-amber-950/30 text-sm transition-colors"
                >
                  <span className="font-medium truncate flex-shrink-0 w-32">
                    {t.customer_name || t.contact_email.split("@")[0]}
                  </span>
                  <span className="text-muted-foreground truncate flex-1">
                    {t.last_snippet || t.subject || "No subject"}
                  </span>
                  <span className="text-xs text-muted-foreground flex-shrink-0">
                    {formatTime(t.last_message_at)}
                  </span>
                </button>
              ))}
              {pendingThreads.length > 5 && (
                <p className="text-xs text-muted-foreground pl-2">+ {pendingThreads.length - 5} more</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters + Search */}
      <div className="flex items-center gap-2 flex-wrap">
        {STATUS_FILTERS.map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            className="capitalize"
            onClick={() => handleFilterChange(f)}
          >
            {f}
          </Button>
        ))}
        <div className="flex items-center gap-1 ml-auto">
          <Input
            placeholder="Search..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
            className="h-8 w-48 text-sm"
          />
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleSearch}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Thread table */}
      <Card className="shadow-sm">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide w-24">Time</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">From</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Subject</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-16 text-center">Msgs</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-28">Category</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-24">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-12">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : threads.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-12 text-muted-foreground">
                  No threads found
                </TableCell>
              </TableRow>
            ) : (
              threads.map((t, i) => (
                <TableRow
                  key={t.id}
                  className={`cursor-pointer transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 ${
                    i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""
                  } ${t.has_pending ? "border-l-4 border-l-amber-400 font-medium" : ""}`}
                  onClick={() => setSelectedThreadId(t.id)}
                >
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {formatTime(t.last_message_at)}
                  </TableCell>
                  <TableCell className="truncate max-w-[180px]">
                    <span className={t.has_pending ? "font-medium" : ""}>
                      {t.customer_name || t.contact_email.split("@")[0]}
                    </span>
                  </TableCell>
                  <TableCell className="truncate max-w-[250px] text-sm">
                    <span className={t.has_pending ? "" : "text-muted-foreground"}>
                      {t.subject || t.last_snippet || "No subject"}
                    </span>
                  </TableCell>
                  <TableCell className="text-center">
                    {t.message_count > 1 && (
                      <Badge variant="secondary" className="text-[10px] px-1.5">
                        {t.message_count}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <CategoryBadge category={t.category} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <StatusBadge status={t.status} />
                      <UrgencyBadge urgency={t.urgency} />
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {page * PAGE_SIZE + 1}\u2013{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="px-2">{page + 1} / {totalPages}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Thread detail sheet */}
      <Sheet open={!!selectedThreadId} onOpenChange={(open) => { if (!open) setSelectedThreadId(null); }}>
        <SheetContent className="w-full sm:max-w-lg flex flex-col h-full">
          <SheetHeader className="flex-shrink-0">
            <SheetTitle className="text-base">Conversation</SheetTitle>
          </SheetHeader>
          {selectedThreadId && (
            <div className="flex-1 overflow-hidden">
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={() => setSelectedThreadId(null)}
                onAction={() => { loadThreads(); loadStats(); }}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
