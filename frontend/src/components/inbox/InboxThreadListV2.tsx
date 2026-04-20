"use client";

/**
 * Phase 3 — Inbox V2 list.
 *
 * Each thread is a compact card (~3-5 rows) with identity on top and
 * an AI-generated bullet digest as the body. The identity chunk
 * (customer name + address) is shown ONCE — the summarizer prompt is
 * told to never repeat either, so bullets read clean:
 *     Marty Reed                                        12:34p
 *     7210 Crocker Road
 *     • Filter cleaning — Approved
 *     • Pool sweep tail — Approved
 *     [Client • Category • Status]
 *
 * Hover/focus reveals the full payload (ask, red flags, linked refs,
 * proposals) in InboxRowHoverPanel.
 *
 * Design rules:
 *   - `has_pending` → amber left border (pending reply from us).
 *   - `is_unread` → bold customer name + blue unread dot.
 *   - Click opens the existing reading pane — unchanged from v1.
 */

import { useEffect, useState } from "react";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertTriangle, Lock, Info } from "lucide-react";

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
  groupByClient?: boolean;
}

/** Group threads by customer (or sender email when unmatched). Pending
 *  groups surface first, then alphabetical. Mirrors the v1 table's rule. */
function groupThreadsByClient(threads: Thread[]): { label: string; threads: Thread[] }[] {
  const byClient = new Map<string, Thread[]>();
  for (const t of threads) {
    const key = t.customer_name || t.contact_email;
    if (!byClient.has(key)) byClient.set(key, []);
    byClient.get(key)!.push(t);
  }
  return [...byClient.entries()]
    .sort((a, b) => {
      const aPending = a[1].some((t) => t.has_pending);
      const bPending = b[1].some((t) => t.has_pending);
      if (aPending !== bPending) return aPending ? -1 : 1;
      return a[0].localeCompare(b[0]);
    })
    .map(([label, items]) => ({ label, threads: items }));
}

/** Body content for a row. Returns either `bullets` (primary display)
 *  or `line` (fallback single-line gist from state/ask/snippet/subject).
 *  Never both. */
function rowBody(t: Thread): { bullets: string[] } | { line: string } {
  const p = t.ai_summary_payload as InboxSummaryPayload | null | undefined;
  if (p && p.version === SUPPORTED_SUMMARY_VERSION) {
    // Primary: the bullet digest — cap at 5 for card height.
    if (p.open_items.length > 0) {
      return { bullets: p.open_items.slice(0, 5) };
    }
    // Fallback order when no bullets: ask, then state, then snippet.
    if (p.ask) return { line: p.ask };
    if (p.state) return { line: p.state };
  }
  if (t.last_snippet) return { line: t.last_snippet };
  if (t.subject) return { line: t.subject };
  return { line: "(no content)" };
}

