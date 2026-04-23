/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProposalCard } from "./ProposalCard";
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
    id: "prop-abc",
    organization_id: "org-1",
    agent_type: "email_drafter",
    entity_type: "job",
    source_type: "agent_thread",
    source_id: "thr-1",
    proposed_payload: {
      action_type: "repair",
      description: "Replace pump seal — Sierra Oaks",
      customer_name: "Tom Lewis",
    },
    confidence: 0.87,
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

describe("ProposalCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders job renderer for entity_type=job", () => {
    render(<ProposalCard proposal={makeProposal()} />);
    expect(screen.getByText("Replace pump seal — Sierra Oaks")).toBeInTheDocument();
    expect(screen.getByText("Tom Lewis")).toBeInTheDocument();
    // Badge + confidence
    expect(screen.getByText(/87%/)).toBeInTheDocument();
  });

  it("renders estimate renderer with totals", () => {
    render(
      <ProposalCard
        proposal={makeProposal({
          entity_type: "estimate",
          proposed_payload: {
            subject: "Pump swap",
            line_items: [
              { description: "Pump", quantity: 1, unit_price: 500 },
              { description: "Labor", quantity: 2, unit_price: 125 },
            ],
          },
        })}
      />
    );
    // Total = 500 + 2*125 = 750
    expect(screen.getByText("$750.00")).toBeInTheDocument();
    expect(screen.getByText("Pump swap")).toBeInTheDocument();
  });

  it("renders org_config renderer with key/value", () => {
    render(
      <ProposalCard
        proposal={makeProposal({
          agent_type: "workflow_observer",
          entity_type: "org_config",
          proposed_payload: { key: "agent_enabled", value: true },
        })}
      />
    );
    expect(screen.getByText("Agent Enabled")).toBeInTheDocument();
    expect(screen.getByText(/On/)).toBeInTheDocument();
  });

  it("falls back to JSON dump for unknown entity_type", () => {
    render(
      <ProposalCard
        proposal={makeProposal({
          entity_type: "something_unknown",
          proposed_payload: { foo: "bar" },
        })}
      />
    );
    // JSON-stringified payload visible
    expect(screen.getByText(/"foo": "bar"/)).toBeInTheDocument();
  });

  it("calls acceptProposal and fires onResolved on Accept click", async () => {
    const resolved = makeProposal({ status: "accepted" });
    (acceptProposal as ReturnType<typeof vi.fn>).mockResolvedValue({
      proposal: resolved,
      outcome_entity_id: "act-1",
      outcome_entity_type: "job",
      conflict: false,
    });
    const onResolved = vi.fn();

    render(<ProposalCard proposal={makeProposal()} onResolved={onResolved} />);
    // `Edit & Accept` also contains "accept" — use exact match to target
    // the primary Accept button only.
    fireEvent.click(screen.getByRole("button", { name: /^accept$/i }));

    await waitFor(() => {
      expect(acceptProposal).toHaveBeenCalledWith("prop-abc");
      expect(onResolved).toHaveBeenCalledWith(resolved);
    });
  });

  it("Phase 4: renders next_step inline and defers onResolved until the step finishes", async () => {
    const resolved = makeProposal({ status: "accepted" });
    (acceptProposal as ReturnType<typeof vi.fn>).mockResolvedValue({
      proposal: resolved,
      outcome_entity_id: "act-1",
      outcome_entity_type: "job",
      conflict: false,
      next_step: {
        kind: "hold_for_dispatch",
        initial: { entity_type: "job", entity_id: "act-1", unassigned_count: 2 },
      },
    });
    const onResolved = vi.fn();
    render(<ProposalCard proposal={makeProposal()} onResolved={onResolved} />);
    fireEvent.click(screen.getByRole("button", { name: /^accept$/i }));
    expect(await screen.findByText(/Held for dispatch/)).toBeInTheDocument();
    expect(onResolved).not.toHaveBeenCalled();
    // Card's own action footer is hidden while the step is up so the
    // user has one focused workflow to complete.
    expect(screen.queryByRole("button", { name: /edit & accept/i })).toBeNull();
  });

  it("Edit & Accept is disabled for non-editable entity types", () => {
    // job renderer doesn't support inline editing yet
    render(<ProposalCard proposal={makeProposal({ entity_type: "job" })} />);
    const editBtn = screen.getByRole("button", { name: /edit & accept/i });
    expect(editBtn).toBeDisabled();
  });

  it("Edit & Accept enters edit mode for editable entity types", () => {
    const estimatePayload = {
      subject: "Pump replace",
      line_items: [{ description: "Pump", quantity: 1, unit_price: 500 }],
    };
    render(
      <ProposalCard
        proposal={makeProposal({ entity_type: "estimate", proposed_payload: estimatePayload })}
      />,
    );
    const editBtn = screen.getByRole("button", { name: /edit & accept/i });
    expect(editBtn).not.toBeDisabled();
    fireEvent.click(editBtn);
    // Footer swaps to Save & Accept + Cancel
    expect(screen.getByRole("button", { name: /save & accept/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("hides action buttons when proposal is already resolved", () => {
    render(<ProposalCard proposal={makeProposal({ status: "accepted" })} />);
    expect(screen.queryByRole("button", { name: /^accept$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^reject$/i })).toBeNull();
  });

  it("renders resolved status badge", () => {
    render(<ProposalCard proposal={makeProposal({ status: "rejected" })} />);
    expect(screen.getByText("rejected")).toBeInTheDocument();
  });
});
