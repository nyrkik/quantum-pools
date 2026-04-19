import { Badge } from "@/components/ui/badge";

interface OrgConfigPayload {
  key?: string;
  value?: unknown;
}

function formatValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return JSON.stringify(v);
}

function formatKey(k: string | undefined): string {
  if (!k) return "setting";
  return k
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function OrgConfigProposalBody({ payload }: { payload: Record<string, unknown> }) {
  const p = payload as OrgConfigPayload;
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">Setting change</Badge>
      </div>
      <div className="font-medium">{formatKey(p.key)}</div>
      <div className="text-xs text-muted-foreground">
        Proposed value: <span className="font-mono">{formatValue(p.value)}</span>
      </div>
    </div>
  );
}
