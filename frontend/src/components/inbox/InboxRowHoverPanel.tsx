"use client";

/**
 * Phase 3 — hover/focus detail panel for an inbox row.
 *
 * Shows the full summary payload in a uniform shape:
 *   - Customer / subject header
 *   - Ask (if present)
 *   - Status
 *   - Open items
 *   - Red flags (if present)
 *   - Linked refs (clickable chips → /customers/:id, /cases/:id, /invoices/:id)
 *   - Inline ProposalCardMini list
 *
 * Uniform across all rows: same shape, same section order. Absent
 * sections just collapse; the skeleton never changes.
 */

import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";

import type { Proposal } from "@/lib/proposals";
import { ProposalCardMini } from "@/components/proposals/ProposalCardMini";
import type { InboxSummaryPayload } from "./InboxSummaryCard";

interface Props {
  payload: InboxSummaryPayload | null;
  subject: string | null;
  customerName: string | null;
  contactEmail: string;
  proposals: Proposal[];
  fallbackSnippet: string | null;
  onProposalResolved?: (p: Proposal) => void;
}

// Known linkable types. Unknown types render as non-interactive chips.
const LINK_ROUTE: Record<string, (id: string) => string> = {
  customer: (id) => `/customers/${id}`,
  case: (id) => `/cases/${id}`,
  invoice: (id) => `/invoices/${id}`,
};

export function InboxRowHoverPanel({
  payload,
  subject,
  customerName,
  contactEmail,
  proposals,
  fallbackSnippet,
  onProposalResolved,
}: Props) {
  const router = useRouter();
  const stagedProposals = proposals.filter((p) => p.status === "staged");

  return (
    <div className="text-sm space-y-3">
      {/* Header: customer + subject (the row only shows customer name + AI synthesis,
          so the hover is where the subject lives) */}
      <div className="border-b pb-2">
        <div className="font-semibold text-sm truncate">
          {customerName || contactEmail}
        </div>
        {subject && (
          <div className="text-xs text-muted-foreground truncate">{subject}</div>
        )}
      </div>

      {/* Ask */}
      {payload?.ask && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Ask
          </div>
          <div className="text-sm">{payload.ask}</div>
        </div>
      )}

      {/* Status */}
      {payload && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Status
          </div>
          <div className="text-sm">{payload.state}</div>
        </div>
      )}

      {/* Open items */}
      {payload && payload.open_items.length > 0 && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Open items
          </div>
          <ul className="text-sm list-disc list-inside mt-0.5 space-y-0.5">
            {payload.open_items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Red flags */}
      {payload && payload.red_flags.length > 0 && (
        <div className="flex items-start gap-1.5 rounded bg-amber-50 dark:bg-amber-950/30 px-2 py-1.5">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-xs text-amber-900 dark:text-amber-200 space-y-0.5">
            {payload.red_flags.map((flag, i) => (
              <div key={i}>{flag}</div>
            ))}
          </div>
        </div>
      )}

      {/* Linked refs — clickable when type is known */}
      {payload && payload.linked_refs.length > 0 && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">
            Linked
          </div>
          <div className="flex flex-wrap gap-1">
            {payload.linked_refs.map((ref, i) => {
              const routeFn = LINK_ROUTE[ref.type];
              const label = ref.label ?? ref.id.slice(0, 8);
              const className = "text-[10px] capitalize";
              if (!routeFn) {
                return (
                  <Badge key={i} variant="outline" className={className}>
                    {ref.type}: {label}
                  </Badge>
                );
              }
              return (
                <Badge
                  key={i}
                  variant="outline"
                  className={`${className} cursor-pointer hover:bg-accent`}
                  onClick={(e) => {
                    e.stopPropagation();
                    router.push(routeFn(ref.id));
                  }}
                >
                  {ref.type}: {label}
                </Badge>
              );
            })}
          </div>
        </div>
      )}

      {/* Staged proposals */}
      {stagedProposals.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Proposals
          </div>
          {stagedProposals.map((p) => (
            <ProposalCardMini
              key={p.id}
              proposal={p}
              onResolved={onProposalResolved}
            />
          ))}
        </div>
      )}

      {/* Fallback when there's no summary at all */}
      {!payload && fallbackSnippet && (
        <div className="text-xs text-muted-foreground line-clamp-4">
          {fallbackSnippet}
        </div>
      )}

      {!payload && !fallbackSnippet && (
        <div className="text-xs text-muted-foreground italic">
          Awaiting summary…
        </div>
      )}
    </div>
  );
}
