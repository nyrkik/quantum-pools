import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

interface EmailReplyPayload {
  thread_id?: string;
  reply_to_message_id?: string;
  to?: string;
  subject?: string;
  body?: string;
  cc?: string[] | null;
  customer_id?: string | null;
}

interface Props {
  payload: Record<string, unknown>;
  isEditing?: boolean;
  onChange?: (next: Record<string, unknown>) => void;
}

export function EmailReplyProposalBody({
  payload,
  isEditing = false,
  onChange,
}: Props) {
  const p = payload as EmailReplyPayload;

  const patch = (fields: Partial<EmailReplyPayload>) => {
    if (!onChange) return;
    onChange({ ...(payload as Record<string, unknown>), ...fields });
  };

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">Reply</Badge>
        <span className="text-xs text-muted-foreground truncate">
          to {p.to || "—"}
        </span>
      </div>

      {isEditing ? (
        <Input
          value={p.subject ?? ""}
          onChange={(e) => patch({ subject: e.target.value })}
          placeholder="Subject"
          className="h-8 text-sm font-medium"
        />
      ) : (
        p.subject && <div className="font-medium truncate">{p.subject}</div>
      )}

      {isEditing ? (
        <Textarea
          value={p.body ?? ""}
          onChange={(e) => patch({ body: e.target.value })}
          placeholder="Reply body"
          className="text-sm min-h-[140px] font-mono"
        />
      ) : (
        <div className="whitespace-pre-wrap text-xs border rounded px-3 py-2 bg-muted/40 max-h-60 overflow-y-auto">
          {p.body}
        </div>
      )}
    </div>
  );
}
