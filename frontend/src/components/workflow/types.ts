/**
 * Phase 4 post-creation-handler types.
 *
 * Mirror the NextStep shape returned by `POST /v1/proposals/{id}/accept`
 * when the backend dispatches through WorkflowConfigService.resolve_next_step.
 * See docs/ai-platform-phase-4.md §4.1.
 */

export type HandlerKind =
  | "assign_inline"
  | "schedule_inline"
  | "unassigned_pool";

export interface NextStep {
  kind: HandlerKind | string;
  initial: Record<string, unknown>;
}

export interface AssigneeOption {
  id: string;
  name: string;
  first_name: string;
}

export interface AssignInlineInitial {
  entity_type: "job";
  entity_id: string;
  default_assignee_id: string | null;
  assignee_options: AssigneeOption[];
}

export interface ScheduleInlineInitial extends AssignInlineInitial {
  default_date: string;
}

export interface UnassignedPoolInitial {
  entity_type: "job";
  entity_id: string;
  pool_count: number;
}

export interface StepComponentProps<TInitial> {
  initial: TInitial;
  onDone: () => void;
}
