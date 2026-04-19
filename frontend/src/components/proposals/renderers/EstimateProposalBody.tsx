import { Badge } from "@/components/ui/badge";

interface LineItem {
  description: string;
  quantity?: number;
  unit_price?: number;
}

interface EstimatePayload {
  subject?: string;
  notes?: string;
  customer_id?: string | null;
  billing_name?: string | null;
  line_items?: LineItem[];
}

function fmtMoney(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  return `$${n.toFixed(2)}`;
}

export function EstimateProposalBody({ payload }: { payload: Record<string, unknown> }) {
  const p = payload as EstimatePayload;
  const total = (p.line_items ?? []).reduce(
    (acc, li) => acc + (li.quantity ?? 1) * (li.unit_price ?? 0),
    0,
  );
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">Estimate</Badge>
        {p.billing_name && (
          <Badge variant="outline" className="text-xs">
            {p.billing_name}
          </Badge>
        )}
      </div>
      {p.subject && <div className="font-medium">{p.subject}</div>}
      <div className="border rounded divide-y bg-muted/40">
        {(p.line_items ?? []).map((li, i) => (
          <div key={i} className="flex justify-between px-3 py-2 text-xs">
            <span className="truncate mr-2">
              {li.description}
              {li.quantity && li.quantity !== 1 ? ` × ${li.quantity}` : ""}
            </span>
            <span className="font-mono">
              {fmtMoney((li.quantity ?? 1) * (li.unit_price ?? 0))}
            </span>
          </div>
        ))}
        <div className="flex justify-between px-3 py-2 text-xs font-semibold bg-muted/60">
          <span>Total</span>
          <span className="font-mono">{fmtMoney(total)}</span>
        </div>
      </div>
      {p.notes && <div className="text-xs text-muted-foreground">{p.notes}</div>}
    </div>
  );
}
