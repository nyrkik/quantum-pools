"use client";

import type { NextStep } from "./types";
import { AssignInlineStep } from "./assign-inline-step";
import { ScheduleInlineStep } from "./schedule-inline-step";
import { UnassignedPoolStep } from "./unassigned-pool-step";

/**
 * Resolve a backend-provided `next_step` to a rendered component.
 *
 * Per docs/ai-platform-phase-4.md §4.1 an unknown `kind` is a soft
 * failure — log a warning and render nothing so the user still ends
 * up on the entity's normal path. This keeps the frontend forward-
 * compatible with handler kinds the backend rolls out before the
 * frontend has shipped a matching component.
 */
export function NextStepRenderer({
  step,
  onDone,
}: {
  step: NextStep | null | undefined;
  onDone: () => void;
}) {
  if (!step) return null;

  switch (step.kind) {
    case "assign_inline":
      return (
        <AssignInlineStep
          initial={step.initial as unknown as Parameters<typeof AssignInlineStep>[0]["initial"]}
          onDone={onDone}
        />
      );
    case "schedule_inline":
      return (
        <ScheduleInlineStep
          initial={step.initial as unknown as Parameters<typeof ScheduleInlineStep>[0]["initial"]}
          onDone={onDone}
        />
      );
    case "unassigned_pool":
      return (
        <UnassignedPoolStep
          initial={step.initial as unknown as Parameters<typeof UnassignedPoolStep>[0]["initial"]}
          onDone={onDone}
        />
      );
    default:
      if (typeof window !== "undefined") {
        // eslint-disable-next-line no-console
        console.warn(
          "[workflow] unknown next_step.kind=%s — rendering nothing",
          step.kind,
        );
      }
      return null;
  }
}
