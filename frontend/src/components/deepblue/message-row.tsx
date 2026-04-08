"use client";

import { Loader2 } from "lucide-react";
import { ToolResultCard } from "@/components/deepblue/tool-cards";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  toolCalls?: { name: string; input: Record<string, unknown> }[];
  toolResults?: { name: string; result: Record<string, unknown> }[];
}

/** Parse stored messages (from API) into ChatMessage format, reconstructing tool data from blocks. */
export function parseStoredMessages(raw: Record<string, unknown>[], conversationId: string = ""): ChatMessage[] {
  return raw.map((m, i) => {
    const blocks = m.blocks as Array<Record<string, unknown>> | undefined;
    let content = (m.content as string) || "";
    const toolCalls: { name: string; input: Record<string, unknown> }[] = [];
    const toolResults: { name: string; result: Record<string, unknown> }[] = [];

    if (blocks) {
      for (const block of blocks) {
        if (block.type === "text") {
          content += (block.text as string) || "";
        } else if (block.type === "tool_use") {
          toolCalls.push({ name: block.name as string, input: (block.input as Record<string, unknown>) || {} });
        } else if (block.type === "tool_result") {
          const resultContent = block.content as string | undefined;
          const toolId = block.tool_use_id as string;
          const matchedCall = blocks.find((b) => b.type === "tool_use" && b.id === toolId);
          const name = (matchedCall?.name as string) || "unknown";
          try {
            const parsed = resultContent ? JSON.parse(resultContent) : {};
            toolResults.push({ name, result: parsed });
          } catch {
            toolResults.push({ name, result: { raw: resultContent } });
          }
        }
      }
    }

    return {
      role: (m.role as string) as "user" | "assistant",
      content,
      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
      toolResults: toolResults.length > 0 ? toolResults : undefined,
      timestamp: (m.timestamp as string) || new Date().toISOString(),
    };
  });
}

interface MessageRowProps {
  message: ChatMessage;
  stale?: boolean;
}

export function MessageRow({ message, stale = false }: MessageRowProps) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] rounded-lg p-3 text-sm ${
        isUser ? "bg-primary text-primary-foreground" : "bg-background border"
      }`}>
        {message.content && (
          <div className="whitespace-pre-wrap">{message.content}</div>
        )}
        {message.toolResults?.map((tr, i) => (
          <ToolResultCard key={i} name={tr.name} result={tr.result} stale={stale} />
        ))}
        {message.toolCalls && message.toolCalls.length > (message.toolResults?.length || 0) && (
          <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Working...
          </div>
        )}
      </div>
    </div>
  );
}
