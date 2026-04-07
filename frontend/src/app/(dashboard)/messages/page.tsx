"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useWSRefetch } from "@/lib/ws";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter } from "@/components/ui/overlay";
import { toast } from "sonner";
import {
  MessageSquare,
  Plus,
  Send,
  Loader2,
  ArrowRightToLine,
  FolderOpen,
} from "lucide-react";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import { ComposeMessage } from "@/components/messages/compose-message";
import { PageLayout } from "@/components/layout/page-layout";
import { AttachmentPicker, type UploadedAttachment } from "@/components/ui/attachment-picker";
import { AttachmentDisplay, type AttachmentInfo } from "@/components/ui/attachment-display";

interface ThreadSummary {
  id: string;
  participants: string[];
  subject: string | null;
  customer_name: string | null;
  priority: string;
  is_unread: boolean;
  message_count: number;
  last_message: string | null;
  last_message_by: string | null;
  last_message_at: string | null;
  converted_to_action_id: string | null;
  case_id: string | null;
}

interface ThreadMessage {
  id: string;
  from_user_id: string;
  from_name: string;
  text: string;
  attachments?: AttachmentInfo[];
  created_at: string;
}

interface ThreadDetail {
  id: string;
  participants: string[];
  subject: string | null;
  customer_name: string | null;
  action_id: string | null;
  priority: string;
  messages: ThreadMessage[];
  converted_to_action_id: string | null;
  case_id: string | null;
}

export default function MessagesPage() {
  const router = useRouter();
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
  const [replyAttachments, setReplyAttachments] = useState<UploadedAttachment[]>([]);
  const [sending, setSending] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const replyRef = useRef<HTMLTextAreaElement>(null);

  const loadThreads = useCallback(() => {
    setLoading(true);
    api.get<{ items: ThreadSummary[] }>(`/v1/messages?view=${view}`)
      .then((d) => setThreads(d.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [view]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  // Real-time: refresh when new internal messages arrive
  useWSRefetch(["message.new", "message.read"], loadThreads, 500);

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
      await api.post(`/v1/messages/${selectedThreadId}/reply`, {
        message: reply.trim(),
        attachment_ids: replyAttachments.length ? replyAttachments.map((a) => a.id) : undefined,
      });
      setReply("");
      setReplyAttachments([]);
      loadDetail(selectedThreadId);
      loadThreads();
    } catch { toast.error("Failed to send"); }
    finally { setSending(false); }
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
    <PageLayout
      title="Messages"
      icon={<MessageSquare className="h-5 w-5 text-muted-foreground" />}
      action={
        <Button size="sm" onClick={() => setComposeOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Compose
        </Button>
      }
    >
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-12rem)]">
      {/* Thread list — hidden on mobile when viewing a thread */}
      <div className={`lg:w-80 xl:w-96 shrink-0 border rounded-lg bg-background overflow-y-auto ${selectedThreadId ? "hidden lg:block" : ""}`}>
        <div className="p-3 border-b space-y-2">
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
              <button
                type="button"
                key={t.id}
                className={`w-full text-left px-3 py-2.5 cursor-pointer hover:bg-muted/50 transition-colors touch-manipulation ${selectedThreadId === t.id ? "bg-muted/50" : ""} ${t.is_unread ? "bg-blue-50/50 dark:bg-blue-950/20" : ""}`}
                onClick={() => setSelectedThreadId(t.id)}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {t.is_unread && <span className="h-2 w-2 rounded-full bg-blue-500 shrink-0" />}
                    <span className={`text-sm truncate ${t.is_unread ? "font-semibold" : "font-medium"}`}>{t.subject || t.participants.join(", ") || "Message"}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground shrink-0 ml-2">{formatTime(t.last_message_at)}</span>
                </div>
                {t.subject && <p className="text-xs text-muted-foreground truncate">{t.participants.join(", ")}</p>}
                <p className="text-xs text-muted-foreground truncate mt-0.5">{t.last_message || ""}</p>
                <div className="flex items-center gap-1.5 mt-1">
                  {t.priority === "urgent" && <Badge variant="outline" className="text-[9px] px-1 border-amber-400 text-amber-600">Urgent</Badge>}
                  {t.customer_name && <Badge variant="secondary" className="text-[9px] px-1">{t.customer_name}</Badge>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Thread detail — full screen on mobile when selected */}
      <div className={`flex-1 border rounded-lg bg-background flex flex-col overflow-hidden ${!selectedThreadId ? "hidden lg:flex" : ""}`}>
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
                <div className="flex items-center gap-2 min-w-0">
                  <Button variant="ghost" size="icon" className="h-8 w-8 lg:hidden shrink-0" onClick={() => setSelectedThreadId(null)}>
                    <ArrowRightToLine className="h-4 w-4 rotate-180" />
                  </Button>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{detail.subject || detail.participants.join(", ")}</p>
                    {detail.subject && <p className="text-xs text-muted-foreground truncate">{detail.participants.join(", ")}</p>}
                    {detail.customer_name && <p className="text-xs text-muted-foreground">Client: {detail.customer_name}</p>}
                  </div>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  {detail.case_id ? (
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => router.push(`/cases/${detail.case_id}`)}>
                      <FolderOpen className="h-3 w-3 mr-1" /> View Case
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={async () => {
                      try {
                        const result = await api.post<{ case_id: string; case_number?: string }>(`/v1/messages/${selectedThreadId}/create-case`, {});
                        toast.success(`Case created: ${result.case_number || ""}`);
                        router.push(`/cases/${result.case_id}`);
                      } catch { toast.error("Failed to create case"); }
                    }}>
                      <FolderOpen className="h-3 w-3 mr-1" /> Create Case
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
                      {m.attachments && m.attachments.length > 0 && (
                        <AttachmentDisplay attachments={m.attachments} />
                      )}
                      <p className={`text-[10px] mt-1 ${isMe ? "text-primary-foreground/60" : "text-muted-foreground"}`}>{formatTime(m.created_at)}</p>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Reply */}
            {(
              <div className="p-3 border-t shrink-0 space-y-2">
                <AttachmentPicker
                  attachments={replyAttachments}
                  onAttachmentsChange={setReplyAttachments}
                  sourceType="internal_message"
                />
                <div className="flex gap-2 items-end">
                  <Textarea
                    ref={replyRef}
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReply(); } }}
                    placeholder="Type a message..."
                    className="text-sm min-h-[2.25rem] max-h-32 resize-none"
                    rows={1}
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
    </PageLayout>
  );
}
