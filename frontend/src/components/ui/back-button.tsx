"use client";

/**
 * BackButton — canonical "Back" affordance for pages under the dashboard.
 *
 * Resolution order for where clicking goes:
 *   1. `?from=<path>` query param on the current URL (explicit override
 *      from the caller that navigated here).
 *   2. `usePreviousRoute()` from NavHistoryProvider (session-scoped stack).
 *   3. `router.back()` — browser history. Soft fallback; may leak
 *      pre-session navigations but that's better than dumping the user
 *      on the fallback list if history is intact.
 *   4. `fallback` prop — hardcoded safety net.
 *
 * Always renders the same shape (ghost variant, `ArrowLeft` icon) so
 * every page has the same back affordance. Callers pass the fallback
 * destination; everything else is handled here.
 */

import { ArrowLeft } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useNavHistory } from "@/lib/nav-history";

export interface BackButtonProps {
  /** Hardcoded safety-net destination when history + from are unavailable. */
  fallback: string;
  /** Label shown next to the icon. Empty string = icon-only. Defaults to "Back". */
  label?: string;
  /** Override button size. Defaults to "sm" when labeled, "icon" when not. */
  size?: "sm" | "icon" | "default";
  className?: string;
}

export function BackButton({
  fallback,
  label = "Back",
  size,
  className,
}: BackButtonProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { popPrevious } = useNavHistory();

  const iconOnly = !label;
  const resolvedSize = size ?? (iconOnly ? "icon" : "sm");

  const handleClick = () => {
    const fromParam = searchParams?.get("from");
    if (fromParam) {
      router.push(fromParam);
      return;
    }
    const prev = popPrevious();
    if (prev) {
      router.push(prev);
      return;
    }
    // Browser history — fine when intact, no-op when the page was
    // opened directly (the fallback below covers that).
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
      return;
    }
    router.push(fallback);
  };

  return (
    <Button
      variant="ghost"
      size={resolvedSize}
      className={className}
      onClick={handleClick}
      aria-label={iconOnly ? "Back" : undefined}
    >
      <ArrowLeft className={iconOnly ? "h-4 w-4" : "mr-2 h-4 w-4"} />
      {label}
    </Button>
  );
}
