"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Inbox } from "lucide-react";

import { events } from "@/lib/events";

import type { StepComponentProps, UnassignedPoolInitial } from "./types";

/**
 * No user input for this step — the job's been parked in the queue.
 * We emit `handler.applied` once on mount so workflow-observer sees
 * the same shape as for interactive handlers. There's no Skip button;
 * the "action" is already complete by virtue of the job existing.
 */
export function UnassignedPoolStep({
  initial,
}: StepComponentProps<UnassignedPoolInitial>) {
  useEffect(() => {
    events.emit("handler.applied", {
      level: "user_action",
      entity_refs: {
        entity_id: initial.entity_id,
        entity_type: initial.entity_type,
      },
      payload: {
        handler: "unassigned_pool",
        input: { pool_count: initial.pool_count },
      },
    });
    // Emit once per mount; the proposal card remounts this component
    // on every accept, so re-emission is the intended behavior.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="border rounded-md bg-muted/40 p-3 flex items-center gap-3">
      <Inbox className="h-4 w-4 text-muted-foreground shrink-0" />
      <div className="text-xs flex-1">
        Added to the unassigned pool.{" "}
        <span className="text-muted-foreground">
          {initial.pool_count} waiting
        </span>
        .
      </div>
      <Link
        href="/jobs?assigned=unassigned"
        className="text-xs text-primary hover:underline shrink-0"
      >
        View queue
      </Link>
    </div>
  );
}
