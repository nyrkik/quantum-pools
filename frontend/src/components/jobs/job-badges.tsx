"use client";

import { Badge } from "@/components/ui/badge";
import {
  Circle,
  Timer,
  CheckCircle2,
  X,
  Clock,
  ThumbsUp,
  Users,
  UserCheck,
} from "lucide-react";

export function ActionTypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    bid: "border-green-400 text-green-600",
    follow_up: "border-blue-400 text-blue-600",
    schedule_change: "border-purple-400 text-purple-600",
    site_visit: "border-amber-400 text-amber-600",
    callback: "border-cyan-400 text-cyan-600",
    repair: "border-red-400 text-red-600",
    equipment: "border-orange-400 text-orange-600",
    invoice: "border-emerald-400 text-emerald-600",
    other: "",
  };
  return (
    <Badge
      variant="outline"
      className={`text-[10px] px-1.5 capitalize ${styles[type] || ""}`}
    >
      {type.replace("_", " ")}
    </Badge>
  );
}

export function ActionStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "open":
      return <Circle className="h-3.5 w-3.5 text-amber-500" />;
    case "in_progress":
      return <Timer className="h-3.5 w-3.5 text-blue-500" />;
    case "done":
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case "cancelled":
      return <X className="h-3.5 w-3.5 text-muted-foreground" />;
    case "pending_approval":
      return <Clock className="h-3.5 w-3.5 text-purple-500" />;
    case "approved":
      return <ThumbsUp className="h-3.5 w-3.5 text-green-500" />;
    default:
      return <Circle className="h-3.5 w-3.5 text-muted-foreground" />;
  }
}

export function JobPathBadge({ path }: { path?: string }) {
  if (!path || path === "internal") return null;
  return (
    <Badge variant="outline" className="text-[10px] px-1.5 border-purple-400 text-purple-600 gap-0.5">
      <UserCheck className="h-2.5 w-2.5" />
      Customer
    </Badge>
  );
}
