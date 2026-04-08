"use client";

import { useState, useRef, useEffect } from "react";
import { useDeepBlue, type DeepBlueMessage } from "./deepblue-provider";
import { Button } from "@/components/ui/button";
import { Sparkles, Send, Loader2, Trash2, ChevronDown, FolderOpen, History, Pin, Users, Share2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { ToolResultCard } from "./tool-cards";


function MessageBubble({ msg }: { msg: DeepBlueMessage }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] rounded-lg p-3 text-sm ${
        isUser
          ? "bg-primary text-primary-foreground"
          : "bg-muted/70"
      }`}>
        {msg.content && (
          <div className="whitespace-pre-wrap">{msg.content}</div>
        )}
        {/* Tool result cards */}
        {msg.toolResults?.map((tr, i) => (
          <ToolResultCard key={i} name={tr.name} result={tr.result} />
        ))}
        {/* Loading indicator for tool calls without results yet */}
        {msg.toolCalls && msg.toolCalls.length > (msg.toolResults?.length || 0) && (
          <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Looking up data...
          </div>
        )}
      </div>
    </div>
  );
}

interface ConversationListItem {
  id: string;
  title: string;
  user_id: string;
  visibility: string;
  pinned: boolean;
  message_count: number;
  shared_at: string | null;
  updated_at: string;
}

export function DeepBlueSheet() {
  const { user } = useAuth();
  const currentUserId = user?.id || "";
  const {
    isOpen, isLoading, messages, context, conversationId, closeDeepBlue, sendMessage, clearConversation, saveToCase, loadConversation,
  } = useDeepBlue();
  const [input, setInput] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [historyScope, setHistoryScope] = useState<"mine" | "shared">("mine");
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const loadHistory = async (scope: "mine" | "shared") => {
    setHistoryLoading(true);
    try {
      const data = await api.get<{ conversations: ConversationListItem[] }>(
        `/v1/deepblue/conversations?scope=${scope}&limit=50`
      );
      setConversations(data.conversations);
    } catch {
      toast.error("Failed to load history");
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (showHistory) loadHistory(historyScope);
  }, [showHistory, historyScope]);

  const handleTogglePin = async (id: string, pinned: boolean) => {
    try {
      await fetch(`/api/v1/deepblue/conversations/${id}/pin`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ pinned: !pinned }),
      });
      loadHistory(historyScope);
    } catch { toast.error("Failed"); }
  };

  const handleToggleShare = async (id: string, currentVisibility: string) => {
    try {
      await fetch(`/api/v1/deepblue/conversations/${id}/visibility`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ visibility: currentVisibility === "shared" ? "private" : "shared" }),
      });
      toast.success(currentVisibility === "shared" ? "Made private" : "Shared with team");
      loadHistory(historyScope);
    } catch { toast.error("Failed"); }
  };

  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    if (pendingDelete !== id) {
      setPendingDelete(id);
      setTimeout(() => setPendingDelete((p) => (p === id ? null : p)), 3000);
      toast("Tap delete again to confirm", { duration: 3000 });
      return;
    }
    setPendingDelete(null);
    try {
      const resp = await fetch(`/api/v1/deepblue/conversations/${id}`, {
        method: "DELETE", credentials: "include",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      toast.success("Deleted");
      loadHistory(historyScope);
    } catch { toast.error("Failed to delete"); }
  };

  const handleResume = async (id: string) => {
    if (loadConversation) {
      await loadConversation(id);
      setShowHistory(false);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    sendMessage(text);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[70] flex flex-col bg-background border-t shadow-2xl ring-1 ring-black/5 sm:right-4 sm:left-auto sm:bottom-4 sm:w-[420px] sm:rounded-xl sm:border sm:border-primary/15 sm:max-h-[600px] sm:shadow-[0_8px_40px_-8px_rgba(0,0,0,0.2)]"
      style={{ maxHeight: "75vh" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b bg-primary/5 shrink-0 sm:rounded-t-xl">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">DeepBlue</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowHistory(!showHistory)} title="History">
            <History className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
          {context.caseId && conversationId && messages.length >= 2 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-[10px] px-2 gap-1 text-muted-foreground"
              onClick={async () => {
                const ok = await saveToCase(context.caseId!);
                if (ok) {
                  toast.success("Saved to case");
                  clearConversation();
                } else {
                  toast.error("Failed to save");
                }
              }}
              title="Save conversation to case"
            >
              <FolderOpen className="h-3 w-3" />
              Save to case
            </Button>
          )}
          {messages.length > 0 && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={clearConversation} title="New conversation">
              <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={closeDeepBlue}>
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          </Button>
        </div>
      </div>

      {/* Messages or History */}
      {showHistory ? (
        <div className="flex-1 overflow-y-auto min-h-0">
          <div className="flex gap-1 p-2 border-b bg-muted/30 sticky top-0">
            <Button
              size="sm"
              variant={historyScope === "mine" ? "default" : "ghost"}
              className="h-7 text-xs flex-1"
              onClick={() => setHistoryScope("mine")}
            >
              My chats
            </Button>
            <Button
              size="sm"
              variant={historyScope === "shared" ? "default" : "ghost"}
              className="h-7 text-xs flex-1"
              onClick={() => setHistoryScope("shared")}
            >
              <Users className="h-3 w-3 mr-1" /> Shared
            </Button>
          </div>
          {historyLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-4 w-4 animate-spin" /></div>
          ) : conversations.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">
              {historyScope === "mine" ? "No previous conversations." : "No shared conversations yet."}
            </p>
          ) : (
            <div className="divide-y">
              {conversations.map((c) => (
                <div key={c.id} className="p-2 hover:bg-muted/40">
                  <div className="flex items-start gap-1.5">
                    <button
                      className="flex-1 min-w-0 text-left"
                      onClick={() => handleResume(c.id)}
                    >
                      <div className="flex items-start gap-1.5">
                        {c.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0 mt-0.5" />}
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate">{c.title || "Untitled"}</p>
                          <p className="text-[10px] text-muted-foreground">
                            {c.message_count} messages · {new Date(c.updated_at).toLocaleDateString()}
                            {c.visibility === "shared" && " · Shared"}
                          </p>
                        </div>
                      </div>
                    </button>
                    {c.user_id === currentUserId && (
                      <div className="flex gap-0.5 shrink-0">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={(e) => { e.stopPropagation(); handleTogglePin(c.id, c.pinned); }}
                          title={c.pinned ? "Unpin" : "Pin"}
                        >
                          <Pin className={`h-3 w-3 ${c.pinned ? "text-amber-500 fill-amber-500" : "text-muted-foreground"}`} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={(e) => { e.stopPropagation(); handleToggleShare(c.id, c.visibility); }}
                          title={c.visibility === "shared" ? "Make private" : "Share with team"}
                        >
                          <Share2 className={`h-3 w-3 ${c.visibility === "shared" ? "text-primary" : "text-muted-foreground"}`} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={`h-7 w-7 ${pendingDelete === c.id ? "bg-destructive/10" : ""}`}
                          onClick={(e) => { e.stopPropagation(); handleDelete(c.id); }}
                          title={pendingDelete === c.id ? "Tap to confirm" : "Delete"}
                        >
                          <Trash2 className={`h-3 w-3 ${pendingDelete === c.id ? "text-destructive" : "text-muted-foreground hover:text-destructive"}`} />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
          {messages.length === 0 && (
            <div className="text-center text-sm text-muted-foreground py-8">
              <Sparkles className="h-8 w-8 mx-auto mb-2 opacity-30" />
              <p>How can I help?</p>
              <p className="text-xs mt-1">Pool troubleshooting, dosing, parts, customer emails, broadcasts...</p>
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 px-3 py-2.5 border-t">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              // Auto-resize
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="Ask DeepBlue..."
            rows={1}
            className="flex-1 min-h-[40px] max-h-[120px] px-3 py-2.5 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
            disabled={isLoading}
          />
          <Button
            size="icon"
            className="h-10 w-10 shrink-0 rounded-lg"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
