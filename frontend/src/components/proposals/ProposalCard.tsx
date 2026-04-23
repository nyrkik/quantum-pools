"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Check, X, Loader2, Pencil } from "lucide-react";

import {
  acceptProposal,
  editAndAcceptProposal,
  rejectProposal,
  type Proposal,
} from "@/lib/proposals";
import { NextStepRenderer } from "@/components/workflow/next-step-registry";
import type { NextStep } from "@/components/workflow/types";

import { JobProposalBody } from "./renderers/JobProposalBody";
import { EstimateProposalBody } from "./renderers/EstimateProposalBody";
import { EquipmentProposalBody } from "./renderers/EquipmentProposalBody";
import { OrgConfigProposalBody } from "./renderers/OrgConfigProposalBody";

export interface ProposalBodyProps {
  payload: Record<string, unknown>;
  /** True when the user is editing before accepting. Renderer should
   *  switch its controls to editable inputs. */
  isEditing?: boolean;
  /** When editing, call with the updated payload on every change. */
  onChange?: (next: Record<string, unknown>) => void;
}

type BodyRenderer = (props: ProposalBodyProps) => ReactNode;

const RENDERERS: Record<string, BodyRenderer> = {
  job: JobProposalBody,
  estimate: EstimateProposalBody,
  equipment_item: EquipmentProposalBody,
  org_config: OrgConfigProposalBody,
};

// Entity types whose renderer supports inline edit mode. Grows as each
// Phase 5+ migration wires its renderer.
const EDITABLE_TYPES = new Set<string>(["estimate"]);

interface ProposalCardProps {
  proposal: Proposal;
  onResolved?: (p: Proposal) => void;
  onError?: (err: Error) => void;
}

