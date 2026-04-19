/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { InboxRowHoverPanel } from "./InboxRowHoverPanel";
import type { InboxSummaryPayload } from "./InboxSummaryCard";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/proposals", async () => {
  const actual = await vi.importActual<typeof import("@/lib/proposals")>("@/lib/proposals");
  return { ...actual, acceptProposal: vi.fn(), rejectProposal: vi.fn() };
});

function payload(overrides: Partial<InboxSummaryPayload> = {}): InboxSummaryPayload {
  return {
    version: 1,
    ask: null,
    state: "Need to reply with availability",
    open_items: [],
    red_flags: [],
    linked_refs: [],
    confidence: 0.8,
    proposal_ids: [],
    ...overrides,
  };
}

describe("InboxRowHoverPanel", () => {
  it("renders subject and customer name in header", () => {
    render(
      <InboxRowHoverPanel
        payload={payload()}
        subject="Pool pump quote"
        customerName="Maple HOA"
        contactPersonName={null}
        contactEmail="mgr@example.com"
        lastMessageAt="2026-04-18T10:00:00Z"
        messageCount={3}
        customerAddress={null}
        proposals={[]}
        fallbackSnippet={null}
      />,
    );
    expect(screen.getByText("Maple HOA")).toBeInTheDocument();
    expect(screen.getByText("Pool pump quote")).toBeInTheDocument();
  });

  it("routes to /cases/:id when case chip is clicked", () => {
    pushMock.mockClear();
    render(
      <InboxRowHoverPanel
        payload={payload({
          linked_refs: [{ type: "case", id: "case-42", label: "SC-25-0042" }],
        })}
        subject="x"
        customerName="Maple"
        contactPersonName={null}
        contactEmail="mgr@example.com"
        lastMessageAt="2026-04-18T10:00:00Z"
        messageCount={1}
        customerAddress={null}
        proposals={[]}
        fallbackSnippet={null}
      />,
    );
    const chip = screen.getByText(/SC-25-0042/);
    fireEvent.click(chip);
    expect(pushMock).toHaveBeenCalledWith("/cases/case-42");
  });

  it("renders unknown linked_ref types as non-interactive chips", () => {
    pushMock.mockClear();
    render(
      <InboxRowHoverPanel
        payload={payload({
          linked_refs: [{ type: "unknown_kind", id: "zzz", label: "Zzz" }],
        })}
        subject="x"
        customerName="Maple"
        contactPersonName={null}
        contactEmail="mgr@example.com"
        lastMessageAt="2026-04-18T10:00:00Z"
        messageCount={1}
        customerAddress={null}
        proposals={[]}
        fallbackSnippet={null}
      />,
    );
    fireEvent.click(screen.getByText(/Zzz/));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("shows fallback snippet when payload is null", () => {
    render(
      <InboxRowHoverPanel
        payload={null}
        subject={null}
        customerName="Maple"
        contactPersonName={null}
        contactEmail="mgr@example.com"
        lastMessageAt={null}
        messageCount={0}
        customerAddress={null}
        proposals={[]}
        fallbackSnippet="See you Tuesday"
      />,
    );
    expect(screen.getByText("See you Tuesday")).toBeInTheDocument();
  });

  it("shows 'Awaiting summary' when payload and snippet are both null", () => {
    render(
      <InboxRowHoverPanel
        payload={null}
        subject={null}
        customerName="Maple"
        contactPersonName={null}
        contactEmail="mgr@example.com"
        lastMessageAt={null}
        messageCount={0}
        customerAddress={null}
        proposals={[]}
        fallbackSnippet={null}
      />,
    );
    expect(screen.getByText(/Awaiting summary/i)).toBeInTheDocument();
  });
});
