import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const emitSpy = vi.fn();
vi.mock("@/lib/events", () => ({ events: { emit: (t: string, i: unknown) => emitSpy(t, i) } }));

import { HoldForDispatchStep } from "./hold-for-dispatch-step";

describe("HoldForDispatchStep", () => {
  beforeEach(() => emitSpy.mockReset());

  it("emits handler.applied once on mount with unassigned_count", () => {
    render(
      <HoldForDispatchStep
        initial={{ entity_type: "job", entity_id: "a-1", unassigned_count: 7 }}
        onDone={vi.fn()}
      />,
    );
    const applied = emitSpy.mock.calls.filter(([t]) => t === "handler.applied");
    expect(applied).toHaveLength(1);
    expect(applied[0][1]).toMatchObject({
      entity_refs: { entity_id: "a-1", entity_type: "job" },
      payload: { handler: "hold_for_dispatch", input: { unassigned_count: 7 } },
    });
    expect(screen.getByText(/Held for dispatch/)).toBeInTheDocument();
    expect(screen.getByText(/7 waiting/)).toBeInTheDocument();
  });
});
