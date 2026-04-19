"use client";

/**
 * Phase 3 — Inbox V2 list.
 *
 * Standardized single-line row: every thread renders with the same
 * skeleton, so the user learns the shape once. Main row content is
 * the AI synthesis (ask → state → top open_item → snippet → subject),
 * not the raw email subject ("Re: Re: Fwd:" is noise). Hover/focus
 * reveals the full summary + staged proposals in a uniform panel.
 *
 * Design rules:
 *   - `has_pending` → amber left border (pending reply from us).
 *   - `is_unread` → bold customer name + blue unread dot.
 *   - Customer name is the primary typography; badges are secondary.
 *   - Click opens the existing reading pane — unchanged from v1.
 *   - Hover/focus opens InboxRowHoverPanel with uniform shape.
 */

import { useEffect, useState } from "react";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertTriangle, Lock } from "lucide-react";

import { formatTime } from "@/lib/format";
import { StatusBadge, CategoryBadge } from "@/components/inbox/inbox-badges";
import { SENDER_TAG_STYLES } from "./contact-learning-modal";
import { InboxRowHoverPanel } from "./InboxRowHoverPanel";
import type { InboxSummaryPayload } from "./InboxSummaryCard";
import type { Proposal } from "@/lib/proposals";
import { api } from "@/lib/api";

import type { Thread } from "@/types/agent";

const SUPPORTED_SUMMARY_VERSION = 1;
const STALE_AFTER_MS = 30 * 60 * 1000;

interface Props {
  threads: Thread[];
  loading: boolean;
  selectedThreadId?: string | null;
  onSelectThread: (id: string) => void;
}

/** Priority-ordered main-row content — the AI synthesis is what the
 *  user reads at a glance, not the email subject. */
function mainRowContent(t: Thread): { text: string; source: string } {
  const p = t.ai_summary_payload as InboxSummaryPayload | null | undefined;
  if (p && p.version === SUPPORTED_SUMMARY_VERSION) {
    if (p.ask) return { text: p.ask, source: "ask" };
    if (p.state) return { text: p.state, source: "state" };
    if (p.open_items.length > 0) return { text: p.open_items[0], source: "open_item" };
  }
  if (t.last_snippet) return { text: t.last_snippet, source: "snippet" };
  if (t.subject) return { text: t.subject, source: "subject" };
  return { text: "(no content)", source: "empty" };
}

