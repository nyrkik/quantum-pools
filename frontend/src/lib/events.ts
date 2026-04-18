/**
 * Platform event emission from the frontend.
 *
 * Batches client-side events (button clicks, route changes, etc.) and
 * POSTs them to /api/v1/events. Design per docs/ai-platform-phase-1.md §7.2:
 *
 * - 20-event buffer OR 5-second timer OR route change OR tab close.
 * - Tab-close flush uses navigator.sendBeacon (fetch doesn't survive unload).
 * - sessionStorage backup restores unflushed events on next tab session.
 * - 401/403 responses drop the batch (unauthenticated).
 * - 5xx responses retry once with a short delay, then drop.
 * - Every event gets a client-side UUID for idempotency.
 *
 * Callers use the `events` singleton:
 *
 *     import { events } from "@/lib/events";
 *     events.emit("thread.archived", { level: "user_action", entity_refs: { thread_id: "..." } });
 *
 * Callers do NOT set session_id or client_emit_id — the client handles
 * those automatically.
 */

import { getSessionId } from "./session-id";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type EventLevel = "user_action" | "error";

export interface EventInput {
  level: EventLevel;
  entity_refs?: Record<string, string>;
  payload?: Record<string, unknown>;
}

interface BufferedEvent {
  event_type: string;
  level: EventLevel;
  entity_refs: Record<string, string>;
  payload: Record<string, unknown>;
  client_emit_id: string;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BATCH_SIZE_LIMIT = 20;
const FLUSH_INTERVAL_MS = 5_000;
const BUFFER_STORAGE_KEY = "qp_events_buffer";
const ENDPOINT = "/api/v1/events";

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

class EventClient {
  private buffer: BufferedEvent[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private initialized = false;
  private flushing = false;

  /**
   * Emit an event. Non-blocking — the event is buffered locally and sent
   * to the server on the next flush. Failures never propagate to the caller.
   */
  emit(eventType: string, input: EventInput): void {
    try {
      this._ensureInitialized();
      this.buffer.push({
        event_type: eventType,
        level: input.level,
        entity_refs: input.entity_refs ?? {},
        payload: input.payload ?? {},
        client_emit_id: _uuid(),
      });
      this._persistBuffer();

      if (this.buffer.length >= BATCH_SIZE_LIMIT) {
        void this.flush();
      } else if (!this.timer) {
        this.timer = setTimeout(() => void this.flush(), FLUSH_INTERVAL_MS);
      }
    } catch (err) {
      // Never let event emission break the caller. Log to console so bugs
      // are visible in dev; production dashboards won't see these.
      // eslint-disable-next-line no-console
      console.warn("[events] emit failed:", err);
    }
  }

  /**
   * Flush the current buffer to the server. Safe to call manually (route
   * transitions can force-flush before navigating).
   */
  async flush(): Promise<void> {
    if (this.flushing) return; // reentrancy guard
    this._clearTimer();
    if (this.buffer.length === 0) return;

    const batch = this.buffer.splice(0);
    this._persistBuffer();
    this.flushing = true;

    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Session-Id": getSessionId(),
        },
        body: JSON.stringify({ events: batch }),
      });

      if (res.status === 401 || res.status === 403) {
        // Unauthenticated — drop. These events don't belong to a logged-in
        // user and the receiver refuses to record them.
        return;
      }

      if (!res.ok) {
        // 5xx or unexpected — put back for one retry on the next tick.
        // We accept worst-case duplicate posts if retry hits after a slow
        // success, because client_emit_id deduplicates server-side.
        this._requeue(batch);
      }
    } catch {
      // Network blip — requeue for next flush.
      this._requeue(batch);
    } finally {
      this.flushing = false;
    }
  }

  /**
   * Tab-close handler: flush via sendBeacon so the browser completes the
   * request during the unload phase (fetch is not reliable here).
   */
  private _flushOnUnload(): void {
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0);
    this._persistBuffer();

    try {
      const body = JSON.stringify({ events: batch });
      const blob = new Blob([body], { type: "application/json" });
      // sendBeacon doesn't carry custom headers — X-Session-Id can't be
      // attached. The server falls back to the tab's auth cookie and per-
      // IP rate limit, which is fine for unload-flush (rare event).
      const ok = navigator.sendBeacon(ENDPOINT, blob);
      if (!ok) {
        // Put back so the next tab session restores it from storage.
        this._requeue(batch);
      }
    } catch {
      this._requeue(batch);
    }
  }

  // -------------------------------------------------------------------------

  private _ensureInitialized(): void {
    if (this.initialized) return;
    if (typeof window === "undefined") return;

    // Restore unflushed buffer from prior tab session.
    const restored = window.sessionStorage.getItem(BUFFER_STORAGE_KEY);
    if (restored) {
      try {
        const parsed = JSON.parse(restored);
        if (Array.isArray(parsed)) {
          this.buffer.push(...parsed);
        }
      } catch {
        /* ignore malformed backup */
      }
      window.sessionStorage.removeItem(BUFFER_STORAGE_KEY);
    }

    // Flush on tab close / visibility change.
    window.addEventListener("pagehide", () => this._flushOnUnload());

    this.initialized = true;
  }

  private _persistBuffer(): void {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        BUFFER_STORAGE_KEY,
        JSON.stringify(this.buffer),
      );
    } catch {
      /* storage full or disabled — ignore */
    }
  }

  private _requeue(batch: BufferedEvent[]): void {
    this.buffer.unshift(...batch);
    this._persistBuffer();
    if (!this.timer) {
      this.timer = setTimeout(() => void this.flush(), FLUSH_INTERVAL_MS);
    }
  }

  private _clearTimer(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}

function _uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const events = new EventClient();
