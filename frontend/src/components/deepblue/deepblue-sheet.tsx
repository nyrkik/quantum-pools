"use client";

import { useState, useEffect } from "react";
import { useDeepBlue } from "./deepblue-provider";
import { Button } from "@/components/ui/button";
import { Sparkles, Loader2, Trash2, ChevronDown, FolderOpen, History, Pin, Users, Share2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { ChatMessageList } from "./chat-message-list";
import { ChatInput } from "./chat-input";


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

// Draft survives close/reopen, route changes, and even browser reload.
// Closing the DeepBlue sheet unmounts the component, which used to destroy
// local input state along with any in-progress draft.
const DRAFT_KEY = "deepblue:input-draft";

function readDraft(): string {
  if (typeof window === "undefined") return "";
  try {
    return sessionStorage.getItem(DRAFT_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeDraft(value: string) {
  if (typeof window === "undefined") return;
  try {
    if (value) sessionStorage.setItem(DRAFT_KEY, value);
    else sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* sessionStorage may be unavailable in private mode */
  }
}

export function DeepBlueSheet() {
  const { user } = useAuth();
  const currentUserId = user?.id || "";
  const {
    isOpen, isLoading, isHistorical, messages, context, conversationId, closeDeepBlue, sendMessage, clearConversation, saveToCase, loadConversation,
  } = useDeepBlue();
  const [input, setInputState] = useState<string>(() => readDraft());
  const setInput = (value: string) => {
    setInputState(value);
    writeDraft(value);
  };
  const [showHistory, setShowHistory] = useState(false);
  const [historyScope, setHistoryScope] = useState<"mine" | "shared">("mine");
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

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


  const handleSend = async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    // Optimistic clear: the user's message gets echoed into the chat list
    // by sendMessage, so leaving the textbox full looks like nothing
    // happened. Clear immediately. If the send throws, restore the text
    // and tell the user so their work isn't silently lost.
    setInput("");
    try {
      await sendMessage(text);
    } catch (err) {
      setInput(text);
      const msg = err instanceof Error ? err.message : "Send failed";
      toast.error(`${msg} — your message is still in the box`);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[70] flex flex-col bg-blue-50 dark:bg-blue-950 border-t border-blue-300 dark:border-blue-700 shadow-2xl ring-1 ring-blue-300/60 sm:right-4 sm:left-auto sm:bottom-4 sm:w-[420px] sm:rounded-xl sm:border sm:border-blue-300 dark:sm:border-blue-700 sm:max-h-[600px] sm:shadow-[0_8px_40px_-8px_rgba(30,64,175,0.15)]"
      style={{ maxHeight: "75vh" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-blue-300 dark:border-blue-700 bg-blue-100/60 dark:bg-blue-900/30 shrink-0 sm:rounded-t-xl">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          <span className="text-sm font-medium text-blue-700 dark:text-blue-300">DeepBlue</span>
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
          <ChatMessageList messages={messages} emptyStateVariant="sheet" historical={isHistorical} conversationId={conversationId} />
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 px-3 py-2.5 border-t border-blue-300 dark:border-blue-700">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          sending={isLoading}
          autoFocus={isOpen}
        />
      </div>
    </div>
  );
}
