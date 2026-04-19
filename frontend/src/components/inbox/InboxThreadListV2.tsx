"use client";

/**
 * Phase 3 — Inbox V2 list.
 *
 * Replaces the column-based table with a card-per-thread layout.
 * Each card has:
 *   Left: customer name, subject, badges, time/count
 *   Right: InboxSummaryCard (AI summary + inline proposals)
 *
 * Rendered only when `org.inbox_v2_enabled === true`. Parent (inbox
 * page) reads the flag from auth context and picks between the v1
 * `InboxThreadTable` and this component.
 */

import { useEffect, useState } from "react";
import { formatTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

import { StatusBadge, CategoryBadge } from "@/components/inbox/inbox-badges";
import { InboxSummaryCard, type InboxSummaryPayload } from "./InboxSummaryCard";
import type { Proposal } from "@/lib/proposals";
import { api } from "@/lib/api";

import type { Thread } from "@/types/agent";

interface Props {
  threads: Thread[];
  loading: boolean;
  selectedThreadId?: string | null;
  onSelectThread: (id: string) => void;
}

export function InboxThreadListV2({ threads, loading, selectedThreadId, onSelectThread }: Props) {
  // Hydrate staged proposals referenced by thread.ai_summary_payload.proposal_ids.
  // Keyed by thread id so each row renders only its own proposals.
  const [proposalsByThread, setProposalsByThread] = useState<Record<string, Proposal[]>>({});

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
    // Pull each batch in parallel; cap to avoid thundering herd on large pages.
    let cancelled = false;
    (async () => {
      const next: Record<string, Proposal[]> = {};
      await Promise.all(
        wanted.map(async ({ threadId, ids }) => {
          try {
            const fetched = await Promise.all(
              ids.map((pid) => api.get<Proposal>(`/v1/proposals/${pid}`).catch(() => null)),
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
    <div className="space-y-2">
      {threads.map((t) => (
        <Card
          key={t.id}
          className={`shadow-sm cursor-pointer transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 ${
            selectedThreadId === t.id ? "ring-2 ring-primary" : ""
          } ${t.is_unread ? "border-l-4 border-primary" : ""}`}
          onClick={() => onSelectThread(t.id)}
        >
          <div className="grid md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] gap-3 p-3">
            {/* Left column: identity + badges + meta */}
            <div className="min-w-0 space-y-1">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium truncate">
                    {t.customer_name || t.contact_name || t.contact_email}
                  </div>
                  <div className="text-sm text-muted-foreground truncate">
                    {t.subject || "(no subject)"}
                  </div>
                </div>
                <div className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatTime(t.last_message_at)}
                </div>
              </div>

              <div className="flex flex-wrap gap-1 items-center pt-0.5">
                {t.sender_tag && (
                  <Badge variant="outline" className="text-[10px] capitalize">
                    {t.sender_tag}
                  </Badge>
                )}
                {t.category && <CategoryBadge category={t.category} />}
                <StatusBadge status={t.status} />
                <span className="text-xs text-muted-foreground ml-1">
                  {t.message_count} msg{t.message_count === 1 ? "" : "s"}
                </span>
              </div>
            </div>

            {/* Right column: AI summary + inline proposals */}
            <div className="min-w-0">
              <InboxSummaryCard
                payload={
                  (t.ai_summary_payload as InboxSummaryPayload | null | undefined) ?? null
                }
                proposals={proposalsByThread[t.id] ?? []}
                fallbackSnippet={t.last_snippet ?? undefined}
              />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
