import { Badge } from "@/components/ui/badge";

/**
 * Renders a Phase 6 `inbox_rule` proposal payload. Mirrors the
 * backend's `describe_rule()` shape: one English sentence summarizing
 * the conditions + actions. Falls back to JSON for shapes the
 * renderer doesn't recognize so unknown payloads still display
 * something rather than blank.
 */

interface Condition {
  field?: string;
  operator?: string;
  value?: unknown;
}

interface Action {
  type?: string;
  params?: Record<string, unknown>;
}

interface InboxRulePayload {
  name?: string;
  conditions?: Condition[];
  actions?: Action[];
}

const FIELD_LABEL: Record<string, string> = {
  sender_email: "sender",
  sender_domain: "sender domain",
  recipient_email: "recipient",
  subject: "subject",
  category: "category",
  customer_id: "customer",
  customer_matched: "matched-to-customer",
  body: "body",
};

const OPERATOR_PHRASE: Record<string, string> = {
  equals: "is",
  contains: "contains",
  starts_with: "starts with",
  ends_with: "ends with",
  matches: "matches pattern",
};

function describeValue(value: unknown): string {
  if (Array.isArray(value)) {
    if (value.length <= 2) return value.map((v) => `"${v}"`).join(" or ");
    return `"${value[0]}" or ${value.length - 1} more`;
  }
  return `"${value}"`;
}

function describeAction(a: Action): string {
  const params = a.params || {};
  switch (a.type) {
    case "assign_folder":
      return `move to folder "${params.folder_key ?? "?"}"`;
    case "assign_tag":
      return `tag as "${params.tag ?? "?"}"`;
    case "assign_category":
      return `set category to "${params.category ?? "?"}"`;
    case "set_visibility":
      return `restrict visibility to roles ${JSON.stringify(params.role_slugs ?? "?")}`;
    case "suppress_contact_prompt":
      return "suppress new-contact prompt";
    case "route_to_spam":
      return "route to spam";
    case "mark_as_read":
      return "mark as read";
    case "skip_customer_match":
      return "skip customer-match shortcut";
    default:
      return `${a.type ?? "?"}(${JSON.stringify(params)})`;
  }
}

export function InboxRuleProposalBody({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const p = payload as InboxRulePayload;
  const conditions = p.conditions ?? [];
  const actions = p.actions ?? [];

  const condPhrases = conditions.map((c) => {
    const field = FIELD_LABEL[c.field || ""] || c.field || "?";
    const op = OPERATOR_PHRASE[c.operator || ""] || c.operator || "?";
    return `${field} ${op} ${describeValue(c.value)}`;
  });
  const actionPhrases = actions.map(describeAction);

  const when = condPhrases.length ? condPhrases.join(" and ") : "every message";
  const then = actionPhrases.length ? actionPhrases.join(", ") : "(no actions)";

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">New inbox rule</Badge>
        {p.name ? (
          <span className="text-xs text-muted-foreground">{p.name}</span>
        ) : null}
      </div>
      <div className="text-foreground">
        <span className="text-muted-foreground">When </span>
        {when}
        <span className="text-muted-foreground">: </span>
        {then}
      </div>
    </div>
  );
}
