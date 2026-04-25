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
    visibility_role_slugs: null,
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

  it("renders open_items as bullets in the body (primary display)", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: null,
              state: null,
              open_items: [
                "Filter cleaning — Approved",
                "Pool sweep tail — Approved",
              ],
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
    expect(screen.getByText("Filter cleaning — Approved")).toBeInTheDocument();
    expect(screen.getByText("Pool sweep tail — Approved")).toBeInTheDocument();
    // Email subject stays hidden in the row (only shown on hover)
    expect(screen.queryByText("Re: Re: Fwd: pool stuff")).toBeNull();
  });

  it("caps bullets at 5 when open_items has more", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: null,
              state: null,
              open_items: ["a", "b", "c", "d", "e", "f", "g"],
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
    ["a", "b", "c", "d", "e"].forEach((b) =>
      expect(screen.getByText(b)).toBeInTheDocument(),
    );
    expect(screen.queryByText("f")).toBeNull();
    expect(screen.queryByText("g")).toBeNull();
  });

  it("falls back to `ask` when no bullets", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: "Please reschedule Thursday",
              state: null,
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
    expect(screen.getByText("Please reschedule Thursday")).toBeInTheDocument();
  });

  it("falls back to `state` when no bullets and no ask", () => {
    render(
      <InboxThreadListV2
        threads={[
          makeThread({
            ai_summary_payload: {
              version: 1,
              ask: null,
              state: "Informational update",
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
    expect(screen.getByText("Informational update")).toBeInTheDocument();
  });

  it("renders customer_address under the name when present", () => {
    render(
      <InboxThreadListV2
        threads={[makeThread({ customer_address: "7210 Crocker Road" })]}
        loading={false}
        onSelectThread={vi.fn()}
      />,
    );
    expect(screen.getByText("7210 Crocker Road")).toBeInTheDocument();
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
