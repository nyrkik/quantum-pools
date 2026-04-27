import { Badge } from "@/components/ui/badge";

/**
 * Renders a Phase 6 `workflow_config` proposal payload in plain
 * language. Two targets exist (`post_creation_handlers` and
 * `default_assignee_strategy`) with `set` / `merge` ops; the renderer
 * picks the most useful one-line summary for each combination.
 */

interface WorkflowConfigPayload {
  target?: string;
  op?: string;
  value?: unknown;
}

const TARGET_LABEL: Record<string, string> = {
  post_creation_handlers: "Post-creation step",
  default_assignee_strategy: "Default assignee",
};

function describeAssigneeStrategy(value: unknown): string {
  if (!value || typeof value !== "object") return "—";
  const v = value as { strategy?: string; fallback_user_id?: string };
  if (v.strategy === "fixed" && v.fallback_user_id) {
    return `Always preselect a specific person (id ${v.fallback_user_id.slice(0, 8)}…)`;
  }
  if (v.strategy === "last_used_in_org") return "Whoever was assigned last";
  if (v.strategy === "always_ask") return "Always ask — no default";
  return JSON.stringify(value);
}

function describeHandlersChange(op: string, value: unknown): string {
  if (!value || typeof value !== "object") return "—";
  const v = value as Record<string, unknown>;
  const entries = Object.entries(v);
  if (entries.length === 0) return "(no change)";
  const lines = entries.map(([entityType, handler]) => {
    if (handler === null || handler === "" || handler === undefined) {
      return `When ${entityType}s are created: don't show a follow-up step`;
    }
    return `When ${entityType}s are created: show "${handler}" step`;
  });
  const verb = op === "set" ? "Replace handlers with:" : "Add/update handlers:";
  return `${verb}\n${lines.join("\n")}`;
}

export function WorkflowConfigProposalBody({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const p = payload as WorkflowConfigPayload;
  const targetLabel = TARGET_LABEL[p.target || ""] || p.target || "setting";

  let body: string;
  if (p.target === "default_assignee_strategy") {
    body = describeAssigneeStrategy(p.value);
  } else if (p.target === "post_creation_handlers") {
    body = describeHandlersChange(p.op || "set", p.value);
  } else {
    body = JSON.stringify(p.value);
  }

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">Workflow change</Badge>
        <span className="text-xs text-muted-foreground">{targetLabel}</span>
      </div>
      <div className="whitespace-pre-line text-foreground">{body}</div>
    </div>
  );
}
