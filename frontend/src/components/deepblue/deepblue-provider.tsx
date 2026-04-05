"use client";

import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from "react";

export interface DeepBlueContextData {
  customerId?: string;
  propertyId?: string;
  bowId?: string;
  visitId?: string;
  caseId?: string;
}

export interface DeepBlueMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: { name: string; input: Record<string, unknown> }[];
  toolResults?: { name: string; result: Record<string, unknown> }[];
  timestamp: string;
}

interface DeepBlueState {
  isOpen: boolean;
  isLoading: boolean;
  messages: DeepBlueMessage[];
  conversationId: string | null;
  context: DeepBlueContextData;
  openDeepBlue: () => void;
  closeDeepBlue: () => void;
  toggleDeepBlue: () => void;
  setContext: (ctx: DeepBlueContextData) => void;
  sendMessage: (text: string) => Promise<void>;
  clearConversation: () => void;
  saveToCase: (caseId: string) => Promise<boolean>;
}

const DeepBlueContext = createContext<DeepBlueState | null>(null);

let msgCounter = 0;

export function DeepBlueProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<DeepBlueMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const contextRef = useRef<DeepBlueContextData>({});

  const openDeepBlue = useCallback(() => setIsOpen(true), []);
  const closeDeepBlue = useCallback(() => setIsOpen(false), []);
  const toggleDeepBlue = useCallback(() => setIsOpen((p) => !p), []);

  const setContext = useCallback((ctx: DeepBlueContextData) => {
    contextRef.current = ctx;
  }, []);

  const clearConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
  }, []);

  const saveToCase = useCallback(async (caseId: string): Promise<boolean> => {
    if (!conversationId) return false;
    try {
      await fetch(`/api/v1/deepblue/conversations/${conversationId}/save-to-case`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ case_id: caseId }),
      });
      return true;
    } catch {
      return false;
    }
  }, [conversationId]);

  const sendMessage = useCallback(async (text: string) => {
    const userMsg: DeepBlueMessage = {
      id: `msg-${++msgCounter}`,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    const assistantMsg: DeepBlueMessage = {
      id: `msg-${++msgCounter}`,
      role: "assistant",
      content: "",
      toolCalls: [],
      toolResults: [],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, assistantMsg]);
    const assistantId = assistantMsg.id;

    try {
      const ctx = contextRef.current;
      const resp = await fetch("/api/v1/deepblue/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
          customer_id: ctx.customerId || null,
          property_id: ctx.propertyId || null,
          bow_id: ctx.bowId || null,
          visit_id: ctx.visitId || null,
        }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (!data) continue;

          try {
            const event = JSON.parse(data);

            if (event.type === "text_delta") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + event.content }
                    : m
                )
              );
            } else if (event.type === "tool_call") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, toolCalls: [...(m.toolCalls || []), { name: event.name, input: event.input }] }
                    : m
                )
              );
            } else if (event.type === "tool_result") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, toolResults: [...(m.toolResults || []), { name: event.name, result: event.result }] }
                    : m
                )
              );
            } else if (event.type === "done") {
              if (event.conversation_id) {
                setConversationId(event.conversation_id);
              }
            } else if (event.type === "error") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content || `Error: ${event.message}` }
                    : m
                )
              );
            }
          } catch {
            // Skip malformed events
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Failed to reach DeepBlue. Check your connection." }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  return (
    <DeepBlueContext.Provider
      value={{
        isOpen, isLoading, messages, conversationId, context: contextRef.current,
        openDeepBlue, closeDeepBlue, toggleDeepBlue, setContext, sendMessage, clearConversation, saveToCase,
      }}
    >
      {children}
    </DeepBlueContext.Provider>
  );
}

export function useDeepBlue(): DeepBlueState {
  const ctx = useContext(DeepBlueContext);
  if (!ctx) throw new Error("useDeepBlue must be used within DeepBlueProvider");
  return ctx;
}

/**
 * Hook for pages to set DeepBlue context. Automatically clears on unmount.
 */
export function useDeepBlueContext(ctx: DeepBlueContextData) {
  const state = useContext(DeepBlueContext);
  const setCtx = state?.setContext;
  useEffect(() => {
    if (!setCtx) return;
    setCtx(ctx);
    return () => setCtx({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setCtx, ctx.customerId, ctx.propertyId, ctx.bowId, ctx.visitId, ctx.caseId]);
}
