import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface LineItem {
  description: string;
  quantity?: number;
  unit_price?: number;
  is_taxed?: boolean;
  service_id?: string | null;
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

interface Props {
  payload: Record<string, unknown>;
  isEditing?: boolean;
  onChange?: (next: Record<string, unknown>) => void;
}

export function EstimateProposalBody({ payload, isEditing = false, onChange }: Props) {
  const p = payload as EstimatePayload;
  const lineItems = p.line_items ?? [];
  const total = lineItems.reduce(
    (acc, li) => acc + (li.quantity ?? 1) * (li.unit_price ?? 0),
    0,
  );

  const updateLineItem = (idx: number, patch: Partial<LineItem>) => {
    if (!onChange) return;
    const next = lineItems.map((li, i) => (i === idx ? { ...li, ...patch } : li));
    onChange({ ...(payload as Record<string, unknown>), line_items: next });
  };

  const removeLineItem = (idx: number) => {
    if (!onChange) return;
    const next = lineItems.filter((_, i) => i !== idx);
    onChange({ ...(payload as Record<string, unknown>), line_items: next });
  };

  const updateSubject = (v: string) => {
    if (!onChange) return;
    onChange({ ...(payload as Record<string, unknown>), subject: v });
  };

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
      {isEditing ? (
        <Input
          value={p.subject ?? ""}
          onChange={(e) => updateSubject(e.target.value)}
          placeholder="Subject"
          className="h-8 text-sm font-medium"
        />
      ) : (
        p.subject && <div className="font-medium">{p.subject}</div>
      )}
      <div className="border rounded divide-y bg-muted/40">
        {lineItems.map((li, i) => {
          const lineTotal = (li.quantity ?? 1) * (li.unit_price ?? 0);
          if (isEditing) {
            return (
              <div key={i} className="flex items-center gap-2 px-2 py-1.5">
                <Input
                  value={li.description}
                  onChange={(e) => updateLineItem(i, { description: e.target.value })}
                  className="h-7 text-xs flex-1 min-w-0"
                />
                <Input
                  type="number"
                  step="0.25"
                  min="0"
                  value={li.quantity ?? 1}
                  onChange={(e) => updateLineItem(i, { quantity: parseFloat(e.target.value) || 0 })}
                  className="h-7 text-xs font-mono w-16"
                  aria-label="Quantity"
                />
                <span className="text-muted-foreground text-xs">×</span>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={li.unit_price ?? 0}
                  onChange={(e) => updateLineItem(i, { unit_price: parseFloat(e.target.value) || 0 })}
                  className="h-7 text-xs font-mono w-24"
                  aria-label="Unit price"
                />
                <span className="font-mono text-xs text-muted-foreground w-20 text-right">
                  {fmtMoney(lineTotal)}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={() => removeLineItem(i)}
                  aria-label="Remove line item"
                  title="Remove line item"
                >
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            );
          }
          return (
            <div key={i} className="flex justify-between px-3 py-2 text-xs">
              <span className="truncate mr-2">
                {li.description}
                {li.quantity && li.quantity !== 1 ? ` × ${li.quantity}` : ""}
              </span>
              <span className="font-mono">{fmtMoney(lineTotal)}</span>
            </div>
          );
        })}
        <div className="flex justify-between px-3 py-2 text-xs font-semibold bg-muted/60">
          <span>Total</span>
          <span className="font-mono">{fmtMoney(total)}</span>
        </div>
      </div>
      {p.notes && !isEditing && (
        <div className="text-xs text-muted-foreground">{p.notes}</div>
      )}
    </div>
  );
}
