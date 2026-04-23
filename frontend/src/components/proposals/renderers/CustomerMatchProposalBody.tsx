"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

interface CustomerMatchPayload {
  thread_id?: string;
  candidate_customer_id?: string;
  reason?: string;
  confidence?: "low" | "medium";
  note?: string | null;
}

interface CandidateInfo {
  id: string;
  display_name: string | null;
  email: string | null;
  primary_address: string | null;
}

interface Props {
  payload: Record<string, unknown>;
  // Match suggestions are read-only — no edit mode.
}

/** Fetch the candidate customer's display fields for the card.
 *  Kept local + defensive — renderers shouldn't take the page down on a
 *  lookup failure. */
function useCandidate(customerId?: string): CandidateInfo | null {
  const [info, setInfo] = useState<CandidateInfo | null>(null);
  useEffect(() => {
    if (!customerId) {
      setInfo(null);
      return;
    }
    let alive = true;
    api
      .get<CandidateInfo>(`/v1/customers/${customerId}?fields=display_name,email,primary_address`)
      .then((c) => { if (alive) setInfo(c); })
      .catch(() => { if (alive) setInfo(null); });
    return () => { alive = false; };
  }, [customerId]);
  return info;
}

export function CustomerMatchProposalBody({ payload }: Props) {
  const p = payload as CustomerMatchPayload;
  const candidate = useCandidate(p.candidate_customer_id);
  const confidenceLabel = p.confidence === "medium" ? "Medium confidence" : "Low confidence";
  const confidenceClass =
    p.confidence === "medium"
      ? "border-amber-400 text-amber-700 dark:text-amber-400"
      : "border-slate-300 text-muted-foreground";

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="secondary">Customer Match</Badge>
        <Badge variant="outline" className={confidenceClass}>
          {confidenceLabel}
        </Badge>
      </div>

      <div className="rounded border bg-muted/40 px-3 py-2 space-y-1">
        <div className="text-xs text-muted-foreground uppercase tracking-wide">
          Suggested match
        </div>
        <div className="font-medium">
          {candidate?.display_name || p.candidate_customer_id || "(unknown)"}
        </div>
        {candidate?.email && (
          <div className="text-xs text-muted-foreground truncate">
            {candidate.email}
          </div>
        )}
        {candidate?.primary_address && (
          <div className="text-xs text-muted-foreground truncate">
            {candidate.primary_address}
          </div>
        )}
      </div>

      {p.reason && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">Why:</span> {p.reason}
        </div>
      )}

      {p.note && (
        <div className="text-xs text-muted-foreground italic">
          {p.note}
        </div>
      )}
    </div>
  );
}
