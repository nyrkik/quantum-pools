import { Badge } from "@/components/ui/badge";

interface JobPayload {
  action_type?: string;
  description?: string;
  customer_id?: string | null;
  customer_name?: string | null;
  assigned_to?: string | null;
  due_date?: string | null;
  property_address?: string | null;
  notes?: string | null;
  job_path?: string;
}

export function JobProposalBody({ payload }: { payload: Record<string, unknown> }) {
  const p = payload as JobPayload;
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="capitalize">
          {p.action_type?.replace("_", " ") ?? "job"}
        </Badge>
        {p.job_path && (
          <Badge variant="outline" className="text-xs capitalize">
            {p.job_path}
          </Badge>
        )}
      </div>
      <div className="font-medium">{p.description ?? "(no description)"}</div>
      {p.customer_name && <div className="text-muted-foreground">{p.customer_name}</div>}
      {p.property_address && (
        <div className="text-xs text-muted-foreground">{p.property_address}</div>
      )}
      {p.due_date && (
        <div className="text-xs text-muted-foreground">
          Due {new Date(p.due_date).toLocaleDateString()}
        </div>
      )}
      {p.notes && <div className="text-xs text-muted-foreground">{p.notes}</div>}
    </div>
  );
}