function prettifyAgent(agent_type: string): string {
  return agent_type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ProposalCard({
  proposal,
  onResolved,
  onError,
}: ProposalCardProps) {
  const [busy, setBusy] = useState<"accept" | "reject" | "save" | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [rejectPermanent, setRejectPermanent] = useState(false);
  // Phase 4: post-accept inline step — defers onResolved until the
  // user completes or skips the step.
  const [nextStep, setNextStep] = useState<NextStep | null>(null);
  const [pendingResolved, setPendingResolved] = useState<Proposal | null>(null);
  // Inline edit mode — renderer renders Inputs, footer swaps to
  // Save & Accept / Cancel. `editedPayload` is a snapshot the renderer
  // mutates via onChange; Save & Accept commits it via the
  // edit-and-accept endpoint (records the diff as an `agent_corrections`
  // row and closes the proposal in one transaction).
  const [isEditing, setIsEditing] = useState(false);
  const [editedPayload, setEditedPayload] = useState<Record<string, unknown>>(
    proposal.proposed_payload,
  );

  const Renderer = RENDERERS[proposal.entity_type];
  const resolved = proposal.status !== "staged";
  const canEdit = EDITABLE_TYPES.has(proposal.entity_type);

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
      const res = await rejectProposal(proposal.id, {
        permanently: rejectPermanent,
        note: rejectNote.trim() || undefined,
      });
      setRejectOpen(false);
      setRejectNote("");
      setRejectPermanent(false);
      onResolved?.(res.proposal);
    } catch (err) {
      onError?.(err as Error);
    } finally {
      setBusy(null);
    }
  }

  function handleEnterEdit() {
    setEditedPayload(proposal.proposed_payload);
    setIsEditing(true);
  }

  function handleCancelEdit() {
    setIsEditing(false);
    setEditedPayload(proposal.proposed_payload);
  }

  async function handleSaveAndAccept() {
    setBusy("save");
    try {
      const res = await editAndAcceptProposal(proposal.id, editedPayload);
      setIsEditing(false);
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

  return (
    <Card className={`shadow-sm border-l-4 ${isEditing ? "border-amber-400" : "border-primary"}`}>
      <div className="flex items-center justify-between gap-2 bg-primary/10 px-4 py-2 border-b">
        <div className="flex items-center gap-2 text-xs">
          <Badge variant="outline" className="capitalize">
            {prettifyAgent(proposal.agent_type)}
          </Badge>
          <span className="text-muted-foreground capitalize">
            proposes: {proposal.entity_type.replace(/_/g, " ")}
          </span>
          {proposal.confidence != null && (
            <Badge variant="secondary" className="font-mono text-[10px]">
              {(proposal.confidence * 100).toFixed(0)}%
            </Badge>
          )}
        </div>
        {resolved && (
          <Badge variant="outline" className="capitalize text-xs">
            {proposal.status}
          </Badge>
        )}
      </div>

      <div className="p-4">
        {Renderer ? (
          <Renderer
            payload={isEditing ? editedPayload : proposal.proposed_payload}
            isEditing={isEditing}
            onChange={isEditing ? setEditedPayload : undefined}
          />
        ) : (
          <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
            {JSON.stringify(proposal.proposed_payload, null, 2)}
          </pre>
        )}
      </div>

      {nextStep && (
        <div className="px-4 pb-4">
          <NextStepRenderer step={nextStep} onDone={handleStepDone} />
        </div>
      )}

      {!resolved && !nextStep && !isEditing && (
        <div className="flex items-center gap-2 justify-end px-4 py-3 border-t bg-muted/30">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleEnterEdit}
            disabled={!canEdit || busy !== null}
            title={
              canEdit
                ? "Edit the proposal before accepting"
                : "Inline editing not available for this proposal type"
            }
          >
            <Pencil className="h-3.5 w-3.5 mr-1" />
            Edit & Accept
          </Button>

          <AlertDialog open={rejectOpen} onOpenChange={setRejectOpen}>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" disabled={busy !== null}>
                <X className="h-4 w-4 mr-1 text-destructive" />
                Reject
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reject proposal?</AlertDialogTitle>
                <AlertDialogDescription>
                  The AI agent will learn from this rejection.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <div className="space-y-3 py-2">
                <div className="flex items-start gap-2">
                  <Checkbox
                    id="reject-permanent"
                    checked={rejectPermanent}
                    onCheckedChange={(v) => setRejectPermanent(v === true)}
                  />
                  <Label htmlFor="reject-permanent" className="text-sm font-normal leading-tight">
                    Never propose this pattern again
                    <div className="text-xs text-muted-foreground mt-1">
                      Adds a strong lesson for the agent — use when the
                      proposal category itself is wrong for this org.
                    </div>
                  </Label>
                </div>
                <div>
                  <Label htmlFor="reject-note" className="text-sm">
                    Note (optional)
                  </Label>
                  <Textarea
                    id="reject-note"
                    value={rejectNote}
                    onChange={(e) => setRejectNote(e.target.value)}
                    placeholder="Why is this wrong? (helps the agent learn)"
                    className="mt-1 text-sm"
                    rows={2}
                  />
                </div>
              </div>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={busy !== null}>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleReject}
                  disabled={busy !== null}
                >
                  {busy === "reject" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "Reject"
                  )}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleAccept}
            disabled={busy !== null}
          >
            {busy === "accept" ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : (
              <Check className="h-4 w-4 mr-1 text-green-600" />
            )}
            Accept
          </Button>
        </div>
      )}

      {isEditing && (
        <div className="flex items-center gap-2 justify-end px-4 py-3 border-t bg-amber-50 dark:bg-amber-950/30">
          <span className="text-xs text-amber-700 dark:text-amber-400 mr-auto">
            Editing — save commits as your version with correction recorded
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCancelEdit}
            disabled={busy !== null}
          >
            Cancel
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSaveAndAccept}
            disabled={busy !== null}
          >
            {busy === "save" ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : (
              <Check className="h-4 w-4 mr-1 text-green-600" />
            )}
            Save & Accept
          </Button>
        </div>
      )}
    </Card>
  );
}
