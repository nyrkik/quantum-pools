"use client";

/**
 * Phase 3 — InboxSummaryCard.
 *
 * Right-side card in the new InboxRowV2 layout. Renders the cached
 * `ai_summary_payload` fields + inline ProposalCardMini[] for any
 * staged proposals from the summarizer.
 *
 * Schema reference: docs/ai-platform-phase-3.md §4 (InboxSummary).
 * The payload may evolve; the `version` field in the payload is how
 * we detect schema mismatches (UI silently falls back to "no summary
 * cached" if version is unexpected).
 */

import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";

import type { Proposal } from "@/lib/proposals";
import { ProposalCardMini } from "@/components/proposals/ProposalCardMini";

const SUPPORTED_VERSION = 1;

interface LinkedRef {
  type: string;            // customer | case | invoice | job
  id: string;
  label?: string | null;
}

export interface InboxSummaryPayload {
  version: number;
  ask: string | null;
  state: string | null;
  open_items: string[];
  red_flags: string[];
  linked_refs: LinkedRef[];
  confidence: number;
  proposal_ids: string[];
}

interface Props {
  payload: InboxSummaryPayload | null;
  proposals?: Proposal[];  // hydrated by the parent from payload.proposal_ids
  fallbackSnippet?: string;
  onProposalResolved?: (p: Proposal) => void;
}

export function InboxSummaryCard({
  payload,
  proposals = [],
  fallbackSnippet,
  onProposalResolved,
}: Props) {
  // Null payload / unsupported version → fall back to the message snippet
  // so the row still says something useful. Matches the "short-thread"
  // behavior from the backend (no summary generated).
  if (!payload || payload.version !== SUPPORTED_VERSION) {
    if (!fallbackSnippet) return null;
    return (
      <div className="text-sm text-muted-foreground line-clamp-2">
        {fallbackSnippet}
      </div>
    );
  }

  const stagedProposals = proposals.filter(
    (p) => p.status === "staged" && payload.proposal_ids.includes(p.id),
  );

  return (
    <div className="space-y-2 text-sm">
      {payload.ask && (
        <div>
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Ask
          </span>
          <div className="text-sm">{payload.ask}</div>
        </div>
      )}

      <div>
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Status
        </span>
        <div className="text-sm">{payload.state}</div>
      </div>

      {payload.open_items.length > 0 && (
        <div>
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Open items
          </span>
          <ul className="text-sm list-disc list-inside space-y-0.5 mt-0.5">
            {payload.open_items.map((item, i) => (
              <li key={i} className="text-sm">{item}</li>
            ))}
          </ul>
        </div>
      )}

      {payload.red_flags.length > 0 && (
        <div className="flex items-start gap-1.5 rounded bg-amber-50 dark:bg-amber-950/30 px-2 py-1.5">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-xs text-amber-900 dark:text-amber-200 space-y-0.5">
            {payload.red_flags.map((flag, i) => (
              <div key={i}>{flag}</div>
            ))}
          </div>
        </div>
      )}

      {payload.linked_refs.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1">
          {payload.linked_refs.map((ref, i) => (
            <Badge key={i} variant="outline" className="text-[10px] capitalize">
              {ref.type}: {ref.label ?? ref.id.slice(0, 8)}
            </Badge>
          ))}
        </div>
      )}

      {stagedProposals.length > 0 && (
        <div className="space-y-1.5 pt-1">
          {stagedProposals.map((p) => (
            <ProposalCardMini
              key={p.id}
              proposal={p}
              onResolved={onProposalResolved}
            />
          ))}
        </div>
      )}
    </div>
  );
}
