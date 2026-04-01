"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Check, Loader2, Eye, Send } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { getBackendOrigin } from "@/lib/api";

interface FeedbackItem {
  id: string;
  feedback_number: number | null;
  user_name: string;
  feedback_type: string;
  title: string;
  description: string | null;
  screenshot_urls: string[];
  page_url: string | null;
  ai_classification: Record<string, string> | null;
  ai_response: string | null;
  status: string;
  priority: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  user_notified: boolean;
  created_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  new: "bg-blue-600",
  triaged: "bg-amber-500",
  in_progress: "bg-purple-600",
  resolved: "bg-green-600",
  closed: "",
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "",
};

const TYPE_LABELS: Record<string, string> = {
  bug: "Bug",
  feature: "Feature",
  question: "Question",
  ux_issue: "UX Issue",
};

export default function FeedbackPage() {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selected, setSelected] = useState<FeedbackItem | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [userMessage, setUserMessage] = useState("");
  const [resolving, setResolving] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (typeFilter !== "all") params.set("feedback_type", typeFilter);
      params.set("limit", "100");
      const data = await api.get<FeedbackItem[]>(`/v1/feedback?${params}`);
      setItems(data);
    } catch {
      toast.error("Failed to load feedback");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleResolve = async () => {
    if (!selected) return;
    setResolving(true);
    try {
      await api.put(`/v1/feedback/${selected.id}`, {
        status: "resolved",
        resolution_notes: resolutionNotes || undefined,
      });
      toast.success("Feedback resolved");
      setSelected(null);
      setResolutionNotes("");
      fetchItems();
    } catch {
      toast.error("Failed to resolve");
    } finally {
      setResolving(false);
    }
  };

  const handleStatusChange = async (id: string, status: string) => {
    try {
      await api.put(`/v1/feedback/${id}`, { status });
      toast.success("Status updated");
      fetchItems();
    } catch {
      toast.error("Failed to update");
    }
  };

  const counts = {
    total: items.length,
    new: items.filter((i) => i.status === "new").length,
    triaged: items.filter((i) => i.status === "triaged").length,
  };

  return (
    <PageLayout
      title="Feedback"
      subtitle={`${counts.total} items${counts.new > 0 ? ` · ${counts.new} new` : ""}`}
    >
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="triaged">Triaged</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="bug">Bug</SelectItem>
            <SelectItem value="feature">Feature</SelectItem>
            <SelectItem value="question">Question</SelectItem>
            <SelectItem value="ux_issue">UX Issue</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide w-20">ID</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Priority</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Type</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Title</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">User</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Page</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Date</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8 text-muted-foreground">
                  No feedback found
                </TableCell>
              </TableRow>
            ) : (
              items.map((item, i) => (
                <TableRow
                  key={item.id}
                  className={`hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                  onClick={() => { setSelected(item); setResolutionNotes(item.resolution_notes || ""); }}
                >
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    {item.feedback_number ? `FB-${String(item.feedback_number).padStart(3, "0")}` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge className={STATUS_COLORS[item.status] || ""} variant={item.status === "closed" ? "secondary" : "default"}>
                      {item.status.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {item.priority && (
                      <Badge className={PRIORITY_COLORS[item.priority] || ""} variant={item.priority === "low" ? "secondary" : "default"}>
                        {item.priority}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{TYPE_LABELS[item.feedback_type] || item.feedback_type}</Badge>
                  </TableCell>
                  <TableCell className="font-medium max-w-[300px] truncate">{item.title}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{item.user_name}</TableCell>
                  <TableCell className="text-muted-foreground text-xs max-w-[120px] truncate">{item.page_url || "—"}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {item.created_at ? new Date(item.created_at).toLocaleDateString() : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setSelected(item); setResolutionNotes(item.resolution_notes || ""); }}>
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                      {item.status === "resolved" && !item.user_notified && (
                        <>
                          <Button variant="outline" size="sm" className="h-6 text-[10px] px-2" onClick={async () => {
                            try {
                              await api.put(`/v1/feedback/${item.id}`, { notify_user: false });
                              fetchItems();
                            } catch { toast.error("Failed"); }
                          }}>
                            No
                          </Button>
                          <Button size="sm" className="h-6 text-[10px] px-2" onClick={async () => {
                            try {
                              await api.put(`/v1/feedback/${item.id}`, { notify_user: true });
                              toast.success("Notified");
                              fetchItems();
                            } catch { toast.error("Failed"); }
                          }}>
                            Notify
                          </Button>
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={(open) => { if (!open) setSelected(null); }}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{selected?.feedback_number ? `FB-${String(selected.feedback_number).padStart(3, "0")}: ` : ""}{selected?.title}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge className={STATUS_COLORS[selected.status] || ""} variant={selected.status === "closed" ? "secondary" : "default"}>
                  {selected.status.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                </Badge>
                {selected.priority && (
                  <Badge className={PRIORITY_COLORS[selected.priority] || ""} variant={selected.priority === "low" ? "secondary" : "default"}>
                    {selected.priority}
                  </Badge>
                )}
                <Badge variant="outline">{TYPE_LABELS[selected.feedback_type] || selected.feedback_type}</Badge>
              </div>

              <div className="text-sm space-y-1">
                <div><span className="text-muted-foreground">From:</span> {selected.user_name}</div>
                <div><span className="text-muted-foreground">Page:</span> {selected.page_url || "—"}</div>
                <div><span className="text-muted-foreground">Date:</span> {selected.created_at ? new Date(selected.created_at).toLocaleString() : "—"}</div>
              </div>

              {selected.description && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Description</p>
                  <p className="text-sm whitespace-pre-wrap bg-muted/50 rounded-md p-3">{selected.description}</p>
                </div>
              )}

              {selected.screenshot_urls.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Screenshots</p>
                  <div className="flex gap-2 flex-wrap">
                    {selected.screenshot_urls.map((url, i) => {
                      const fullUrl = `${getBackendOrigin()}${url}`;
                      return (
                        <a key={i} href={fullUrl} target="_blank" rel="noopener noreferrer">
                          <img src={fullUrl} alt="" className="h-24 w-24 object-cover rounded-md border hover:opacity-80 transition" />
                        </a>
                      );
                    })}
                  </div>
                </div>
              )}

              {selected.ai_response && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">AI Assessment</p>
                  <p className="text-sm bg-blue-50 dark:bg-blue-950/30 rounded-md p-3 border border-blue-200 dark:border-blue-900">{selected.ai_response}</p>
                </div>
              )}

              {selected.ai_classification && (
                <div className="text-xs text-muted-foreground">
                  AI category: {selected.ai_classification.category || "—"} · Severity: {selected.ai_classification.severity || "—"}
                  {selected.ai_classification.investigation_notes && (
                    <p className="mt-1">Notes: {selected.ai_classification.investigation_notes}</p>
                  )}
                </div>
              )}

              {selected.resolved_by && (
                <div className="text-sm border-t pt-3">
                  <div><span className="text-muted-foreground">Resolved by:</span> {selected.resolved_by}</div>
                  {selected.resolved_at && <div><span className="text-muted-foreground">On:</span> {new Date(selected.resolved_at).toLocaleString()}</div>}
                  {selected.resolution_notes && <div className="mt-1 text-muted-foreground">{selected.resolution_notes}</div>}
                </div>
              )}

              {/* Status controls — for non-resolved items */}
              {selected.status !== "resolved" && selected.status !== "closed" && (
                <div className="border-t pt-3 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Set status:</span>
                    {["new", "triaged", "in_progress"].filter((s) => s !== selected.status).map((s) => (
                      <Button key={s} variant="outline" size="sm" className="h-7 text-xs capitalize" onClick={() => { handleStatusChange(selected.id, s); setSelected({ ...selected, status: s }); }}>
                        {s.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
