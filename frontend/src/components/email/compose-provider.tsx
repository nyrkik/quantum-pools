"use client";

import { createContext, useContext, useState, useCallback, useRef, type ReactNode } from "react";
import { events } from "@/lib/events";

export interface ComposeOptions {
  to?: string;
  customerId?: string;
  customerName?: string;
  subject?: string;
  body?: string;
  jobId?: string;
  caseId?: string;
  onSent?: () => void;
  /** Original AI draft body — if user edits, diff is logged as correction */
  originalDraft?: string;
  originalSubject?: string;
  /** FROM address override (e.g., thread.delivered_to). Shown as info, passed to backend. */
  fromAddress?: string;
}

interface ComposeContextValue {
  isOpen: boolean;
  isMinimized: boolean;
  options: ComposeOptions;
  openCompose: (opts?: ComposeOptions) => void;
  /**
   * Close the compose panel. Emits `compose.discarded` if the user
   * abandoned a non-empty draft. Call this from the Discard button,
   * the X button, or the Minus-then-X flow.
   */
  closeCompose: () => void;
  /**
   * Close the compose panel AFTER a successful send. Does NOT emit
   * discard — the backend fired compose.sent when the message went out.
   * Call this from the Send handler once the server returns success.
   */
  closeComposeAfterSend: () => void;
  toggleMinimize: () => void;
}

const ComposeContext = createContext<ComposeContextValue | null>(null);

export function ComposeProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [options, setOptions] = useState<ComposeOptions>({});
  const openedAtRef = useRef<number | null>(null);

  const openCompose = useCallback((opts?: ComposeOptions) => {
    setOptions(opts || {});
    setIsOpen(true);
    setIsMinimized(false);
    openedAtRef.current = Date.now();

    const refs: Record<string, string> = {};
    if (opts?.customerId) refs.customer_id = opts.customerId;
    if (opts?.caseId) refs.case_id = opts.caseId;
    if (opts?.jobId) refs.job_id = opts.jobId;
    events.emit("compose.opened", {
      level: "user_action",
      entity_refs: refs,
    });
  }, []);

  const closeCompose = useCallback(() => {
    // Only emit discard if the compose was actually open (not a redundant
    // close while already closed).
    if (isOpen && openedAtRef.current !== null) {
      const durationMs = Date.now() - openedAtRef.current;
      events.emit("compose.discarded", {
        level: "user_action",
        payload: { duration_ms_open: durationMs },
      });
    }
    openedAtRef.current = null;
    setIsOpen(false);
    setIsMinimized(false);
    setOptions({});
  }, [isOpen]);

  const closeComposeAfterSend = useCallback(() => {
    // Don't emit discard — the compose.sent event was emitted server-side
    // when the message left the queue. Keep state cleanup only.
    openedAtRef.current = null;
    setIsOpen(false);
    setIsMinimized(false);
    setOptions({});
  }, []);

  const toggleMinimize = useCallback(() => {
    setIsMinimized((prev) => !prev);
  }, []);

  return (
    <ComposeContext.Provider value={{ isOpen, isMinimized, options, openCompose, closeCompose, closeComposeAfterSend, toggleMinimize }}>
      {children}
    </ComposeContext.Provider>
  );
}

export function useCompose(): ComposeContextValue {
  const ctx = useContext(ComposeContext);
  if (!ctx) throw new Error("useCompose must be used within ComposeProvider");
  return ctx;
}
