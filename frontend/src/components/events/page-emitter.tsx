"use client";

/**
 * Route-change emitter — fires `page.viewed` on every navigation and
 * `page.exited` with dwell_ms for the 10 surfaces the spec flags as
 * worth dwell-tracking (docs/event-taxonomy.md §8.11).
 *
 * Mount this once under (dashboard) — it listens to `usePathname()` and
 * tracks entry/exit for each route segment.
 *
 * Dwell-tracked surfaces: if the user spends 3 minutes on the inbox and
 * 5 seconds on a settings page, we want to know — those two are very
 * different engagement signals. Non-dwell-tracked pages still emit
 * `page.viewed` but not `page.exited`; the event stream doesn't need
 * every idle minute on the login page.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { events } from "@/lib/events";

// The 10 key surfaces that get dwell-time tracking.
// Match any path that starts with these prefixes.
const DWELL_TRACKED_PREFIXES = [
  "/inbox",
  "/cases/",
  "/customers/",
  "/invoices/",
  "/estimates/",
  "/jobs/",
  "/settings",
  "/profitability",
  "/deepblue",
  "/satellite",
];

function isDwellTracked(path: string): boolean {
  return DWELL_TRACKED_PREFIXES.some((prefix) => path.startsWith(prefix));
}

/** Convert a specific path to a normalized route template for analytics.
 *  /customers/abc123 → /customers/[id]
 *  /cases/xyz-789/jobs → /cases/[id]/jobs
 *  Keeps the path distinctive without exploding cardinality into
 *  per-entity rows. Raw path still goes in the payload for specificity. */
function normalizeRouteTemplate(path: string): string {
  // Replace UUIDs and short IDs in path segments with [id]
  return path.replace(
    /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
    "/[id]",
  );
}

export function PageEmitter() {
  const pathname = usePathname();
  const currentRef = useRef<{ path: string; enteredAt: number } | null>(null);

  useEffect(() => {
    if (!pathname) return;

    // Emit page.exited for the PREVIOUS page, if it was dwell-tracked.
    const prev = currentRef.current;
    if (prev && prev.path !== pathname && isDwellTracked(prev.path)) {
      const dwellMs = Date.now() - prev.enteredAt;
      events.emit("page.exited", {
        level: "user_action",
        payload: {
          path: normalizeRouteTemplate(prev.path),
          raw_path: prev.path,
          dwell_ms: dwellMs,
        },
      });
    }

    // Emit page.viewed for the CURRENT page.
    events.emit("page.viewed", {
      level: "user_action",
      payload: {
        path: normalizeRouteTemplate(pathname),
        raw_path: pathname,
      },
    });

    currentRef.current = { path: pathname, enteredAt: Date.now() };

    // On unmount (tab close, SPA logout-redirect), emit final page.exited
    // if on a dwell-tracked surface.
    return () => {
      const state = currentRef.current;
      if (state && state.path === pathname && isDwellTracked(pathname)) {
        const dwellMs = Date.now() - state.enteredAt;
        events.emit("page.exited", {
          level: "user_action",
          payload: {
            path: normalizeRouteTemplate(pathname),
            raw_path: pathname,
            dwell_ms: dwellMs,
          },
        });
      }
    };
  }, [pathname]);

  return null;
}
