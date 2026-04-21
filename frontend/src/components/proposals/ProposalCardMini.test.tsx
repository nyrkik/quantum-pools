/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProposalCardMini } from "./ProposalCardMini";
import type { Proposal } from "@/lib/proposals";

vi.mock("@/lib/proposals", async () => {
  const actual = await vi.importActual<typeof import("@/lib/proposals")>("@/lib/proposals");
  return {
    ...actual,
    acceptProposal: vi.fn(),
    rejectProposal: vi.fn(),
  };
});

import { acceptProposal, rejectProposal } from "@/lib/proposals";

function makeProposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: "prop-mini",
    organization_id: "org-1",
    agent_type: "inbox_summarizer",
    entity_type: "job",
    source_type: "agent_thread",
    source_id: "thr-1",
    proposed_payload: {
      action_type: "repair",
      description: "Replace pump seal",
    },
    confidence: 0.9,
    status: "staged",
    rejected_permanently: false,
    superseded_by_id: null,
    outcome_entity_type: null,
    outcome_entity_id: null,
    user_delta: null,
    resolved_at: null,
    resolved_by_user_id: null,
    resolution_note: null,
    created_at: "2026-04-19T10:00:00Z",
    updated_at: "2026-04-19T10:00:00Z",
    ...overrides,
  };
}

describe("ProposalCardMini", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the entity_type badge + body renderer", () => {
    render(<ProposalCardMini proposal={makeProposal()} />);
    expect(screen.getByText("Replace pump seal")).toBeInTheDocument();
    expect(screen.getByText(/^job$/i)).toBeInTheDocument();
  });

  it("fires accept on Accept click", async () => {
    const resolved = makeProposal({ status: "accepted" });
    (acceptProposal as ReturnType<typeof vi.fn>).mockResolvedValue({
      proposal: resolved, outcome_entity_id: "act-1",
      outcome_entity_type: "job", conflict: false,
    });
    const onResolved = vi.fn();

    render(<ProposalCardMini proposal={makeProposal()} onResolved={onResolved} />);
    fireEvent.click(screen.getByTitle("Accept proposal"));

    await waitFor(() => {
      expect(acceptProposal).toHaveBeenCalledWith("prop-mini");
      expect(onResolved).toHaveBeenCalledWith(resolved);
    });
  });

  it("fires reject on Reject click (no modal in mini)", async () => {
    const resolved = makeProposal({ status: "rejected" });
    (rejectProposal as ReturnType<typeof vi.fn>).mockResolvedValue({
      proposal: resolved,
    });
    const onResolved = vi.fn();

    render(<ProposalCardMini proposal={makeProposal()} onResolved={onResolved} />);
    fireEvent.click(screen.getByTitle("Reject proposal"));

    await waitFor(() => {
      expect(rejectProposal).toHaveBeenCalledWith("prop-mini");
      expect(onResolved).toHaveBeenCalledWith(resolved);
    });
  });

  it("hides action buttons when proposal is resolved", () => {
    render(<ProposalCardMini proposal={makeProposal({ status: "accepted" })} />);
    expect(screen.queryByTitle("Accept proposal")).toBeNull();
    expect(screen.queryByTitle("Reject proposal")).toBeNull();
  });

  it("Phase 4: when accept returns a next_step, renders the step + defers onResolved", async () => {
    const resolved = makeProposal({ status: "accepted" });
    (acceptProposal as ReturnType<typeof vi.fn>).mockResolvedValue({
      proposal: resolved,
      outcome_entity_id: "act-1",
      outcome_entity_type: "job",
      conflict: false,
      next_step: {
        kind: "hold_for_dispatch",
        initial: { entity_type: "job", entity_id: "act-1", unassigned_count: 4 },
      },
    });
    const onResolved = vi.fn();
    render(<ProposalCardMini proposal={makeProposal()} onResolved={onResolved} />);
    fireEvent.click(screen.getByTitle("Accept proposal"));

    // Step renders inside the card.
    expect(await screen.findByText(/Held for dispatch/)).toBeInTheDocument();
    // onResolved is deferred until the step finishes.
    expect(onResolved).not.toHaveBeenCalled();
  });
});
