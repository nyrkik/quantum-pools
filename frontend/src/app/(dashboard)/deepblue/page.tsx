"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  Sparkles, Send, Loader2, Plus, Pin, PinOff, Trash2, Users, Search, Menu, X, Lock,
} from "lucide-react";

interface ConversationListItem {
  id: string;
  title: string;
  user_id: string;
  visibility: string;
  pinned: boolean;
  message_count: number;
  updated_at: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

interface ConversationDetail {
  id: string;
  title: string;
  visibility: string;
  pinned: boolean;
  case_id: string | null;
  messages: Message[];
}

export default function DeepBluePage() {
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const currentUserId = user?.id || "";
  const initialId = searchParams.get("id");
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [scope, setScope] = useState<"mine" | "shared">("mine");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingActive, setLoadingActive] = useState(false);
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await api.get<{ conversations: ConversationListItem[] }>(
        `/v1/deepblue/conversations?scope=${scope}&limit=100`
      );
      setConversations(data.conversations);
    } catch {
      toast.error("Failed to load conversations");
    } finally {
      setLoadingList(false);
    }
  }, [scope]);

  useEffect(() => { loadList(); }, [loadList]);

  // Auto-load conversation from ?id= query param
  useEffect(() => {
    if (initialId && !active) {
      loadConversation(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialId]);

  const loadConversation = useCallback(async (id: string) => {
    setLoadingActive(true);
    try {
      const data = await api.get<ConversationDetail>(`/v1/deepblue/conversations/${id}`);
      setActive(data);
      setActiveId(id);
      setSidebarOpen(false); // close sidebar on mobile after selection
    } catch {
      toast.error("Failed to load conversation");
    } finally {
      setLoadingActive(false);
    }
  }, []);

  const startNew = () => {
    setActive(null);
    setActiveId(null);
    setSidebarOpen(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active, streamingContent]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setSending(true);
    setStreamingContent("");

    const userMsg: Message = { role: "user", content: text, timestamp: new Date().toISOString() };
    const currentMessages = active?.messages || [];
    setActive((prev) =>
      prev
        ? { ...prev, messages: [...currentMessages, userMsg] }
        : { id: "new", title: text.slice(0, 60), visibility: "private", pinned: false, case_id: null, messages: [userMsg] }
    );

    try {
      const resp = await fetch("/api/v1/deepblue/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          message: text,
          conversation_id: activeId,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No stream");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let newConvoId = activeId;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6).trim());
            if (event.type === "text_delta") {
              fullContent += event.content;
              setStreamingContent(fullContent);
            } else if (event.type === "done" && event.conversation_id) {
              newConvoId = event.conversation_id;
            } else if (event.type === "error") {
              toast.error(event.message || "Error");
            }
          } catch {}
        }
      }

      const assistantMsg: Message = { role: "assistant", content: fullContent, timestamp: new Date().toISOString() };
      setActive((prev) =>
        prev ? { ...prev, messages: [...prev.messages, assistantMsg], id: newConvoId || prev.id } : null
      );
      setActiveId(newConvoId);
      setStreamingContent("");
      loadList();
    } catch {
      toast.error("Failed to reach DeepBlue");
    } finally {
      setSending(false);
    }
  };

  const handleTogglePin = async (id: string, pinned: boolean) => {
    try {
      await fetch(`/api/v1/deepblue/conversations/${id}/pin`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ pinned: !pinned }),
      });
      loadList();
    } catch { toast.error("Failed"); }
  };

  const handleToggleShare = async (id: string, currentVisibility: string) => {
    try {
      await fetch(`/api/v1/deepblue/conversations/${id}/visibility`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ visibility: currentVisibility === "shared" ? "private" : "shared" }),
      });
      toast.success(currentVisibility === "shared" ? "Made private" : "Shared with team");
      loadList();
    } catch { toast.error("Failed"); }
  };

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
        method: "DELETE",
        credentials: "include",
      });
      if (!resp.ok) throw new Error();
      toast.success("Deleted");
      if (activeId === id) {
        setActive(null);
        setActiveId(null);
      }
      loadList();
    } catch { toast.error("Failed to delete"); }
  };

  const filtered = conversations.filter((c) =>
    !search.trim() || (c.title || "").toLowerCase().includes(search.toLowerCase())
  );

  const pinnedChats = filtered.filter((c) => c.pinned);
  const unpinnedChats = filtered.filter((c) => !c.pinned);

  return (
    <div className="flex h-[calc(100vh-4rem)] sm:h-[calc(100vh-3rem)] -m-4 sm:-m-6 -mt-16 sm:-mt-6">
      {/* Sidebar */}
      <div className={`
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} sm:translate-x-0
        fixed sm:static inset-y-0 left-0 z-40 w-72 bg-background border-r flex flex-col
        transition-transform duration-200
      `}>
        <div className="flex items-center justify-between p-3 border-b">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">DeepBlue</span>
          </div>
          <Button size="sm" variant="ghost" className="sm:hidden" onClick={() => setSidebarOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="p-2 space-y-2">
          <Button className="w-full justify-start" size="sm" onClick={startNew}>
            <Plus className="h-3.5 w-3.5 mr-1.5" /> New chat
          </Button>
          <div className="relative">
            <Search className="h-3 w-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="w-full h-8 pl-7 pr-2 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          </div>
          <div className="flex gap-1">
            <Button size="sm" variant={scope === "mine" ? "default" : "ghost"} className="h-6 text-[10px] flex-1" onClick={() => setScope("mine")}>
              Mine
            </Button>
            <Button size="sm" variant={scope === "shared" ? "default" : "ghost"} className="h-6 text-[10px] flex-1" onClick={() => setScope("shared")}>
              <Users className="h-2.5 w-2.5 mr-0.5" /> Shared
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {loadingList ? (
            <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">
              {scope === "mine" ? "No conversations yet." : "Nothing shared with the team."}
            </p>
          ) : (
            <>
              {pinnedChats.length > 0 && (
                <>
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground px-2 pt-2 pb-1">Pinned</p>
                  {pinnedChats.map((c) => (
                    <ConversationRow
                      key={c.id}
                      conv={c}
                      isActive={c.id === activeId}
                      showActions={c.user_id === currentUserId}
                      pendingDelete={pendingDelete}
                      onSelect={() => loadConversation(c.id)}
                      onPin={() => handleTogglePin(c.id, c.pinned)}
                      onShare={() => handleToggleShare(c.id, c.visibility)}
                      onDelete={() => handleDelete(c.id)}
                    />
                  ))}
                </>
              )}
              {unpinnedChats.length > 0 && (
                <>
                  {pinnedChats.length > 0 && (
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground px-2 pt-2 pb-1">Recent</p>
                  )}
                  {unpinnedChats.map((c) => (
                    <ConversationRow
                      key={c.id}
                      conv={c}
                      isActive={c.id === activeId}
                      showActions={c.user_id === currentUserId}
                      pendingDelete={pendingDelete}
                      onSelect={() => loadConversation(c.id)}
                      onPin={() => handleTogglePin(c.id, c.pinned)}
                      onShare={() => handleToggleShare(c.id, c.visibility)}
                      onDelete={() => handleDelete(c.id)}
                    />
                  ))}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Backdrop for mobile sidebar */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/30 z-30 sm:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 bg-muted/20">
        <div className="flex items-center justify-between p-3 border-b bg-background">
          <Button variant="ghost" size="icon" className="sm:hidden" onClick={() => setSidebarOpen(true)}>
            <Menu className="h-4 w-4" />
          </Button>
          <p className="text-sm font-medium truncate flex-1 text-center sm:text-left">
            {active?.title || "New conversation"}
          </p>
          <div className="w-8" />
        </div>

        <div className="flex-1 overflow-y-auto">
          {loadingActive ? (
            <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : !active && !streamingContent ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground p-6">
              <Sparkles className="h-12 w-12 opacity-30 mb-3" />
              <p className="text-sm font-medium">How can I help?</p>
              <p className="text-xs mt-1 max-w-md">
                Pool troubleshooting, chemical dosing, parts lookup, customer emails, broadcasts, and more.
              </p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto p-4 space-y-4">
              {active?.messages.map((m, i) => (
                <MessageRow key={i} message={m} />
              ))}
              {streamingContent && (
                <MessageRow message={{ role: "assistant", content: streamingContent }} />
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="border-t bg-background p-3">
          <div className="max-w-3xl mx-auto flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
              }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="Ask DeepBlue..."
              rows={1}
              disabled={sending}
              className="flex-1 min-h-[44px] max-h-[160px] px-3 py-2.5 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
            />
            <Button
              size="icon"
              className="h-11 w-11 shrink-0 rounded-lg"
              onClick={handleSend}
              disabled={!input.trim() || sending}
            >
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConversationRow({
  conv, isActive, showActions, pendingDelete, onSelect, onPin, onShare, onDelete,
}: {
  conv: ConversationListItem;
  isActive: boolean;
  showActions: boolean;
  pendingDelete: string | null;
  onSelect: () => void;
  onPin: () => void;
  onShare: () => void;
  onDelete: () => void;
}) {
  return (
    <div className={`group rounded-md p-1.5 ${isActive ? "bg-primary/10" : "hover:bg-muted/50"}`}>
      <button className="w-full text-left" onClick={onSelect}>
        <div className="flex items-center gap-1.5">
          {conv.pinned && <Pin className="h-2.5 w-2.5 text-amber-500 shrink-0" />}
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{conv.title || "Untitled"}</p>
            <p className="text-[10px] text-muted-foreground">
              {conv.message_count} · {new Date(conv.updated_at).toLocaleDateString()}
              {conv.visibility === "shared" && " · Shared"}
            </p>
          </div>
        </div>
      </button>
      {showActions && (
        <div className="flex items-center gap-0.5 mt-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={(e) => { e.stopPropagation(); onPin(); }}
            title={conv.pinned ? "Unpin conversation" : "Pin conversation"}
          >
            {conv.pinned ? (
              <Pin className="h-2.5 w-2.5 text-amber-500 fill-amber-500" />
            ) : (
              <PinOff className="h-2.5 w-2.5 text-muted-foreground" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={(e) => { e.stopPropagation(); onShare(); }}
            title={conv.visibility === "shared" ? "Shared with team — click to make private" : "Private — click to share with team"}
          >
            {conv.visibility === "shared" ? (
              <Users className="h-2.5 w-2.5 text-primary" />
            ) : (
              <Lock className="h-2.5 w-2.5 text-muted-foreground" />
            )}
          </Button>
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="icon"
            className={`h-6 w-6 ${pendingDelete === conv.id ? "bg-destructive/10" : ""}`}
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            title={pendingDelete === conv.id ? "Tap again to confirm delete" : "Delete conversation"}
          >
            <Trash2 className={`h-2.5 w-2.5 ${pendingDelete === conv.id ? "text-destructive" : "text-muted-foreground"}`} />
          </Button>
        </div>
      )}
    </div>
  );
}

function MessageRow({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] rounded-lg p-3 text-sm ${
        isUser ? "bg-primary text-primary-foreground" : "bg-background border"
      }`}>
        <div className="whitespace-pre-wrap">{message.content}</div>
      </div>
    </div>
  );
}
