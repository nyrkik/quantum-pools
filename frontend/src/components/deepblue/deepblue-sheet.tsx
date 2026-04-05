"use client";

import { useState, useRef, useEffect } from "react";
import { useDeepBlue, type DeepBlueMessage } from "./deepblue-provider";
import { Button } from "@/components/ui/button";
import { Bot, X, Send, Loader2, Trash2, ChevronDown, FolderOpen, Mail } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

function ToolResultCard({ name, result }: { name: string; result: Record<string, unknown> }) {
  if (name === "chemical_dosing_calculator") {
    const dosing = result.dosing as Array<Record<string, unknown>> | undefined;
    if (!dosing?.length) return null;
    const issues = dosing.filter((d) => d.status !== "ok");
    return (
      <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-1">
        <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
          Dosing — {result.pool_gallons?.toLocaleString()} gal
        </p>
        {issues.length === 0 ? (
          <p className="text-green-600">All readings in range</p>
        ) : (
          issues.map((d, i) => (
            <div key={i} className="flex justify-between items-start gap-2">
              <div>
                <span className={`font-medium ${d.status === "high" ? "text-red-600" : "text-amber-600"}`}>
                  {d.parameter as string}: {String(d.current)}
                </span>
                <span className="text-muted-foreground ml-1">(target: {d.target as string})</span>
              </div>
              {d.amount ? (
                <span className="text-right shrink-0 font-mono">{String(d.amount)}</span>
              ) : null}
            </div>
          ))
        )}
      </div>
    );
  }

  if (name === "get_equipment") {
    const equipment = result.equipment as Array<Record<string, unknown>> | undefined;
    if (!equipment?.length) return <p className="text-xs text-muted-foreground mt-1">No equipment found.</p>;
    return (
      <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-0.5">
        <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">Equipment</p>
        {equipment.map((e, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-muted-foreground w-16 shrink-0">{e.type as string}</span>
            <span className="font-medium">{e.name as string}</span>
          </div>
        ))}
      </div>
    );
  }

  if (name === "find_replacement_parts") {
    const catalogParts = result.catalog_parts as Array<Record<string, unknown>> | undefined;
    const webResults = result.web_results as Array<Record<string, unknown>> | undefined;
    const matched = result.equipment_matched as string | undefined;
    const hasParts = (catalogParts?.length || 0) + (webResults?.length || 0) > 0;
    return (
      <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-1">
        {matched && (
          <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
            Parts — {matched}
          </p>
        )}
        {!hasParts ? (
          <p className="text-muted-foreground">No parts found.</p>
        ) : (
          <>
            {catalogParts && catalogParts.length > 0 && catalogParts.slice(0, 5).map((p, i) => (
              <div key={`c${i}`} className="flex justify-between gap-2">
                <span>{p.name as string}</span>
                {p.sku ? <span className="text-muted-foreground shrink-0">{String(p.sku)}</span> : null}
              </div>
            ))}
            {webResults && webResults.length > 0 && (
              <>
                <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground mt-1.5">Online</p>
                {webResults.slice(0, 5).map((r, i) => (
                  <div key={`w${i}`} className="flex justify-between gap-2">
                    {r.url ? (
                      <a href={String(r.url)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline truncate">
                        {r.name as string}
                      </a>
                    ) : (
                      <span className="truncate">{r.name as string}</span>
                    )}
                    {r.price ? <span className="font-mono shrink-0">${Number(r.price).toFixed(2)}</span> : null}
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>
    );
  }

  if (name === "draft_broadcast_email" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    return <BroadcastPreviewCard preview={preview} />;
  }

  // Generic fallback
  return null;
}

function BroadcastPreviewCard({ preview }: { preview: Record<string, unknown> }) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [result, setResult] = useState<{ sent_count: number; failed_count: number } | null>(null);

  const handleConfirm = async () => {
    setSending(true);
    try {
      const res = await api.post<{ sent_count: number; failed_count: number; recipient_count: number }>(
        "/v1/deepblue/confirm-broadcast",
        {
          subject: preview.subject,
          body: preview.body,
          filter_type: preview.filter_type,
        }
      );
      setResult(res);
      setSent(true);
      toast.success(`Broadcast sent to ${res.sent_count} customers`);
    } catch {
      toast.error("Failed to send broadcast");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="bg-muted/50 rounded-md p-2.5 mt-1.5 text-xs space-y-2 border border-primary/20">
      <div className="flex items-center gap-1.5">
        <Mail className="h-3 w-3 text-primary" />
        <span className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">Broadcast Preview</span>
      </div>
      <div className="space-y-1">
        <p className="font-medium">{String(preview.subject)}</p>
        <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{String(preview.body)}</p>
      </div>
      <div className="flex items-center justify-between pt-1 border-t">
        <span className="text-muted-foreground">
          {String(preview.filter_label)} — <span className="font-medium text-foreground">{String(preview.recipient_count)} recipients</span>
        </span>
      </div>
      {sent && result ? (
        <p className="text-green-600 font-medium">
          Sent to {result.sent_count} customers{result.failed_count > 0 ? ` (${result.failed_count} failed)` : ""}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" className="h-8 flex-1" onClick={handleConfirm} disabled={sending}>
            {sending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Send className="h-3 w-3 mr-1" />}
            Send to {String(preview.recipient_count)} customers
          </Button>
          <Button variant="ghost" size="sm" className="h-8">Cancel</Button>
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: DeepBlueMessage }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] rounded-lg p-3 text-sm ${
        isUser
          ? "bg-primary text-primary-foreground"
          : "bg-muted/70"
      }`}>
        {msg.content && (
          <div className="whitespace-pre-wrap">{msg.content}</div>
        )}
        {/* Tool result cards */}
        {msg.toolResults?.map((tr, i) => (
          <ToolResultCard key={i} name={tr.name} result={tr.result} />
        ))}
        {/* Loading indicator for tool calls without results yet */}
        {msg.toolCalls && msg.toolCalls.length > (msg.toolResults?.length || 0) && (
          <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Looking up data...
          </div>
        )}
      </div>
    </div>
  );
}

export function DeepBlueSheet() {
  const {
    isOpen, isLoading, messages, context, conversationId, closeDeepBlue, sendMessage, clearConversation, saveToCase,
  } = useDeepBlue();
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    sendMessage(text);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[70] flex flex-col bg-background border-t shadow-2xl sm:right-4 sm:left-auto sm:bottom-4 sm:w-[420px] sm:rounded-xl sm:border sm:max-h-[600px]"
      style={{ maxHeight: "75vh" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b bg-primary/5 shrink-0 sm:rounded-t-xl">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">DeepBlue</span>
        </div>
        <div className="flex items-center gap-1">
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

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {messages.length === 0 && (
          <div className="text-center text-sm text-muted-foreground py-8">
            <Bot className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p>How can I help?</p>
            <p className="text-xs mt-1">Pool troubleshooting, dosing, parts, customer emails, broadcasts...</p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 px-3 py-2.5 border-t">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              // Auto-resize
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="Ask DeepBlue..."
            rows={1}
            className="flex-1 min-h-[40px] max-h-[120px] px-3 py-2.5 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
            disabled={isLoading}
          />
          <Button
            size="icon"
            className="h-10 w-10 shrink-0 rounded-lg"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
