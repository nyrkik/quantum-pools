"use client";

import { useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Send, Loader2 } from "lucide-react";
import { VoiceDictationButton } from "@/components/voice/voice-dictation-button";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  sending: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}

export function ChatInput({ value, onChange, onSend, sending, autoFocus = false, placeholder = "Ask DeepBlue..." }: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [autoFocus]);

  const handleSend = () => {
    if (!value.trim() || sending) return;
    onSend();
    // Re-focus after send
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  return (
    <div className="flex items-end gap-2">
      <textarea
        ref={inputRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder={placeholder}
        rows={1}
        className="flex-1 min-h-[40px] max-h-[160px] px-3 py-2.5 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
        disabled={sending}
      />
      <VoiceDictationButton
        surface="deepblue_chat"
        size="md"
        disabled={sending}
        onTranscript={(text) => onChange(value ? `${value} ${text}` : text)}
      />
      <Button
        size="icon"
        className="h-10 w-10 shrink-0 rounded-lg"
        onClick={handleSend}
        disabled={!value.trim() || sending}
      >
        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
      </Button>
    </div>
  );
}

/** Reset textarea height after clearing input */
export function resetTextareaHeight(el: HTMLTextAreaElement | null) {
  if (el) el.style.height = "auto";
}
