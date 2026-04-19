/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  InboxSummaryCard,
  type InboxSummaryPayload,
} from "./InboxSummaryCard";
import type { Proposal } from "@/lib/proposals";

vi.mock("@/lib/proposals", async () => {
  const actual = await vi.importActual<typeof import("@/lib/proposals")>("@/lib/proposals");
  return { ...actual, acceptProposal: vi.fn(), rejectProposal: vi.fn() };
});

function makeSummary(overrides: Partial<InboxSummaryPayload> = {}): InboxSummaryPayload {
  return {
    version: 1,
    ask: "Can you come fix the pump?",
    state: "Scheduled a repair visit for Thursday.",
    open_items: ["Confirm time with client"],
    red_flags: [],
    linked_refs: [{ type: "case", id: "case-1", label: "SC-25-0042" }],
    confidence: 0.9,
    proposal_ids: [],
    ...overrides,
  };
}

function makeProposal(id: string, entity_type = "job"): Proposal {
  return {
    id,
    organization_id: "org-1",
    agent_type: "inbox_summarizer",
    entity_type,
    source_type: "agent_thread",
    source_id: "thr-1",
    proposed_payload: { action_type: "repair", description: "Replace pump seal" },
    confidence: 0.85,
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
  };
}

describe("InboxSummaryCard", () => {
  it("renders ask, status, open items, and linked refs", () => {
    render(<InboxSummaryCard payload={makeSummary()} />);
    expect(screen.getByText("Can you come fix the pump?")).toBeInTheDocument();
    expect(screen.getByText("Scheduled a repair visit for Thursday.")).toBeInTheDocument();
    expect(screen.getByText("Confirm time with client")).toBeInTheDocument();
    expect(screen.getByText(/SC-25-0042/)).toBeInTheDocument();
  });

  it("hides the Ask section when ask is null (informational thread)", () => {
    render(<InboxSummaryCard payload={makeSummary({ ask: null })} />);
    expect(screen.queryByText(/^Ask$/i)).toBeNull();
  });

  it("renders red_flags with warning styling", () => {
    render(
      <InboxSummaryCard
        payload={makeSummary({ red_flags: ["Customer threatens chargeback"] })}
      />
    );
    expect(screen.getByText("Customer threatens chargeback")).toBeInTheDocument();
  });

  it("renders staged proposals that match payload.proposal_ids", () => {
    const p1 = makeProposal("prop-1");
    const p2 = makeProposal("prop-2");
    const summary = makeSummary({ proposal_ids: ["prop-1"] });
    render(<InboxSummaryCard payload={summary} proposals={[p1, p2]} />);
    // p1 renders (id in list), p2 does not
    expect(screen.getAllByText("Replace pump seal")).toHaveLength(1);
  });

  it("falls back to snippet when payload is null", () => {
    render(
      <InboxSummaryCard payload={null} fallbackSnippet="Thanks, see you Friday!" />
    );
    expect(screen.getByText("Thanks, see you Friday!")).toBeInTheDocument();
  });

  it("falls back to snippet on unsupported payload version", () => {
    const payload = makeSummary({ version: 99 });
    render(
      <InboxSummaryCard payload={payload} fallbackSnippet="future version fallback" />
    );
    expect(screen.getByText("future version fallback")).toBeInTheDocument();
    // Primary content from unsupported payload NOT rendered
    expect(screen.queryByText("Scheduled a repair visit for Thursday.")).toBeNull();
  });

  it("renders nothing when payload is null and no fallback is provided", () => {
    const { container } = render(<InboxSummaryCard payload={null} />);
    expect(container.firstChild).toBeNull();
  });
});