export function InboxThreadListV2({
  threads,
  loading,
  selectedThreadId,
  onSelectThread,
  groupByClient = false,
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

  function renderRow(t: Thread) {
        const body = rowBody(t);
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

                  <div className="min-w-0 flex-1 grid grid-cols-1 sm:grid-cols-[minmax(0,11rem)_1fr] gap-2 sm:gap-3">
                    {/* Left column: identity (name → address → badges) */}
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center justify-between gap-1.5">
                        <div className="min-w-0 flex items-center gap-1.5">
                          <span
                            className={`truncate text-sm ${
                              t.is_unread ? "font-semibold" : "font-medium"
                            }`}
                            title={t.contact_email}
                          >
                            {t.customer_name || t.contact_name || t.contact_email}
                          </span>
                          {t.visibility_permission && (
                            <Lock
                              className="h-3 w-3 text-muted-foreground shrink-0"
                              aria-label={`Restricted: ${t.visibility_permission}`}
                            />
                          )}
                        </div>
                        {/* Mobile-only: time + info tap-target. On desktop time
                            renders on the right, and hover opens the panel. */}
                        <div className="flex items-center gap-1 sm:hidden shrink-0">
                          <span className="text-xs text-muted-foreground">
                            {formatTime(t.last_message_at)}
                          </span>
                          <Popover>
                            <PopoverTrigger asChild>
                              <button
                                type="button"
                                onClick={(e) => e.stopPropagation()}
                                aria-label="Show summary"
                                className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted"
                              >
                                <Info className="h-3.5 w-3.5" />
                              </button>
                            </PopoverTrigger>
                            <PopoverContent
                              align="end"
                              side="bottom"
                              sideOffset={4}
                              collisionPadding={16}
                              className="w-[22rem] p-4"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <InboxRowHoverPanel
                                payload={hasPayload ? payload : null}
                                subject={t.subject}
                                customerName={t.customer_name}
                                contactPersonName={t.contact_person_name ?? null}
                                contactEmail={t.contact_email}
                                lastMessageAt={t.last_message_at}
                                messageCount={t.message_count}
                                customerAddress={t.customer_address}
                                proposals={proposalsByThread[t.id] ?? []}
                                fallbackSnippet={t.last_snippet}
                              />
                            </PopoverContent>
                          </Popover>
                        </div>
                      </div>
                      {t.customer_name && t.contact_person_name && (
                        <div className="text-xs text-muted-foreground truncate">
                          {t.contact_person_name}
                        </div>
                      )}
                      {t.customer_address && (
                        <div className="text-xs text-muted-foreground truncate">
                          {t.customer_address}
                        </div>
                      )}
                      {/* Badges directly under address */}
                      <div className="flex items-center flex-wrap gap-1 pt-0.5">
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

                    {/* Right column: bullets + time */}
                    <div className="min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex items-start gap-1.5 flex-1">
                          {redFlagCount > 0 && (
                            <AlertTriangle
                              className="h-3.5 w-3.5 text-amber-600 shrink-0 mt-0.5"
                              aria-label={`${redFlagCount} red flag${redFlagCount > 1 ? "s" : ""}`}
                            />
                          )}
                          <div className="min-w-0 flex-1">
                            {"bullets" in body ? (
                              <ul className="space-y-0.5">
                                {body.bullets.map((b, i) => (
                                  <li
                                    key={i}
                                    className="text-sm text-foreground truncate"
                                  >
                                    <span className="text-muted-foreground mr-1.5">
                                      •
                                    </span>
                                    {b}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <div
                                className={`text-sm truncate ${
                                  hasPayload
                                    ? "text-foreground"
                                    : "text-muted-foreground"
                                }`}
                              >
                                {body.line}
                              </div>
                            )}
                            {t.message_count > 1 && (
                              <div className="text-[10px] text-muted-foreground mt-1">
                                {t.message_count} msgs
                              </div>
                            )}
                          </div>
                        </div>
                        <span className="hidden sm:inline text-xs text-muted-foreground whitespace-nowrap shrink-0">
                          {formatTime(t.last_message_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              </HoverCardTrigger>
              <HoverCardContent
                side="bottom"
                align="center"
                sideOffset={4}
                collisionPadding={16}
                className="w-[28rem]"
              >
                <InboxRowHoverPanel
                  payload={hasPayload ? payload : null}
                  subject={t.subject}
                  customerName={t.customer_name}
                  contactPersonName={t.contact_person_name ?? null}
                  contactEmail={t.contact_email}
                  lastMessageAt={t.last_message_at}
                  messageCount={t.message_count}
                  customerAddress={t.customer_address}
                  proposals={proposalsByThread[t.id] ?? []}
                  fallbackSnippet={t.last_snippet}
                />
              </HoverCardContent>
            </HoverCard>
          </li>
        );
  }

  if (groupByClient) {
    const groups = groupThreadsByClient(threads);
    return (
      <div className="space-y-3">
        {groups.map((g) => (
          <ul
            key={g.label}
            className="divide-y rounded-md border bg-background overflow-hidden"
          >
            <li className="bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium uppercase tracking-wide flex items-center justify-between">
              <span className="truncate">{g.label}</span>
              <span className="opacity-70 ml-2 shrink-0">
                {g.threads.length}
              </span>
            </li>
            {g.threads.map((t) => renderRow(t))}
          </ul>
        ))}
      </div>
    );
  }

  return (
    <ul className="divide-y rounded-md border bg-background">
      {threads.map((t) => renderRow(t))}
    </ul>
  );
}
