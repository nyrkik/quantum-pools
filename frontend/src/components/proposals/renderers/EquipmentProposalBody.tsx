import { Badge } from "@/components/ui/badge";

interface EquipmentPayload {
  equipment_type?: string;
  brand?: string | null;
  model?: string | null;
  serial_number?: string | null;
  part_number?: string | null;
  horsepower?: number | null;
  flow_rate_gpm?: number | null;
  voltage?: number | null;
  install_date?: string | null;
  notes?: string | null;
}

export function EquipmentProposalBody({ payload }: { payload: Record<string, unknown> }) {
  const p = payload as EquipmentPayload;
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="capitalize">
          {p.equipment_type ?? "equipment"}
        </Badge>
        {p.brand && <span className="font-medium">{p.brand}</span>}
        {p.model && <span className="text-muted-foreground">{p.model}</span>}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {p.serial_number && (
          <div>
            <span className="font-medium">Serial:</span> {p.serial_number}
          </div>
        )}
        {p.part_number && (
          <div>
            <span className="font-medium">Part #:</span> {p.part_number}
          </div>
        )}
        {p.horsepower && (
          <div>
            <span className="font-medium">HP:</span> {p.horsepower}
          </div>
        )}
        {p.flow_rate_gpm && (
          <div>
            <span className="font-medium">GPM:</span> {p.flow_rate_gpm}
          </div>
        )}
        {p.voltage && (
          <div>
            <span className="font-medium">V:</span> {p.voltage}
          </div>
        )}
        {p.install_date && (
          <div>
            <span className="font-medium">Installed:</span>{" "}
            {new Date(p.install_date).toLocaleDateString()}
          </div>
        )}
      </div>
      {p.notes && <div className="text-xs text-muted-foreground">{p.notes}</div>}
    </div>
  );
}
