import { Badge } from "@/components/ui/badge";

const STATUS_COLORS: Record<string, string> = {
  draft: "secondary",
  sent: "outline",
  revised: "outline",
  approved: "default",
  paid: "default",
  overdue: "destructive",
  void: "secondary",
  written_off: "outline",
};

export function InvoiceStatusBadge({ status }: { status: string }) {
  const variant = STATUS_COLORS[status] || "secondary";
  const colorClass =
    status === "sent"
      ? "border-blue-400 text-blue-600"
      : status === "revised"
        ? "border-amber-400 text-amber-600"
        : status === "approved"
          ? "bg-green-600"
          : status === "paid"
            ? "bg-green-600"
            : status === "written_off"
              ? "border-yellow-500 text-yellow-600"
              : "";
  return (
    <Badge variant={variant as "default"} className={colorClass}>
      {status.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
    </Badge>
  );
}
