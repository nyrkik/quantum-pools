"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Loader2, Menu } from "lucide-react";
import { DeepBlueSidebar } from "@/components/deepblue/deepblue-sidebar";
import { ChatMessageList } from "@/components/deepblue/chat-message-list";
import { ChatInput } from "@/components/deepblue/chat-input";
import type { ChatMessage } from "@/components/deepblue/message-row";
import type { ConversationListItem } from "@/components/deepblue/conversation-row";

interface ConversationDetail {
  id: string;
  title: string;
  visibility: string;
  pinned: boolean;
  case_id: string | null;
  messages: ChatMessage[];
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
      setSidebarOpen(false);
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
    setSidebarOpen(false);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    setStreamingContent("");

    const userMsg: ChatMessage = { role: "user", content: text, timestamp: new Date().toISOString() };
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
      const toolCalls: { name: string; input: Record<string, unknown> }[] = [];
      const toolResults: { name: string; result: Record<string, unknown> }[] = [];

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
            } else if (event.type === "tool_call") {
              toolCalls.push({ name: event.name, input: event.input });
            } else if (event.type === "tool_result") {
              toolResults.push({ name: event.name, result: event.result });
            } else if (event.type === "done" && event.conversation_id) {
              newConvoId = event.conversation_id;
            } else if (event.type === "error") {
              toast.error(event.message || "Error");
            }
          } catch {}
        }
      }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: fullContent,
        timestamp: new Date().toISOString(),
        toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        toolResults: toolResults.length > 0 ? toolResults : undefined,
      };
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

  const handleDeleteStart = (id: string) => {
    setPendingDelete(id);
    setTimeout(() => setPendingDelete((p) => (p === id ? null : p)), 5000);
  };

  const handleDeleteConfirm = async (id: string) => {
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

  const handleDeleteCancel = () => setPendingDelete(null);

  return (
    <div className="flex h-[calc(100vh-4rem)] sm:h-[calc(100vh-3rem)] -m-4 sm:-m-6 -mt-16 sm:-mt-6">
      <DeepBlueSidebar
        conversations={conversations}
        loadingList={loadingList}
        scope={scope}
        onScopeChange={setScope}
        search={search}
        onSearchChange={setSearch}
        activeId={activeId}
        currentUserId={currentUserId}
        pendingDelete={pendingDelete}
        sidebarOpen={sidebarOpen}
        onSidebarClose={() => setSidebarOpen(false)}
        onStartNew={startNew}
        onSelectConversation={(id) => loadConversation(id)}
        onTogglePin={handleTogglePin}
        onToggleShare={handleToggleShare}
        onDeleteStart={handleDeleteStart}
        onDeleteConfirm={handleDeleteConfirm}
        onDeleteCancel={handleDeleteCancel}
      />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 bg-muted/20">
        <div className="h-14 shrink-0 sm:hidden" />
        <div className="flex items-center justify-between p-3 border-b bg-background gap-2">
          <Button
            variant="outline"
            size="sm"
            className="sm:hidden h-8 gap-1.5 shrink-0"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-3.5 w-3.5" />
            Chats
          </Button>
          <p className="text-sm font-medium truncate flex-1 text-center sm:text-left">
            {active?.title || "New conversation"}
          </p>
          <div className="w-8 sm:hidden" />
        </div>

        <div className="flex-1 overflow-y-auto">
          {loadingActive ? (
            <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : (
            <div className="max-w-3xl mx-auto p-4 space-y-4">
              <ChatMessageList
                messages={active?.messages || []}
                streamingContent={streamingContent || undefined}
                emptyStateVariant="page"
              />
            </div>
          )}
        </div>

        <div className="border-t bg-background p-3">
          <div className="max-w-3xl mx-auto">
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSend}
              sending={sending}
              autoFocus={!!active}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
