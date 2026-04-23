"use client";

import { useState, useRef, useEffect } from "react";
import { SmilePlus } from "lucide-react";
import data from "@emoji-mart/data";
import Picker from "@emoji-mart/react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export interface MessageReaction {
  emoji: string;
  count: number;
  user_ids: string[];
  user_names: string[];
}

interface Props {
  messageId: string;
  reactions: MessageReaction[];
  currentUserId: string;
  /** Align chips right-aligned for the current user's own bubble. */
  alignRight?: boolean;
  /** Called after a successful add/remove so the parent can refetch. */
  onChange?: () => void;
}

// Six quick-pick reactions, ordered by what people actually use on staff
// chat. Thumbs pair is intentionally adjacent. Keep small — too many
// inline defeats the purpose (vs. the + picker button).
const QUICK_REACTIONS = ["👍", "👎", "❤️", "😂", "🎉", "🙏"];

export function MessageReactions({
  messageId,
  reactions,
  currentUserId,
  alignRight,
  onChange,
}: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pickerOpen && !quickOpen) return;
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
        setQuickOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [pickerOpen, quickOpen]);

  const toggle = async (emoji: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/v1/messages/reactions/${messageId}`, { emoji });
      setPickerOpen(false);
      setQuickOpen(false);
      onChange?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to react");
    } finally {
      setBusy(false);
    }
  };

  // iMessage/Slack/Discord overlap pattern:
  //  - Reaction chips overlap the bottom edge of the bubble (half above,
  //    half below) — only visible when reactions exist. Solid background +
  //    shadow so they read as stickers on top of the message.
  //  - The "+" add button is hidden at rest; reveals on hover over the
  //    bubble (parent message wrapper must carry the `group` class), or
  //    while the picker is open. Solid + shadow when shown, no washed-out
  //    translucency.
  //  - Empty state takes zero layout space so messages without reactions
  //    look identical to before this feature.
  const hasAny = reactions.length > 0;
  const showPicker = pickerOpen || quickOpen;
  const addButtonVisibility = showPicker
    ? "opacity-100"
    : "opacity-0 group-hover:opacity-100 focus-within:opacity-100";
  return (
    <div
      ref={wrapRef}
      className={cn(
        "relative flex flex-wrap items-center gap-1",
        alignRight && "justify-end",
        hasAny ? "-mt-2.5 px-2 z-10" : "h-0",
      )}
    >
      {reactions.map((r) => {
        const mine = r.user_ids.includes(currentUserId);
        const title = r.user_names.join(", ");
        return (
          <button
            key={r.emoji}
            type="button"
            onClick={() => toggle(r.emoji)}
            disabled={busy}
            title={title}
            className={cn(
              // Solid opaque background on every chip so the top half that
              // overlaps a colored message bubble stays readable. "Mine"
              // state is signaled by a thicker primary-colored border +
              // count color, NOT a translucent fill — translucent fills
              // vanish into same-colored bubbles behind them.
              "inline-flex items-center gap-1 h-6 px-1.5 rounded-full border text-xs leading-none transition-colors shadow-sm bg-background text-foreground hover:bg-muted",
              mine ? "border-2 border-primary" : "border-border",
            )}
          >
            <span>{r.emoji}</span>
            <span className={cn("text-[11px] tabular-nums", mine && "text-primary font-semibold")}>{r.count}</span>
          </button>
        );
      })}

      <button
        type="button"
        onClick={() => setQuickOpen((v) => !v)}
        disabled={busy}
        className={cn(
          "inline-flex items-center h-6 w-6 justify-center rounded-full border border-border bg-background text-muted-foreground shadow-sm hover:bg-muted hover:text-foreground transition-opacity",
          addButtonVisibility,
          // When no chips exist, absolutely position the button at the
          // bubble's bottom edge so revealing it doesn't shift layout.
          !hasAny && "absolute bottom-0 translate-y-1/2",
          !hasAny && alignRight && "right-2",
          !hasAny && !alignRight && "left-2",
        )}
        title="Add reaction"
        aria-label="Add reaction"
      >
        <SmilePlus className="h-3.5 w-3.5" />
      </button>

      {quickOpen && !pickerOpen && (
        <div
          className={cn(
            "absolute bottom-7 z-40 flex items-center gap-0.5 rounded-full border border-border bg-background shadow-md px-1.5 py-1",
            alignRight ? "right-0" : "left-0",
          )}
        >
          {QUICK_REACTIONS.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => toggle(e)}
              disabled={busy}
              className="h-7 w-7 inline-flex items-center justify-center rounded-full hover:bg-muted text-base"
              title={`React ${e}`}
            >
              {e}
            </button>
          ))}
          <div className="h-5 w-px bg-border mx-0.5" aria-hidden />
          <button
            type="button"
            onClick={() => { setQuickOpen(false); setPickerOpen(true); }}
            className="h-7 w-7 inline-flex items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
            title="More"
            aria-label="More emoji"
          >
            <SmilePlus className="h-4 w-4" />
          </button>
        </div>
      )}

      {pickerOpen && (
        <div className={cn("absolute bottom-7 z-50", alignRight ? "right-0" : "left-0")}>
          <Picker
            data={data}
            onEmojiSelect={(emoji: { native: string }) => toggle(emoji.native)}
            theme="light"
            previewPosition="none"
            skinTonePosition="none"
            maxFrequentRows={1}
            perLine={8}
          />
        </div>
      )}
    </div>
  );
}
