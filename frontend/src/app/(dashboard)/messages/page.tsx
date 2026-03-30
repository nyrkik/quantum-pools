"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter } from "@/components/ui/overlay";
import { toast } from "sonner";
import {
  MessageSquare,
  Plus,
  Check,
  CheckCheck,
  Send,
  Loader2,
  ArrowRightToLine,
} from "lucide-react";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import { ComposeMessage } from "@/components/messages/compose-message";

interface ThreadSummary {
  id: string;
  participants: string[];
  subject: string | null;
  customer_name: string | null;
  priority: string;
  status: string;
  message_count: number;
  last_message: string | null;
  last_message_by: string | null;
  last_message_at: string | null;
  acknowledged_at: string | null;
  completed_at: string | null;
  converted_to_action_id: string | null;
}

interface ThreadMessage {
  id: string;
  from_user_id: string;
  from_name: string;
  text: string;
  created_at: string;
}

interface ThreadDetail {
  id: string;
  participants: string[];
  subject: string | null;
  customer_name: string | null;
  action_id: string | null;
  priority: string;
  status: string;
  messages: ThreadMessage[];
  converted_to_action_id: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  active: "",
  acknowledged: "text-blue-600",
  completed: "text-green-600",
};

export default function MessagesPage() {
  const { user } = useAuth();
  const perms = usePermissions();
  const searchParams = useSearchParams();
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(searchParams.get("thread"));
  const [view, setView] = useState<"mine" | "team">("mine");
  const isAdmin = perms.role === "admin" || perms.role === "owner";
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const replyRef = useRef<HTMLInputElement>(null);

  const loadThreads = useCallback(() => {
    setLoading(true);
    api.get<{ items: ThreadSummary[] }>(`/v1/messages?view=${view}`)
      .then((d) => setThreads(d.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [view]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  const loadDetail = useCallback((threadId: string) => {
    setDetailLoading(true);
    api.get<ThreadDetail>(`/v1/messages/${threadId}`)
      .then((d) => { setDetail(d); setTimeout(() => replyRef.current?.focus(), 100); })
      .catch(() => toast.error("Failed to load"))
      .finally(() => setDetailLoading(false));
  }, []);

  useEffect(() => {
    if (selectedThreadId) loadDetail(selectedThreadId);
    else setDetail(null);
  }, [selectedThreadId, loadDetail]);

  const handleReply = async () => {
    if (!reply.trim() || !selectedThreadId) return;
    setSending(true);
    try {
      await api.post(`/v1/messages/${selectedThreadId}/reply`, { message: reply.trim() });
      setReply("");
      loadDetail(selectedThreadId);
      loadThreads();
    } catch { toast.error("Failed to send"); }
    finally { setSending(false); }
  };

  const handleAction = async (action: string) => {
    if (!selectedThreadId) return;
    try {
      await api.put(`/v1/messages/${selectedThreadId}/${action}`);
      toast.success(action === "acknowledge" ? "Acknowledged" : "Completed");
      loadDetail(selectedThreadId);
      loadThreads();
    } catch { toast.error("Failed"); }
  };

  const handleConvert = async () => {
    if (!selectedThreadId) return;
    try {
      const result = await api.post<{ action_id: string }>(`/v1/messages/${selectedThreadId}/convert-to-job`);
      toast.success("Converted to job");
      loadDetail(selectedThreadId);
      loadThreads();
    } catch { toast.error("Failed"); }
  };

  const formatTime = (iso: string | null) => {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-8rem)]">
      {/* Thread list */}
      <div className="lg:w-80 xl:w-96 shrink-0 border rounded-lg bg-background overflow-y-auto">
        <div className="p-3 border-b space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Messages</h2>
            <Button size="sm" className="h-7 text-xs gap-1" onClick={() => setComposeOpen(true)}>
              <Plus className="h-3 w-3" /> New
            </Button>
          </div>
          {isAdmin && (
            <div className="flex gap-1 bg-muted p-0.5 rounded-md">
              <button
                onClick={() => setView("mine")}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${view === "mine" ? "bg-background shadow-sm font-medium" : "text-muted-foreground"}`}
              >
                Mine
              </button>
              <button
                onClick={() => setView("team")}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${view === "team" ? "bg-background shadow-sm font-medium" : "text-muted-foreground"}`}
              >
                Team
              </button>
            </div>
          )}
        </div>
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : threads.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">No messages yet</p>
        ) : (
          <div className="divide-y">
            {threads.map((t) => (
              <div
                key={t.id}
                className={`px-3 py-2.5 cursor-pointer hover:bg-muted/50 transition-colors ${selectedThreadId === t.id ? "bg-muted/50" : ""} ${t.status === "active" && t.last_message_by !== user?.id ? "bg-blue-50/50 dark:bg-blue-950/20" : ""}`}
                onClick={() => setSelectedThreadId(t.id)}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-sm font-medium truncate">{t.participants.join(", ") || "Message"}</span>
                  <span className="text-[10px] text-muted-foreground shrink-0 ml-2">{formatTime(t.last_message_at)}</span>
                </div>
                {t.subject && <p className="text-xs text-muted-foreground truncate">{t.subject}</p>}
                <p className="text-xs text-muted-foreground truncate mt-0.5">{t.last_message || ""}</p>
                <div className="flex items-center gap-1.5 mt-1">
                  {t.priority === "urgent" && <Badge variant="outline" className="text-[9px] px-1 border-amber-400 text-amber-600">Urgent</Badge>}
                  {t.customer_name && <Badge variant="secondary" className="text-[9px] px-1">{t.customer_name}</Badge>}
                  {t.status === "acknowledged" && <Check className="h-3 w-3 text-blue-500" />}
                  {t.status === "completed" && <CheckCheck className="h-3 w-3 text-green-500" />}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Thread detail */}
      <div className="flex-1 border rounded-lg bg-background flex flex-col overflow-hidden">
        {!selectedThreadId ? (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">Select a conversation</p>
            </div>
          </div>
        ) : detailLoading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : detail ? (
          <>
            {/* Header */}
            <div className="p-3 border-b shrink-0">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">{detail.participants.join(", ")}</p>
                  {detail.subject && <p className="text-xs text-muted-foreground">{detail.subject}</p>}
                  {detail.customer_name && <p className="text-xs text-muted-foreground">Client: {detail.customer_name}</p>}
                </div>
                <div className="flex gap-1.5">
                  {detail.status === "active" && (
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleAction("acknowledge")}>
                      <Check className="h-3 w-3 mr-1" /> Ack
                    </Button>
                  )}
                  {(detail.status === "active" || detail.status === "acknowledged") && (
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleAction("complete")}>
                      <CheckCheck className="h-3 w-3 mr-1" /> Done
                    </Button>
                  )}
                  {!detail.converted_to_action_id && (
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleConvert}>
                      <ArrowRightToLine className="h-3 w-3 mr-1" /> Job
                    </Button>
                  )}
                </div>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {detail.messages.map((m) => {
                const isMe = m.from_user_id === user?.id;
                return (
                  <div key={m.id} className={`flex ${isMe ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[80%] rounded-lg px-3 py-2 ${isMe ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                      {!isMe && <p className="text-[10px] font-medium mb-0.5 opacity-70">{m.from_name}</p>}
                      <p className="text-sm whitespace-pre-wrap">{m.text}</p>
                      <p className={`text-[10px] mt-1 ${isMe ? "text-primary-foreground/60" : "text-muted-foreground"}`}>{formatTime(m.created_at)}</p>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Reply */}
            {detail.status !== "completed" && (
              <div className="p-3 border-t shrink-0">
                <div className="flex gap-2">
                  <Input
                    ref={replyRef}
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReply(); } }}
                    placeholder="Type a message..."
                    className="text-sm"
                  />
                  <Button size="icon" className="h-9 w-9 shrink-0" onClick={handleReply} disabled={!reply.trim() || sending}>
                    {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>

      <ComposeMessage
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSent={() => { setComposeOpen(false); loadThreads(); }}
      />
    </div>
  );
}
