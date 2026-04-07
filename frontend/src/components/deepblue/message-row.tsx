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
