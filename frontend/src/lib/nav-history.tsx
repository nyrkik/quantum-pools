"use client";

/**
 * NavHistoryProvider — session-scoped navigation stack.
 *
 * Tracks every pathname change inside the dashboard and lets `<BackButton />`
 * resolve "where did the user come from in THIS session" — independent of
 * the browser's native history, which leaks pre-session navigations that
 * aren't meaningful to the current flow.
 *
 * The stack is in-memory only. A full page reload resets it (which is
 * correct — nothing from a prior session is relevant). Opening a link
 * in a new tab gets a fresh empty stack.
 *
 * Usage at the route level:
 *
 *     // app/(dashboard)/layout.tsx
 *     <NavHistoryProvider>{children}</NavHistoryProvider>
 *
 * Usage in a component:
 *
 *     const { peekPrevious } = useNavHistory();
 *     const prev = peekPrevious();  // full "/path?query" or null
 *
 * The typical consumer is `<BackButton />`; most components should use
 * that instead of reading the context directly.
 */

import { createContext, useContext, useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";

interface NavHistoryContextValue {
  /** Returns the full `"/path?query"` of the previous route, or null. */
  peekPrevious: () => string | null;
  /** Pops + returns the previous route, or null. */
  popPrevious: () => string | null;
}

const NavHistoryContext = createContext<NavHistoryContextValue | null>(null);

function buildHref(pathname: string, searchParams: URLSearchParams): string {
  const qs = searchParams.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}

export function NavHistoryProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const stackRef = useRef<string[]>([]);
  const prevRef = useRef<string | null>(null);

  useEffect(() => {
    const href = buildHref(pathname ?? "/", searchParams ?? new URLSearchParams());
    if (prevRef.current && prevRef.current !== href) {
      stackRef.current.push(prevRef.current);
      // Keep the stack from growing unbounded on pathological flows.
      // 50 deep is plenty for anything a user actually does.
      if (stackRef.current.length > 50) {
        stackRef.current.shift();
      }
    }
    prevRef.current = href;
  }, [pathname, searchParams]);

  const value: NavHistoryContextValue = {
    peekPrevious: () => (stackRef.current.length ? stackRef.current[stackRef.current.length - 1] : null),
    popPrevious: () => stackRef.current.pop() ?? null,
  };

  return (
    <NavHistoryContext.Provider value={value}>
      {children}
    </NavHistoryContext.Provider>
  );
}

export function useNavHistory(): NavHistoryContextValue {
  const ctx = useContext(NavHistoryContext);
  if (!ctx) {
    // Outside the provider (e.g. in isolated tests, or pages not nested
    // under the dashboard layout) return no-op peek/pop rather than
    // crashing the component tree.
    return { peekPrevious: () => null, popPrevious: () => null };
  }
  return ctx;
}
