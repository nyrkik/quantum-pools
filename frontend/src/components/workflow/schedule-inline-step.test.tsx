import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const putSpy = vi.fn();
vi.mock("@/lib/api", () => ({ api: { put: (p: string, b: unknown) => putSpy(p, b) } }));

const emitSpy = vi.fn();
vi.mock("@/lib/events", () => ({ events: { emit: (t: string, i: unknown) => emitSpy(t, i) } }));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ScheduleInlineStep } from "./schedule-inline-step";

const INITIAL = {
  entity_type: "job" as const,
  entity_id: "action-2",
  default_date: "2026-04-21T09:00:00Z",
  default_assignee_id: "u2",
  assignee_options: [
    { id: "u1", name: "Kim (Manager)", first_name: "Kim" },
    { id: "u2", name: "Jose (Tech)", first_name: "Jose" },
  ],
};

describe("ScheduleInlineStep", () => {
  beforeEach(() => {
    putSpy.mockReset();
    emitSpy.mockReset();
    putSpy.mockResolvedValue({});
  });

  it("Save PUTs assigned_to + due_date (ISO UTC) + emits handler.applied", async () => {
    const onDone = vi.fn();
    render(<ScheduleInlineStep initial={INITIAL} onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(1));
    const [path, body] = putSpy.mock.calls[0];
    expect(path).toBe("/v1/admin/agent-actions/action-2");
    const typedBody = body as { assigned_to: string; due_date: string };
    expect(typedBody.assigned_to).toBe("Jose");
    // Must be a valid ISO UTC instant. The exact value depends on
    // the host TZ (datetime-local is interpreted locally), so just
    // validate shape rather than the wall-clock.
    expect(typedBody.due_date).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);

    const applied = emitSpy.mock.calls.find(([t]) => t === "handler.applied");
    expect(applied).toBeTruthy();
    expect(applied![1]).toMatchObject({
      entity_refs: {
        entity_id: "action-2",
        entity_type: "job",
        assignee_user_id: "u2",
      },
      payload: { handler: "schedule_inline" },
    });
    expect(onDone).toHaveBeenCalled();
  });

  it("Skip emits handler.abandoned, no PUT", async () => {
    const onDone = vi.fn();
    render(<ScheduleInlineStep initial={INITIAL} onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /Skip/ }));
    expect(putSpy).not.toHaveBeenCalled();
    const abandoned = emitSpy.mock.calls.find(([t]) => t === "handler.abandoned");
    expect(abandoned![1]).toMatchObject({
      payload: { handler: "schedule_inline", reason: "skip" },
    });
    expect(onDone).toHaveBeenCalled();
  });
});
