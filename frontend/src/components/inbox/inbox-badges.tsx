"use client";

import { Badge } from "@/components/ui/badge";

export function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Badge variant="outline" className="border-amber-400 text-amber-600">Pending</Badge>;
    case "handled":
      return <Badge variant="default" className="bg-green-600">Handled</Badge>;
    case "ignored":
      return <Badge variant="secondary">Ignored</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export function UrgencyBadge({ urgency }: { urgency: string | null }) {
  if (!urgency) return null;
  switch (urgency) {
    case "high":
      return <Badge variant="destructive" className="text-[10px] px-1.5">High</Badge>;
    case "medium":
      return <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px] px-1.5">Med</Badge>;
    case "low":
      return <Badge variant="secondary" className="text-[10px] px-1.5">Low</Badge>;
    default:
      return null;
  }
}

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const styles: Record<string, string> = {
    schedule: "border-blue-400 text-blue-600",
    complaint: "border-red-400 text-red-600",
    billing: "border-amber-400 text-amber-600",
    gate_code: "border-green-400 text-green-600",
    service_request: "border-purple-400 text-purple-600",
    general: "",
  };
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 capitalize ${styles[category] || ""}`}>
      {category.replace("_", " ")}
    </Badge>
  );
}
