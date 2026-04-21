"use client";

/**
 * VoiceDictationButton — Phase 1 voice input (FB-29).
 *
 * Browser-native Web Speech API push-to-talk. Press the mic to start
 * capturing; press again to stop. Final transcripts stream out via
 * `onTranscript`; interim partials optionally via `onInterim` so the
 * caller can render a live preview while the user is speaking.
 *
 * Feature-detects `SpeechRecognition` / `webkitSpeechRecognition` and
 * renders null when unsupported (Firefox) — don't confuse the user
 * with a dead button. Emits `voice.dictated` on successful stop with
 * `{surface, duration_ms, char_count, language}` — NO transcript
 * content in the event, by design.
 *
 * Spec: docs/voice-integration-plan.md §3.
 */

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";

import { events } from "@/lib/events";
import { cn } from "@/lib/utils";

// The Web Speech API types aren't in @types/dom as of this writing;
// define the minimal surface we use without pulling in a polyfill.
type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionEventLike = {
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

function resolveCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

/**
 * Emit `voice.dictated` on a completed dictation. Intentionally no
 * transcript content in the payload — privacy by design, same rule
 * as every other platform event.
 */
function emitDictated(
  surface: VoiceDictationButtonProps["surface"],
  startedAt: number,
  charCount: number,
  language: string,
) {
  events.emit("voice.dictated", {
    level: "user_action",
    payload: {
      surface,
      duration_ms: Math.max(0, Date.now() - startedAt),
      char_count: charCount,
      language,
    },
  });
}

export interface VoiceDictationButtonProps {
  /** Called with the final transcript each time recognition produces
   * a complete phrase. Caller is responsible for appending / replacing
   * as appropriate for their field. */
  onTranscript: (text: string) => void;
  /** Optional interim partial — good for showing a live preview under
   * the input while the user is still speaking. */
  onInterim?: (text: string) => void;
  /** BCP-47 language tag; defaults to en-US. */
  lang?: string;
  /** Where the button is mounted — fed into the `voice.dictated`
   * event payload so adoption can be measured per surface. */
  surface:
    | "deepblue_chat"
    | "email_reply"
    | "email_compose"
    | "job_notes"
    | "visit_notes"
    | "other";
  className?: string;
  size?: "sm" | "md";
  disabled?: boolean;
  /** When true, keep recognizing until stop is called. Default true —
   * matches dictation expectation. */
  continuous?: boolean;
}

export function VoiceDictationButton({
  onTranscript,
  onInterim,
  lang = "en-US",
  surface,
  className,
  size = "sm",
  disabled,
  continuous = true,
}: VoiceDictationButtonProps) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const startedAtRef = useRef<number>(0);
  const finalCharsRef = useRef<number>(0);

  // Detect browser support once on mount. Defer to an effect so the
  // SSR render returns a stable null and we don't hydrate-mismatch.
  useEffect(() => {
    setSupported(resolveCtor() !== null);
  }, []);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop();
      } catch {
        /* ignore */
      }
    };
  }, []);

  if (supported === false) {
    // Firefox or any browser without Web Speech — render nothing. No
    // tooltip, no error, no dead button. The user doesn't need to
    // learn their browser isn't supported; they just don't see a mic.
    return null;
  }
  if (supported === null) {
    // Pre-mount / SSR — render a hidden placeholder with the same
    // dimensions so layout doesn't shift when support is detected.
    return (
      <button
        type="button"
        disabled
        className={cn(
          "inline-flex items-center justify-center rounded-md text-muted-foreground",
          size === "sm" ? "h-7 w-7" : "h-9 w-9",
          className,
        )}
        aria-hidden
      />
    );
  }

  const start = () => {
    const Ctor = resolveCtor();
    if (!Ctor) return;
    try {
      const rec = new Ctor();
      rec.lang = lang;
      rec.continuous = continuous;
      rec.interimResults = !!onInterim;
      rec.onresult = (ev) => {
        let interim = "";
        for (let i = 0; i < ev.results.length; i++) {
          const r = ev.results[i];
          const transcript = r[0].transcript;
          if (r.isFinal) {
            finalCharsRef.current += transcript.length;
            onTranscript(transcript);
          } else {
            interim += transcript;
          }
        }
        if (interim && onInterim) onInterim(interim);
      };
      rec.onerror = (ev) => {
        setError(ev.error || "unknown");
        setListening(false);
      };
      rec.onend = () => {
        setListening(false);
        emitDictated(surface, startedAtRef.current, finalCharsRef.current, lang);
        finalCharsRef.current = 0;
      };
      recognitionRef.current = rec;
      startedAtRef.current = Date.now();
      finalCharsRef.current = 0;
      setError(null);
      setListening(true);
      rec.start();
    } catch (e) {
      setError(e instanceof Error ? e.message : "start_failed");
      setListening(false);
    }
  };

  const stop = () => {
    try {
      recognitionRef.current?.stop();
    } catch {
      /* onend fires regardless */
    }
  };

  const handleClick = () => {
    if (listening) stop();
    else start();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      aria-label={listening ? "Stop dictation" : "Start voice dictation"}
      aria-pressed={listening}
      title={
        error === "not-allowed"
          ? "Microphone blocked — enable in browser settings"
          : listening
          ? "Stop dictation"
          : "Dictate"
      }
      className={cn(
        "inline-flex items-center justify-center rounded-md transition-colors",
        size === "sm" ? "h-7 w-7" : "h-9 w-9",
        listening
          ? "text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-950/30 dark:hover:bg-red-950/50 animate-pulse"
          : "text-muted-foreground hover:bg-muted",
        error ? "text-destructive" : "",
        className,
      )}
    >
      {error === "not-allowed" ? (
        <MicOff className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      ) : (
        <Mic className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      )}
    </button>
  );
}
