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

/**
 * Parse stored messages (from API) into ChatMessage format.
 *
 * Anthropic stores tool interactions as:
 *   assistant message → blocks: [text, tool_use]
 *   user message → blocks: [tool_result]   (linked by tool_use_id)
 *
 * We merge tool_result user messages INTO the preceding assistant message
 * as toolResults, so the UI shows tool cards on the assistant bubble.
 * Pure tool_result user messages are hidden (they're infrastructure).
 */
export function parseStoredMessages(raw: Record<string, unknown>[], conversationId: string = ""): ChatMessage[] {
  // First pass: build a map of tool_use_id → tool name from assistant messages
  const toolNameMap: Record<string, string> = {};
  for (const m of raw) {
    const blocks = m.blocks as Array<Record<string, unknown>> | undefined;
    if (blocks) {
      for (const b of blocks) {
        if (b.type === "tool_use" && b.id && b.name) {
          toolNameMap[b.id as string] = b.name as string;
        }
      }
    }
  }

  // Second pass: build ChatMessages, merging tool results into assistant messages
  const result: ChatMessage[] = [];
  let lastAssistant: ChatMessage | null = null;

  for (const m of raw) {
    const role = m.role as string;
    const blocks = m.blocks as Array<Record<string, unknown>> | undefined;

    if (role === "assistant") {
      let content = (m.content as string) || "";
      const toolCalls: { name: string; input: Record<string, unknown> }[] = [];

      if (blocks) {
        for (const b of blocks) {
          if (b.type === "text") content += (b.text as string) || "";
          else if (b.type === "tool_use") {
            toolCalls.push({ name: b.name as string, input: (b.input as Record<string, unknown>) || {} });
          }
        }
      }

      const msg: ChatMessage = {
        role: "assistant",
        content,
        toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        toolResults: [],
        timestamp: (m.timestamp as string) || new Date().toISOString(),
      };
      result.push(msg);
      lastAssistant = msg;

    } else if (role === "user") {
      // Check if this is a pure tool_result message (infrastructure, hide from UI)
      const hasToolResult = blocks?.some((b) => b.type === "tool_result");
      const hasText = !!(m.content as string)?.trim() || blocks?.some((b) => b.type === "text" && (b.text as string)?.trim());

      if (hasToolResult && !hasText) {
        // Pure tool result — merge into preceding assistant message
        if (lastAssistant && blocks) {
          for (const b of blocks) {
            if (b.type === "tool_result") {
              const toolId = b.tool_use_id as string;
              const name = toolNameMap[toolId] || "unknown";
              const resultContent = b.content as string | undefined;
              try {
                const parsed = resultContent ? JSON.parse(resultContent) : {};
                lastAssistant.toolResults = [...(lastAssistant.toolResults || []), { name, result: parsed }];
              } catch {
                lastAssistant.toolResults = [...(lastAssistant.toolResults || []), { name, result: { raw: resultContent } }];
              }
            }
          }
        }
        // Don't add this as a visible message
        continue;
      }

      // Regular user message
      result.push({
        role: "user",
        content: (m.content as string) || "",
        timestamp: (m.timestamp as string) || new Date().toISOString(),
      });
      lastAssistant = null;
    }
  }

  // Clean up empty toolResults arrays
  for (const msg of result) {
    if (msg.toolResults && msg.toolResults.length === 0) {
      msg.toolResults = undefined;
    }
  }

  return result;
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
