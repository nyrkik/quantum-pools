"use client";

import { useEffect, useRef } from "react";
import { Sparkles } from "lucide-react";
import { MessageRow, type ChatMessage } from "./message-row";

interface ChatMessageListProps {
  messages: ChatMessage[];
  streamingContent?: string;
  emptyStateVariant?: "page" | "sheet";
  /** If true, all confirmation cards are disabled (loaded from history). */
  historical?: boolean;
  conversationId?: string | null;
}

export function ChatMessageList({ messages, streamingContent, emptyStateVariant = "page", historical = false, conversationId }: ChatMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  if (messages.length === 0 && !streamingContent) {
    return emptyStateVariant === "sheet" ? (
      <div className="text-center text-sm py-8">
        <Sparkles className="h-8 w-8 mx-auto mb-2 text-blue-400/50" />
        <p className="text-blue-700/70 dark:text-blue-300/70">How can I help?</p>
        <p className="text-xs mt-1 text-blue-600/50 dark:text-blue-400/50">Pool troubleshooting, dosing, parts, customer emails, broadcasts...</p>
      </div>
    ) : (
      <div className="text-center text-muted-foreground py-16">
        <Sparkles className="h-10 w-10 mx-auto mb-3 opacity-20" />
        <p className="text-sm font-medium">How can I help?</p>
        <p className="text-xs mt-1 max-w-md">
          Pool troubleshooting, chemical dosing, parts lookup, customer emails, broadcasts, and more.
        </p>
      </div>
    );
  }

  // Build map: for each confirmation tool name, which message index has the LAST occurrence?
  const lastToolIndex: Record<string, number> = {};
  const confirmTools = new Set(["draft_broadcast_email", "draft_customer_email", "add_equipment_to_pool", "log_chemical_reading", "update_customer_note"]);
  messages.forEach((m, i) => {
    m.toolResults?.forEach((tr) => {
      if (confirmTools.has(tr.name)) {
        lastToolIndex[tr.name] = i;
      }
    });
  });

  return (
    <>
      {messages.map((m, i, arr) => {
        const hasUserMsgAfter = arr.slice(i + 1).some((later) => later.role === "user");
        // For this message's tool results, is each one the last of its type?
        const toolLastFlags = m.toolResults?.map((tr) =>
          confirmTools.has(tr.name) ? lastToolIndex[tr.name] === i : true
        );
        return <MessageRow key={i} message={m} stale={historical || hasUserMsgAfter} toolLastFlags={toolLastFlags} conversationId={conversationId} />;
      })}
      {streamingContent && (
        <MessageRow message={{ role: "assistant", content: streamingContent }} />
      )}
      <div ref={endRef} />
    </>
  );
}
