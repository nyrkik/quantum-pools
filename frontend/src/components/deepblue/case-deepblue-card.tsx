"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Sparkles, Send, Loader2, Plus, ChevronDown, ChevronUp } from "lucide-react";
import { ChatMessageList } from "./chat-message-list";
import { parseStoredMessages, type ChatMessage } from "./message-row";

interface RawConversation {
  id: string;
  title: string;
  messages: Record<string, unknown>[];
  updated_at: string;
}

interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  updated_at: string;
}

function parseConversations(raw: RawConversation[]): Conversation[] {
  return raw.map((c) => ({
    ...c,
    messages: parseStoredMessages(c.messages, c.id),
  }));
}

export function CaseDeepBlueCard({
  caseId,
  customerId,
  conversations: initialConversations,
  onUpdate,
}: {
  caseId: string;
  customerId: string | null;
  conversations: RawConversation[];
  onUpdate: () => void;
}) {
  const [conversations, setConversations] = useState<Conversation[]>(() => parseConversations(initialConversations));
  const [activeConvoId, setActiveConvoId] = useState<string | null>(
    initialConversations.length > 0 ? initialConversations[0].id : null
  );
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [expanded, setExpanded] = useState(initialConversations.length > 0);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const parsed = parseConversations(initialConversations);
    setConversations(parsed);
    if (!activeConvoId && parsed.length > 0) {
      setActiveConvoId(parsed[0].id);
    }
  }, [initialConversations]);


  const activeConvo = conversations.find((c) => c.id === activeConvoId);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setIsLoading(true);
    setStreamingContent("");
    if (!expanded) setExpanded(true);

    // Optimistic user message
    const tempUserMsg: ChatMessage = { role: "user", content: text, timestamp: new Date().toISOString() };
    if (activeConvoId) {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeConvoId
            ? { ...c, messages: [...c.messages, tempUserMsg] }
            : c
        )
      );
    } else {
      // New conversation — create a temporary entry so the message is visible
      const tempId = `temp-${Date.now()}`;
      setConversations((prev) => [
        { id: tempId, title: text.slice(0, 60), messages: [tempUserMsg], updated_at: new Date().toISOString() },
        ...prev,
      ]);
      setActiveConvoId(tempId);
    }

    try {
      const resp = await fetch("/api/v1/deepblue/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          message: text,
          conversation_id: activeConvoId,
          case_id: caseId,
          customer_id: customerId,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No stream");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let toolResults: { name: string; result: Record<string, unknown> }[] = [];
      let newConvoId = activeConvoId;

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
            } else if (event.type === "tool_result") {
              toolResults.push({ name: event.name, result: event.result });
            } else if (event.type === "done" && event.conversation_id) {
              newConvoId = event.conversation_id;
            }
          } catch {}
        }
      }

      // Finalize: add assistant message to conversation
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: fullContent,
        timestamp: new Date().toISOString(),
        toolResults: toolResults.length > 0 ? toolResults : undefined,
      };

      if (newConvoId && newConvoId !== activeConvoId) {
        // New conversation was created — replace temp entry or prepend
        setActiveConvoId(newConvoId);
        setConversations((prev) => {
          const withoutTemp = prev.filter((c) => !c.id.startsWith("temp-"));
          return [
            { id: newConvoId!, title: text.slice(0, 60), messages: [tempUserMsg, assistantMsg], updated_at: new Date().toISOString() },
            ...withoutTemp,
          ];
        });
      } else {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === activeConvoId
              ? { ...c, messages: [...c.messages, assistantMsg] }
              : c
          )
        );
      }
      setStreamingContent("");
      onUpdate();
    } catch {
      setStreamingContent("Failed to reach DeepBlue.");
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, activeConvoId, caseId, customerId, expanded, onUpdate]);

  const startNewConversation = () => {
    setActiveConvoId(null);
    setExpanded(true);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            DeepBlue
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={startNewConversation}>
              <Plus className="h-3 w-3 mr-0.5" /> New
            </Button>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setExpanded(!expanded)}>
              {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Conversation tabs if multiple */}
        {conversations.length > 1 && (
          <div className="flex gap-1 mb-2 overflow-x-auto pb-1">
            {conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => { setActiveConvoId(c.id); setExpanded(true); }}
                className={`text-[10px] px-2 py-1 rounded-full whitespace-nowrap border ${
                  c.id === activeConvoId ? "bg-primary text-primary-foreground border-primary" : "bg-muted/50 border-transparent hover:bg-muted"
                }`}
              >
                {c.title?.slice(0, 25) || "Conversation"}
              </button>
            ))}
          </div>
        )}

        {/* Messages */}
        {expanded && (
          <div className="max-h-[300px] overflow-y-auto overflow-x-hidden space-y-2 mb-2 break-words">
            <ChatMessageList
              messages={activeConvo?.messages || []}
              streamingContent={streamingContent || undefined}
              emptyStateVariant="sheet"
              historical={false}
              conversationId={activeConvoId}
            />
          </div>
        )}

        {/* Input */}
        <div className="flex items-end gap-1.5">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 80) + "px";
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            onFocus={() => { if (!expanded) setExpanded(true); }}
            placeholder="Ask DeepBlue..."
            rows={1}
            className="flex-1 min-h-[36px] max-h-[80px] px-2.5 py-2 rounded-md border bg-background text-xs focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none"
            disabled={isLoading}
          />
          <Button
            size="icon"
            className="h-9 w-9 shrink-0 rounded-md"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
          >
            {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
