"use client";

import { Badge } from "@/components/ui/badge";
import { Circle, CheckCircle2, EyeOff, Archive, AlertTriangle, Minus, Send, Bot } from "lucide-react";

export function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <span title="Pending"><Circle className="h-4 w-4 text-amber-500" /></span>;
    case "awaiting_reply":
      return <span title="Awaiting reply"><Send className="h-4 w-4 text-blue-500" /></span>;
    case "handled":
      return <span title="Handled"><CheckCircle2 className="h-4 w-4 text-green-600" /></span>;
    case "ignored":
      return <span title="Ignored"><EyeOff className="h-4 w-4 text-muted-foreground" /></span>;
    case "archived":
      return <span title="Archived"><Archive className="h-4 w-4 text-muted-foreground" /></span>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export function UrgencyBadge({ urgency }: { urgency: string | null }) {
  if (!urgency) return null;
  switch (urgency) {
    case "high":
      return <span title="High urgency"><AlertTriangle className="h-4 w-4 text-red-500" /></span>;
    case "medium":
      return <span title="Medium urgency"><AlertTriangle className="h-4 w-4 text-amber-500" /></span>;
    case "low":
      return <span title="Low urgency"><Minus className="h-4 w-4 text-muted-foreground" /></span>;
    default:
      return null;
  }
}

/** Sticky AI marker for threads the classifier auto-closed. Shows in
 *  every Handled/All view across roles — first surface where non-admins
 *  see the AI's work. Stays visible after the admin acks the in-thread
 *  banner, so the audit trail of "this was AI" survives.
 */
export function AIBadge({ show }: { show: boolean | undefined }) {
  if (!show) return null;
  return (
    <span title="Auto-handled by AI" className="inline-flex items-center gap-0.5 px-1.5 py-0 rounded text-[9px] font-medium bg-muted text-muted-foreground">
      <Bot className="h-2.5 w-2.5" />
      AI
    </span>
  );
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
  const labels: Record<string, string> = {
    service_request: "Service",
    gate_code: "Gate Code",
    auto_reply: "Auto Reply",
    no_response: "No Response",
  };
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 capitalize ${styles[category] || ""}`}>
      {labels[category] || category.replace("_", " ")}
    </Badge>
  );
}
