import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const putSpy = vi.fn();
vi.mock("@/lib/api", () => ({ api: { put: (p: string, b: unknown) => putSpy(p, b) } }));

const emitSpy = vi.fn();
vi.mock("@/lib/events", () => ({ events: { emit: (t: string, i: unknown) => emitSpy(t, i) } }));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { AssignInlineStep } from "./assign-inline-step";

const INITIAL = {
  entity_type: "job" as const,
  entity_id: "action-1",
  default_assignee_id: "u1",
  assignee_options: [
    { id: "u1", name: "Kim (Manager)", first_name: "Kim" },
    { id: "u2", name: "Jose (Tech)", first_name: "Jose" },
  ],
};

describe("AssignInlineStep", () => {
  beforeEach(() => {
    putSpy.mockReset();
    emitSpy.mockReset();
    putSpy.mockResolvedValue({});
  });

  it("Save sends first_name to PUT + emits handler.applied with assignee_user_id ref", async () => {
    const onDone = vi.fn();
    render(<AssignInlineStep initial={INITIAL} onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(1));
    expect(putSpy).toHaveBeenCalledWith("/v1/admin/agent-actions/action-1", {
      assigned_to: "Kim",
    });
    const applied = emitSpy.mock.calls.find(([t]) => t === "handler.applied");
    expect(applied).toBeTruthy();
    expect(applied![1]).toMatchObject({
      level: "user_action",
      entity_refs: {
        entity_id: "action-1",
        entity_type: "job",
        assignee_user_id: "u1",
      },
      payload: { handler: "assign_inline" },
    });
    // No user_id in the payload — R2 (event discipline).
    const payload = (applied![1] as { payload: Record<string, unknown> }).payload;
    expect(JSON.stringify(payload)).not.toMatch(/assignee_user_id|user_id/);
    expect(onDone).toHaveBeenCalled();
  });

  it("Skip emits handler.abandoned with reason=skip, no PUT", async () => {
    const onDone = vi.fn();
    render(<AssignInlineStep initial={INITIAL} onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /Skip/ }));
    expect(putSpy).not.toHaveBeenCalled();
    const abandoned = emitSpy.mock.calls.find(([t]) => t === "handler.abandoned");
    expect(abandoned).toBeTruthy();
    expect(abandoned![1]).toMatchObject({
      payload: { handler: "assign_inline", reason: "skip" },
      entity_refs: { entity_id: "action-1", entity_type: "job" },
    });
    expect(onDone).toHaveBeenCalled();
  });
});
