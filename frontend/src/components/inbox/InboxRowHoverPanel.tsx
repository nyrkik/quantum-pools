"use client";

/**
 * Phase 3 — hover/focus detail panel for an inbox row.
 *
 * Structured like an email: labeled header block (From / Subject / Date),
 * then clearly sectioned body (Summary, Customer asks, Red flags, Linked,
 * Proposals). Every section is optional — absent sections collapse but
 * the skeleton shape is identical across every thread so the user learns
 * where to look.
 */

import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Mail } from "lucide-react";

import type { Proposal } from "@/lib/proposals";
import { ProposalCardMini } from "@/components/proposals/ProposalCardMini";
import { formatTime } from "@/lib/format";
import type { InboxSummaryPayload } from "./InboxSummaryCard";

interface Props {
  payload: InboxSummaryPayload | null;
  subject: string | null;
  customerName: string | null;
  contactPersonName: string | null;
  contactEmail: string;
  lastMessageAt: string | null;
  messageCount: number;
  customerAddress: string | null;
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

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-1">
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </h3>
      {children}
    </section>
  );
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[4rem_1fr] gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground truncate">{value}</span>
    </div>
  );
}

export function InboxRowHoverPanel({
  payload,
  subject,
  customerName,
  contactPersonName,
  contactEmail,
  lastMessageAt,
  messageCount,
  customerAddress,
  proposals,
  fallbackSnippet,
  onProposalResolved,
}: Props) {
  const router = useRouter();
  const stagedProposals = proposals.filter((p) => p.status === "staged");

  return (
    <div className="text-sm">
      {/* Header — looks like email chrome */}
      <header className="pb-3 mb-3 border-b">
        <div className="flex items-center gap-2 mb-2">
          <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
          <h2 className="font-semibold text-sm truncate">
            {customerName || contactEmail}
          </h2>
        </div>
        <div className="space-y-1">
          <FieldRow
            label="From"
            value={
              contactPersonName ? (
                <>
                  {contactPersonName}{" "}
                  <span className="text-muted-foreground">
                    &lt;{contactEmail}&gt;
                  </span>
                </>
              ) : (
                contactEmail
              )
            }
          />
          {customerAddress && (
            <FieldRow label="Address" value={customerAddress} />
          )}
          <FieldRow label="Subject" value={subject || "(no subject)"} />
          <FieldRow
            label="Date"
            value={
              <>
                {formatTime(lastMessageAt)} • {messageCount} msg
                {messageCount === 1 ? "" : "s"}
              </>
            }
          />
        </div>
      </header>

      {/* Body — each section is independent, clear break between them */}
      <div className="space-y-3">
        {/* Summary bullets (primary content) */}
        {payload && payload.open_items.length > 0 && (
          <Section label="Summary">
            <ul className="space-y-1 text-sm">
              {payload.open_items.map((item, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-muted-foreground">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* State line — only when bullets absent */}
        {payload && payload.open_items.length === 0 && payload.state && (
          <Section label="Summary">
            <p className="text-sm">{payload.state}</p>
          </Section>
        )}

        {/* Customer's explicit question */}
        {payload?.ask && (
          <Section label="Customer asks">
            <p className="text-sm rounded bg-muted/60 px-2.5 py-1.5">
              {payload.ask}
            </p>
          </Section>
        )}

        {/* Red flags — highlighted */}
        {payload && payload.red_flags.length > 0 && (
          <Section label="Red flags">
            <div className="flex items-start gap-2 rounded bg-amber-50 dark:bg-amber-950/30 px-2.5 py-1.5">
              <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
              <ul className="text-xs text-amber-900 dark:text-amber-200 space-y-0.5">
                {payload.red_flags.map((flag, i) => (
                  <li key={i}>{flag}</li>
                ))}
              </ul>
            </div>
          </Section>
        )}

        {/* Linked refs — clickable chips route to entity pages */}
        {payload && payload.linked_refs.length > 0 && (
          <Section label="Linked">
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
          </Section>
        )}

        {/* Staged proposals — inline action cards */}
        {stagedProposals.length > 0 && (
          <Section label="Proposals">
            <div className="space-y-1.5">
              {stagedProposals.map((p) => (
                <ProposalCardMini
                  key={p.id}
                  proposal={p}
                  onResolved={onProposalResolved}
                />
              ))}
            </div>
          </Section>
        )}

        {/* Fallback states when no cached payload */}
        {!payload && fallbackSnippet && (
          <Section label="Preview">
            <p className="text-xs text-muted-foreground line-clamp-4">
              {fallbackSnippet}
            </p>
          </Section>
        )}

        {!payload && !fallbackSnippet && (
          <p className="text-xs text-muted-foreground italic">
            Awaiting summary…
          </p>
        )}
      </div>
    </div>
  );
}