export function InboxThreadListV2({
  threads,
  loading,
  selectedThreadId,
  onSelectThread,
}: Props) {
  // Hydrate staged proposals referenced by thread.ai_summary_payload.proposal_ids.
  // Keyed by thread id so each hover renders only its own proposals.
  const [proposalsByThread, setProposalsByThread] = useState<
    Record<string, Proposal[]>
  >({});

  useEffect(() => {
    const wanted: Array<{ threadId: string; ids: string[] }> = [];
    for (const t of threads) {
      const ids = t.ai_summary_payload?.proposal_ids ?? [];
      if (ids.length > 0) wanted.push({ threadId: t.id, ids });
    }
    if (wanted.length === 0) {
      setProposalsByThread({});
      return;
    }
    let cancelled = false;
    (async () => {
      const next: Record<string, Proposal[]> = {};
      await Promise.all(
        wanted.map(async ({ threadId, ids }) => {
          try {
            const fetched = await Promise.all(
              ids.map((pid) =>
                api.get<Proposal>(`/v1/proposals/${pid}`).catch(() => null),
              ),
            );
            next[threadId] = fetched.filter((p): p is Proposal => p !== null);
          } catch {
            next[threadId] = [];
          }
        }),
      );
      if (!cancelled) setProposalsByThread(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [threads]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (threads.length === 0) {
    return (
      <div className="text-center py-12 text-sm text-muted-foreground">
        No threads match this view.
      </div>
    );
  }

  return (
    <ul className="divide-y rounded-md border bg-background">
      {threads.map((t) => {
        const main = mainRowContent(t);
        const isSelected = selectedThreadId === t.id;
        const payload = (t.ai_summary_payload as InboxSummaryPayload | null | undefined) ?? null;
        const hasPayload = !!payload && payload.version === SUPPORTED_SUMMARY_VERSION;
        const redFlagCount = hasPayload ? payload.red_flags.length : 0;
        const stagedCount = (proposalsByThread[t.id] ?? []).filter(
          (p) => p.status === "staged",
        ).length;
        const isStale =
          t.has_pending &&
          t.last_message_at &&
          Date.now() - new Date(t.last_message_at).getTime() > STALE_AFTER_MS;
        const effectiveTag = t.matched_customer_id ? "client" : t.sender_tag;
        const tagStyle = effectiveTag ? SENDER_TAG_STYLES[effectiveTag] : null;

        // Left border — mutually exclusive priority: selected > pending > unread.
        // Selected wins because that's the active focus; pending wins over unread
        // because it's a team action signal, not a read-state signal.
        let borderClass = "border-l-4 border-transparent";
        if (isSelected) borderClass = "border-l-4 border-primary";
        else if (t.has_pending) borderClass = "border-l-4 border-amber-400";
        else if (t.is_unread) borderClass = "border-l-4 border-blue-500";

        return (
          <li key={t.id}>
            <HoverCard openDelay={250} closeDelay={100}>
              <HoverCardTrigger asChild>
                <button
                  type="button"
                  onClick={() => onSelectThread(t.id)}
                  aria-current={isSelected ? "true" : undefined}
                  className={`group w-full text-left px-3 py-2 flex items-start gap-3 transition-colors ${borderClass} ${
                    isSelected
                      ? "bg-blue-50 dark:bg-blue-950/40"
                      : "hover:bg-blue-50 dark:hover:bg-blue-950/30"
                  } focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40`}
                >
                  {/* Unread dot — stays even with the blue left border so the
                      dot signals "new" vs. "open conversation" (left border). */}
                  <div className="pt-1 shrink-0">
                    <span
                      className={`block h-2 w-2 rounded-full ${
                        t.is_unread ? "bg-blue-500" : "bg-transparent"
                      }`}
                      aria-hidden="true"
                    />
                  </div>

                  <div className="min-w-0 flex-1">
                    {/* Top row: customer name + meta chips + time */}
                    <div className="flex items-baseline justify-between gap-2">
                      <div className="min-w-0 flex items-center gap-1.5">
                        <span
                          className={`truncate text-sm ${
                            t.is_unread ? "font-semibold" : "font-medium"
                          }`}
                          title={t.contact_email}
                        >
                          {t.customer_name || t.contact_name || t.contact_email}
                        </span>
                        {t.customer_name && t.contact_person_name && (
                          <span className="text-xs text-muted-foreground truncate">
                            ({t.contact_person_name})
                          </span>
                        )}
                        {t.visibility_permission && (
                          <Lock
                            className="h-3 w-3 text-muted-foreground shrink-0"
                            aria-label={`Restricted: ${t.visibility_permission}`}
                          />
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                        {formatTime(t.last_message_at)}
                      </span>
                    </div>

                    {/* Main synthesis line — the whole point of v2 */}
                    <div className="flex items-center gap-1.5 mt-0.5">
                      {redFlagCount > 0 && (
                        <AlertTriangle
                          className="h-3.5 w-3.5 text-amber-600 shrink-0"
                          aria-label={`${redFlagCount} red flag${redFlagCount > 1 ? "s" : ""}`}
                        />
                      )}
                      <span
                        className={`truncate text-sm ${
                          hasPayload ? "text-foreground" : "text-muted-foreground"
                        }`}
                      >
                        {main.text}
                      </span>
                    </div>

                    {/* Meta row: tag / category / status / counts / stale */}
                    <div className="flex items-center flex-wrap gap-1 mt-1">
                      {effectiveTag && tagStyle && (
                        <span
                          className={`px-1.5 py-0 rounded text-[9px] font-medium ${tagStyle.bg} ${tagStyle.text}`}
                        >
                          {effectiveTag.charAt(0).toUpperCase() +
                            effectiveTag.slice(1)}
                        </span>
                      )}
                      <CategoryBadge category={t.category} />
                      <StatusBadge status={t.status} />
                      {isStale && (
                        <span className="px-1.5 py-0 rounded text-[9px] font-medium bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400">
                          Stale
                        </span>
                      )}
                      {t.message_count > 1 && (
                        <span className="text-[10px] text-muted-foreground">
                          {t.message_count} msgs
                        </span>
                      )}
                      {stagedCount > 0 && (
                        <Badge
                          variant="outline"
                          className="text-[10px] border-primary/40 text-primary"
                        >
                          {stagedCount} proposal{stagedCount > 1 ? "s" : ""}
                        </Badge>
                      )}
                      {t.assigned_to_name && (
                        <Badge variant="secondary" className="text-[10px]">
                          {t.assigned_to_name}
                        </Badge>
                      )}
                    </div>
                  </div>
                </button>
              </HoverCardTrigger>
              <HoverCardContent
                side="right"
                align="start"
                sideOffset={12}
                avoidCollisions={false}
                className="w-[28rem]"
              >
                <InboxRowHoverPanel
                  payload={hasPayload ? payload : null}
                  subject={t.subject}
                  customerName={t.customer_name}
                  contactEmail={t.contact_email}
                  proposals={proposalsByThread[t.id] ?? []}
                  fallbackSnippet={t.last_snippet}
                />
              </HoverCardContent>
            </HoverCard>
          </li>
        );
      })}
    </ul>
  );
}
