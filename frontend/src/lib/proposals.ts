"use client";

/**
 * Proposals API client — Phase 2 Step 8.
 *
 * Thin wrapper over ApiClient that talks to /api/v1/proposals/*.
 * ProposalCard consumes these; admin consoles consume /admin/platform/proposals.
 */

import { api } from "./api";

import type { NextStep } from "@/components/workflow/types";

export type ProposalStatus =
  | "staged"
  | "accepted"
  | "edited"
  | "rejected"
  | "expired"
  | "superseded";

export interface Proposal {
  id: string;
  organization_id: string;
  agent_type: string;
  entity_type: string;
  source_type: string;
  source_id: string | null;
  proposed_payload: Record<string, unknown>;
  confidence: number | null;
  /** Optional natural-language summary the staging agent supplied. Phase
   *  6 workflow_observer encodes the detector_id as a leading
   *  `[detector_id]` prefix so the dashboard widget's "Never suggest
   *  this" can resolve which detector to mute. */
  input_context?: string | null;
  status: ProposalStatus;
  rejected_permanently: boolean;
  superseded_by_id: string | null;
  outcome_entity_type: string | null;
  outcome_entity_id: string | null;
  user_delta: Array<Record<string, unknown>> | null;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResolveResponse {
  proposal: Proposal;
  outcome_entity_id: string | null;
  outcome_entity_type: string | null;
  conflict: boolean;
  /** Phase 4: post-creation handler step. Null when the org has no
   * handler configured for this entity_type, when no handler entry
   * type matches, or when handler resolution failed soft. */
  next_step?: NextStep | null;
}

export interface RejectResponse {
  proposal: Proposal;
}

export async function getProposal(id: string): Promise<Proposal> {
  return api.get<Proposal>(`/v1/proposals/${id}`);
}

/** List org-scoped proposals. Used by the /inbox/matches review queue
 *  and the Phase 6 dashboard widget (workflow_observer suggestions).
 *  Narrow filters — add pagination when volume grows. */
export async function listProposals(opts: {
  entityType?: string;
  agentType?: string;
  status?: string;
  limit?: number;
} = {}): Promise<{ items: Proposal[]; total: number }> {
  const params = new URLSearchParams();
  if (opts.entityType) params.set("entity_type", opts.entityType);
  if (opts.agentType) params.set("agent_type", opts.agentType);
  if (opts.status) params.set("status", opts.status);
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return api.get<{ items: Proposal[]; total: number }>(
    `/v1/proposals${qs ? `?${qs}` : ""}`,
  );
}

export async function acceptProposal(id: string): Promise<ResolveResponse> {
  return api.post<ResolveResponse>(`/v1/proposals/${id}/accept`);
}

export async function editAndAcceptProposal(
  id: string,
  editedPayload: Record<string, unknown>,
  note?: string,
): Promise<ResolveResponse> {
  return api.post<ResolveResponse>(`/v1/proposals/${id}/edit-and-accept`, {
    edited_payload: editedPayload,
    note,
  });
}

export async function rejectProposal(
  id: string,
  opts: { permanently?: boolean; note?: string } = {},
): Promise<RejectResponse> {
  return api.post<RejectResponse>(`/v1/proposals/${id}/reject`, {
    permanently: opts.permanently ?? false,
    note: opts.note,
  });
}
