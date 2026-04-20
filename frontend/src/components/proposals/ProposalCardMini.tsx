"use client";

/**
 * Compact variant of ProposalCard for embedding inside an inbox row.
 * No header, no confidence pill, smaller action buttons — everything
 * a user needs to triage in-line without opening the thread.
 *
 * The full ProposalCard still exists and is used by DeepBlue tool
 * cards, proposal admin views, and the expanded inbox row.
 */

import { useState } from "react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Check, X, Loader2 } from "lucide-react";

import {
  acceptProposal,
  rejectProposal,
  type Proposal,
} from "@/lib/proposals";
import { NextStepRenderer } from "@/components/workflow/next-step-registry";
import type { NextStep } from "@/components/workflow/types";

import { JobProposalBody } from "./renderers/JobProposalBody";
import { EstimateProposalBody } from "./renderers/EstimateProposalBody";
import { EquipmentProposalBody } from "./renderers/EquipmentProposalBody";
import { OrgConfigProposalBody } from "./renderers/OrgConfigProposalBody";

type BodyRenderer = (props: { payload: Record<string, unknown> }) => ReactNode;

const RENDERERS: Record<string, BodyRenderer> = {
  job: JobProposalBody,
  estimate: EstimateProposalBody,
  equipment_item: EquipmentProposalBody,
  org_config: OrgConfigProposalBody,
};

interface Props {
  proposal: Proposal;
  onResolved?: (p: Proposal) => void;
  onError?: (err: Error) => void;
}

export function ProposalCardMini({ proposal, onResolved, onError }: Props) {
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  // Phase 4: post-accept inline step. While `nextStep` is non-null the
  // card replaces its own body with the step UI and defers
  // `onResolved` until the user completes or skips the step.
  const [nextStep, setNextStep] = useState<NextStep | null>(null);
  const [pendingResolved, setPendingResolved] = useState<Proposal | null>(null);

  const Renderer = RENDERERS[proposal.entity_type];
  const resolved = proposal.status !== "staged";

  async function handleAccept() {
    setBusy("accept");
    try {
      const res = await acceptProposal(proposal.id);
      if (res.next_step) {
        setPendingResolved(res.proposal);
        setNextStep(res.next_step);
      } else {
        onResolved?.(res.proposal);
      }
    } catch (err) {
      onError?.(err as Error);
    } finally {
      setBusy(null);
    }
  }

  function handleStepDone() {
    const p = pendingResolved;
    setNextStep(null);
    setPendingResolved(null);
    if (p) onResolved?.(p);
  }

  async function handleReject() {
    setBusy("reject");
    try {
      const res = await rejectProposal(proposal.id);
      onResolved?.(res.proposal);
    } catch (err) {
      onError?.(err as Error);
    } finally {
      setBusy(null);
    }
  }

  if (nextStep) {
    return (
      <div className="rounded border bg-background p-2 text-sm">
        <NextStepRenderer step={nextStep} onDone={handleStepDone} />
      </div>
    );
  }

  return (
    <div className="rounded border bg-background px-3 py-2 text-sm flex items-start gap-2">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-1">
          <Badge variant="outline" className="text-[10px] capitalize">
            {proposal.entity_type.replace(/_/g, " ")}
          </Badge>
          {resolved && (
            <Badge variant="secondary" className="text-[10px] capitalize">
              {proposal.status}
            </Badge>
          )}
        </div>
        {Renderer ? (
          <Renderer payload={proposal.proposed_payload} />
        ) : (
          <div className="text-xs text-muted-foreground truncate">
            {Object.keys(proposal.proposed_payload).length} fields
          </div>
        )}
      </div>

      {!resolved && (
        <div className="flex flex-col gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleAccept}
            disabled={busy !== null}
            title="Accept"
          >
            {busy === "accept" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4 text-muted-foreground hover:text-green-600" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleReject}
            disabled={busy !== null}
            title="Reject"
          >
            {busy === "reject" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <X className="h-4 w-4 text-muted-foreground hover:text-destructive" />
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
