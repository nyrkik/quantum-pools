/**
 * Tab-scoped session ID for event correlation.
 *
 * Each browser tab gets its own UUID that persists for the life of the tab
 * (via sessionStorage) but is distinct across tabs. The backend emits with
 * this ID on every frontend-originated event via the X-Session-Id header,
 * so Sonar can reconstruct per-tab activity timelines.
 *
 * See docs/event-taxonomy.md §7 and docs/ai-platform-phase-1.md §7.1.
 */

const KEY = "qp_session_id";

export function getSessionId(): string {
  if (typeof window === "undefined") {
    // Server-side rendering — no session concept. Caller should not hit
    // this path for event emission (SSR doesn't emit).
    return "";
  }
  let sid = window.sessionStorage.getItem(KEY);
  if (!sid) {
    sid =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : _fallbackUUID();
    window.sessionStorage.setItem(KEY, sid);
  }
  return sid;
}

function _fallbackUUID(): string {
  // Only used if crypto.randomUUID is unavailable (very old browsers).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
