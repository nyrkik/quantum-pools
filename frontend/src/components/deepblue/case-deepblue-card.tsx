"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Sparkles, Send, Loader2, Plus, ChevronDown, ChevronUp } from "lucide-react";

interface ConversationMessage {
  role: string;
  content: string;
  timestamp: string;
}

interface Conversation {
  id: string;
  title: string;
  messages: ConversationMessage[];
  updated_at: string;
}

export function CaseDeepBlueCard({
  caseId,
  customerId,
  conversations: initialConversations,
  onUpdate,
}: {
  caseId: string;
  customerId: string | null;
  conversations: Conversation[];
  onUpdate: () => void;
}) {
  const [conversations, setConversations] = useState<Conversation[]>(initialConversations);
  const [activeConvoId, setActiveConvoId] = useState<string | null>(
    initialConversations.length > 0 ? initialConversations[0].id : null
  );
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [expanded, setExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setConversations(initialConversations);
    if (!activeConvoId && initialConversations.length > 0) {
      setActiveConvoId(initialConversations[0].id);
    }
  }, [initialConversations]);

  useEffect(() => {
    if (expanded) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversations, streamingContent, expanded]);

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
    const tempUserMsg: ConversationMessage = { role: "user", content: text, timestamp: new Date().toISOString() };
    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeConvoId
          ? { ...c, messages: [...c.messages, tempUserMsg] }
          : c
      )
    );

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
            } else if (event.type === "done" && event.conversation_id) {
              newConvoId = event.conversation_id;
            }
          } catch {}
        }
      }

      // Finalize: add assistant message to conversation
      const assistantMsg: ConversationMessage = { role: "assistant", content: fullContent, timestamp: new Date().toISOString() };

      if (newConvoId && newConvoId !== activeConvoId) {
        // New conversation was created
        setActiveConvoId(newConvoId);
        setConversations((prev) => [
          { id: newConvoId!, title: text.slice(0, 60), messages: [tempUserMsg, assistantMsg], updated_at: new Date().toISOString() },
          ...prev,
        ]);
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
          <div className="max-h-[300px] overflow-y-auto space-y-2 mb-2">
            {activeConvo?.messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs ${
                  m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted/70"
                }`}>
                  <div className="whitespace-pre-wrap">{m.content}</div>
                </div>
              </div>
            ))}
            {streamingContent && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs bg-muted/70">
                  <div className="whitespace-pre-wrap">{streamingContent}</div>
                </div>
              </div>
            )}
            {!activeConvo?.messages.length && !streamingContent && (
              <p className="text-xs text-muted-foreground text-center py-3">
                Ask DeepBlue about this case...
              </p>
            )}
            <div ref={messagesEndRef} />
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
