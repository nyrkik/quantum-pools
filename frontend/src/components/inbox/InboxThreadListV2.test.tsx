/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { InboxThreadListV2 } from "./InboxThreadListV2";
import type { Thread } from "@/types/agent";

// The component hydrates proposals via api.get for any thread whose
// payload.proposal_ids is non-empty. Stub it so tests stay hermetic.
vi.mock("@/lib/api", () => ({
  api: { get: vi.fn().mockResolvedValue(null) },
}));

// next/navigation is only touched by the hover panel's linked-ref clicks;
// stub it so render() doesn't blow up in jsdom.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function makeThread(overrides: Partial<Thread> = {}): Thread {
  return {
    id: "thr-1",
    contact_email: "client@example.com",
    subject: "Re: Re: Fwd: pool stuff",
    customer_name: "Pinebrook HOA",
    contact_name: null,
    customer_address: null,
    matched_customer_id: "cust-1",
    case_id: null,
    status: "open",
    urgency: null,
    category: null,
    message_count: 3,
    last_message_at: "2026-04-18T10:00:00Z",
    last_direction: "inbound",
    last_snippet: "Please confirm the invoice balance",
    has_pending: false,
    has_open_actions: false,
    assigned_to_user_id: null,
    assigned_to_name: null,
    assigned_at: null,
    is_unread: false,
    visibility_permission: null,
    delivered_to: null,
    sender_tag: null,
    ai_summary_payload: null,
    ...overrides,
  };
}

describe("InboxThreadListV2", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders customer name as primary label and time", () => {
    render(
      <InboxThreadListV2
        threads={[makeThread()]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    expect(screen.getByText("Pinebrook HOA")).toBeInTheDocument();
  });

  it("shows the AI `ask` in the main row when payload has one", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: "Please reschedule Thursday",
              state: "Quote pending",
              open_items: ["Send revised quote"],
              red_flags: [],
              linked_refs: [],
              confidence: 0.9,
              proposal_ids: [],
            },
          }),
        ]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    expect(screen.getByText("Please reschedule Thursday")).toBeInTheDocument();
    // Email subject stays hidden in the row (only shown on hover)
    expect(screen.queryByText("Re: Re: Fwd: pool stuff")).toBeNull();
  });

  it("falls back to `state` when ask is null", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: null,
              state: "We owe them a callback",
              open_items: [],
              red_flags: [],
              linked_refs: [],
              confidence: 0.8,
              proposal_ids: [],
            },
          }),
        ]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    expect(screen.getByText("We owe them a callback")).toBeInTheDocument();
  });

  it("falls back to first open_item when ask and state are empty", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: null,
              state: "",
              open_items: ["Send revised quote", "Schedule next visit"],
              red_flags: [],
              linked_refs: [],
              confidence: 0.8,
              proposal_ids: [],
            },
          }),
        ]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    // state is empty string, falls through to open_items[0]
    expect(screen.getByText("Send revised quote")).toBeInTheDocument();
  });

  it("falls back to last_snippet when payload is null", () => {
    render(
      <InboxThreadListV2
        threads={[makeThread({ ai_summary_payload: null })]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    expect(screen.getByText("Please confirm the invoice balance")).toBeInTheDocument();
  });

  it("falls back to subject when payload and snippet are both absent", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({ ai_summary_payload: null, last_snippet: null }),
        ]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    expect(screen.getByText("Re: Re: Fwd: pool stuff")).toBeInTheDocument();
  });

  it("shows red-flag warning icon when summary has red_flags", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: "refund",
              state: "Customer threatens chargeback",
              open_items: [],
              red_flags: ["Mentioned attorney"],
              linked_refs: [],
              confidence: 0.95,
              proposal_ids: [],
            },
          }),
        ]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    // Warning icon has accessible label
    expect(screen.getByLabelText(/1 red flag/)).toBeInTheDocument();
  });

  it("shows empty state when no threads", () => {
    render(
      <InboxThreadListV2 threads={[]} loading={false} onSelectThread={vi.fn()} />,
    );
    expect(screen.getByText(/No threads match this view/i)).toBeInTheDocument();
  });

  it("ignores unsupported payload versions (treats as null)", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 99,
              ask: "should not appear",
              state: "should not appear",
              open_items: [],
              red_flags: [],
              linked_refs: [],
              confidence: 0.9,
              proposal_ids: [],
            },
          }),
        ]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    // Falls through to snippet
    expect(screen.getByText("Please confirm the invoice balance")).toBeInTheDocument();
    expect(screen.queryByText("should not appear")).toBeNull();
  });
});
