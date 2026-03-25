"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Loader2,
  Clock,
  Send,
  X,
  Bot,
  CheckCircle2,
  Circle,
  Timer,
  ClipboardList,
  Plus,
  Trash2,
  Mail,
  DollarSign,
} from "lucide-react";

// ─── Interfaces ──────────────────────────────────────────────────────

interface AgentAction {
  id: string;
  agent_message_id: string;
  action_type: string;
  description: string;
  assigned_to: string | null;
  due_date: string | null;
  status: string;
  completed_at: string | null;
  created_at: string | null;
  from_email?: string;
  customer_name?: string;
  subject?: string;
}

interface ActionComment {
  id: string;
  author: string;
  text: string;
  created_at: string;
}

interface RelatedJob {
  id: string;
  action_type: string;
  description: string;
  status: string;
  comments: { author: string; text: string }[];
}

interface ActionDetail extends AgentAction {
  comments?: ActionComment[];
  notes?: string | null;
  invoice_id?: string | null;
  from_email?: string;
  customer_name?: string;
  subject?: string;
  email_body?: string;
  our_response?: string;
  related_jobs?: RelatedJob[];
}

interface AgentStats {
  total: number;
  pending: number;
  sent: number;
  auto_sent: number;
  rejected: number;
  ignored: number;
  by_category: Record<string, number>;
  by_urgency: Record<string, number>;
  recent_24h: number;
  open_actions: number;
  overdue_actions: number;
  avg_response_seconds: number | null;
  stale_pending: number;
}

// ─── Constants ───────────────────────────────────────────────────────

const ACTION_TYPES = [
  "follow_up",
  "bid",
  "schedule_change",
  "site_visit",
  "callback",
  "repair",
  "equipment",
  "other",
];

// ─── Team Members Hook ──────────────────────────────────────────────

let _cachedTeam: string[] | null = null;
function useTeamMembers() {
  const [members, setMembers] = useState<string[]>(_cachedTeam || []);
  useEffect(() => {
    if (_cachedTeam) return;
    api
      .get<
        { first_name: string; is_verified: boolean; is_active: boolean }[]
      >("/v1/team")
      .then((data) => {
        const names = data
          .filter((m) => m.is_verified && m.is_active)
          .map((m) => m.first_name);
        _cachedTeam = names;
        setMembers(names);
      })
      .catch(() => {});
  }, []);
  return members;
}

// ─── Helpers ─────────────────────────────────────────────────────────

function formatTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDueDate(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.ceil((d.getTime() - now.getTime()) / 86400000);
  if (diffDays < 0) return `${Math.abs(diffDays)}d overdue`;
  if (diffDays === 0) return "Due today";
  if (diffDays === 1) return "Due tomorrow";
  return `Due in ${diffDays}d`;
}

function isOverdue(iso: string | null) {
  if (!iso) return false;
  return new Date(iso) < new Date();
}

// ─── Badge Components ───────────────────────────────────────────────

function ActionTypeBadge({ type }: { type: string }) {
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

function ActionStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "open":
      return <Circle className="h-3.5 w-3.5 text-amber-500" />;
    case "in_progress":
      return <Timer className="h-3.5 w-3.5 text-blue-500" />;
    case "done":
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case "cancelled":
      return <X className="h-3.5 w-3.5 text-muted-foreground" />;
    default:
      return <Circle className="h-3.5 w-3.5 text-muted-foreground" />;
  }
}

// ─── Client Property Search ─────────────────────────────────────────

function ClientPropertySearch({
  customerName,
  propertyAddress,
  onChange,
}: {
  customerName: string;
  propertyAddress: string;
  onChange: (name: string, address: string) => void;
}) {
  const [query, setQuery] = useState(customerName);
  const [results, setResults] = useState<
    {
      customer_name: string;
      property_address: string;
      property_name: string | null;
    }[]
  >([]);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api.get<
          {
            customer_name: string;
            property_address: string;
            property_name: string | null;
          }[]
        >(`/v1/admin/client-search?q=${encodeURIComponent(query)}`);
        setResults(data);
        setShowResults(true);
      } catch {
        setResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const [manualAddress, setManualAddress] = useState(false);

  return (
    <div className="space-y-2">
      <div className="relative">
        <div className="relative">
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onChange(e.target.value, propertyAddress);
            }}
            placeholder="Client name (search or type)"
            className="text-sm h-8 pr-7"
            onFocus={() => results.length > 0 && setShowResults(true)}
          />
          {(query || propertyAddress) && (
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => { setQuery(""); onChange("", ""); setManualAddress(false); setResults([]); }}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        {showResults && results.length > 0 && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowResults(false)}
            />
            <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-md border bg-background shadow-lg">
              {results.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  className="w-full px-3 py-2 text-left hover:bg-muted/50 text-sm"
                  onClick={() => {
                    setQuery(r.customer_name);
                    onChange(r.customer_name, r.property_address);
                    setShowResults(false);
                    setManualAddress(false);
                  }}
                >
                  <span className="font-medium">{r.customer_name}</span>
                  {r.property_name && (
                    <span className="text-muted-foreground ml-1">
                      ({r.property_name})
                    </span>
                  )}
                  <span className="text-xs text-muted-foreground block">
                    {r.property_address}
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      {propertyAddress && !manualAddress ? (
        <p className="text-xs text-muted-foreground px-1 cursor-pointer hover:text-foreground" onClick={() => setManualAddress(true)}>
          {propertyAddress}
        </p>
      ) : (
        <Input
          value={propertyAddress}
          onChange={(e) => onChange(query, e.target.value)}
          placeholder="Address"
          className="text-sm h-8"
        />
      )}
    </div>
  );
}

// ─── Job Detail Sheet ────────────────────────────────────────────

function ActionDetailSheet({
  actionId,
  onClose,
  onUpdate,
}: {
  actionId: string;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const teamMembers = useTeamMembers();
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [followUp, setFollowUp] = useState<{
    draft: string;
    to: string;
    subject: string;
  } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const [reviseInstruction, setReviseInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [invoiceDraft, setInvoiceDraft] = useState<{
    customer_id: string | null;
    customer_name: string;
    subject: string;
    line_items: {
      description: string;
      quantity: number;
      unit_price: number;
    }[];
    notes: string;
  } | null>(null);
  const [draftingInvoice, setDraftingInvoice] = useState(false);
  const [creatingInvoice, setCreatingInvoice] = useState(false);

  const handleDraftInvoice = async () => {
    setDraftingInvoice(true);
    try {
      const result = await api.post<{
        customer_id: string | null;
        customer_name: string;
        subject: string;
        line_items: {
          description: string;
          quantity: number;
          unit_price: number;
        }[];
        notes: string;
      }>(`/v1/admin/agent-actions/${actionId}/draft-invoice`, {});
      setInvoiceDraft(result);
    } catch {
      toast.error("Failed to draft invoice");
    } finally {
      setDraftingInvoice(false);
    }
  };

  const handleCreateInvoice = async () => {
    if (!invoiceDraft || !invoiceDraft.customer_id) {
      toast.error("No customer matched — can't create invoice");
      return;
    }
    setCreatingInvoice(true);
    try {
      const today = new Date().toISOString().split("T")[0];
      const due = new Date(Date.now() + 30 * 86400000)
        .toISOString()
        .split("T")[0];
      const inv = await api.post<{ id: string }>("/v1/invoices", {
        customer_id: invoiceDraft.customer_id,
        document_type: "estimate",
        subject: invoiceDraft.subject,
        issue_date: today,
        due_date: due,
        notes: invoiceDraft.notes,
        line_items: invoiceDraft.line_items.map((li, i) => ({
          description: li.description,
          quantity: li.quantity,
          unit_price: li.unit_price,
          is_taxed: false,
          sort_order: i,
        })),
      });
      // Link estimate to the job
      if (inv.id) {
        await api.put(`/v1/admin/agent-actions/${actionId}`, { invoice_id: inv.id } as Record<string, string>).catch(() => {});
      }
      toast.success("Estimate created");
      setInvoiceDraft(null);
      onUpdate();
    } catch (err: unknown) {
      toast.error(
        (err as { message?: string })?.message || "Failed to create invoice"
      );
    } finally {
      setCreatingInvoice(false);
    }
  };

  const handleDraftFollowUp = async () => {
    if (!detail) return;
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{
        draft: string;
        to: string;
        subject: string;
      }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/draft-followup`,
        {}
      );
      setFollowUp(result);
      setFollowUpText(result.draft);
    } catch {
      toast.error("Failed to draft follow-up");
    } finally {
      setDraftingFollowUp(false);
    }
  };

  const handleSendFollowUp = async () => {
    if (!detail || !followUpText.trim()) return;
    setSendingFollowUp(true);
    try {
      const result = await api.post<{
        sent: boolean;
        closed_actions: { description: string }[];
        ask_actions: {
          id: string;
          description: string;
          reason: string;
        }[];
      }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/send-followup`,
        { response_text: followUpText }
      );
      if (result.closed_actions?.length) {
        toast.success(
          `Follow-up sent. Completed: ${result.closed_actions
            .map((a) => a.description.slice(0, 40))
            .join(", ")}`
        );
      } else {
        toast.success("Follow-up sent");
      }
      if (result.ask_actions?.length) {
        for (const a of result.ask_actions) {
          toast(
            `Does this close "${a.description.slice(0, 50)}"? ${a.reason}`,
            { duration: 10000 }
          );
        }
      }
      setFollowUp(null);
      setFollowUpText("");
      setReviseInstruction("");
      loadDetail();
      onUpdate();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const handleRevise = async () => {
    if (!detail || !reviseInstruction.trim() || !followUpText) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(
        `/v1/admin/agent-messages/${detail.agent_message_id}/revise-draft`,
        {
          draft: followUpText,
          instruction: reviseInstruction,
        }
      );
      setFollowUpText(result.draft);
      setReviseInstruction("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setRevising(false);
    }
  };

  const loadDetail = useCallback(() => {
    setLoading(true);
    api
      .get<ActionDetail>(`/v1/admin/agent-actions/${actionId}`)
      .then((d) => {
        setDetail(d);
      })
      .catch(() => toast.error("Failed to load action"))
      .finally(() => setLoading(false));
  }, [actionId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleAddComment = async () => {
    if (!comment.trim()) return;
    setPosting(true);
    try {
      const result = await api.post<{
        action_resolved?: boolean;
        action_updated?: boolean;
        new_description?: string;
        auto_comment?: { author: string; text: string };
      }>(`/v1/admin/agent-actions/${actionId}/comments`, { text: comment });
      setComment("");
      if (result.auto_comment) {
        toast.success(`DeepBlue: ${result.auto_comment.text.slice(0, 80)}`);
      }
      if (result.action_resolved) {
        toast.success("Job marked complete — your comment resolved it");
      } else if (result.action_updated && result.new_description) {
        toast.success(
          `Job updated: ${result.new_description.slice(0, 60)}`
        );
      }
      loadDetail();
      onUpdate();
    } catch {
      toast.error("Failed to add comment");
    } finally {
      setPosting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!detail) return null;

  return (
    <div className="space-y-5 pt-2">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <ActionStatusIcon status={detail.status} />
          <ActionTypeBadge type={detail.action_type} />
          {detail.due_date &&
            isOverdue(detail.due_date) &&
            detail.status !== "done" && (
              <Badge
                variant="destructive"
                className="text-[10px] px-1.5"
              >
                Overdue
              </Badge>
            )}
        </div>
        <p className="text-sm font-medium">{detail.description}</p>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{detail.customer_name || detail.from_email}</span>
          {detail.assigned_to && (
            <span>Assigned: {detail.assigned_to}</span>
          )}
          {detail.due_date && <span>{formatDueDate(detail.due_date)}</span>}
        </div>
      </div>

      {/* Context trail */}
      {(detail.subject || detail.related_jobs) && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Context
          </p>

          {detail.subject && (
            <div className="bg-muted/50 rounded-md p-3 text-sm space-y-1">
              <p className="text-xs text-muted-foreground">
                Email: {detail.from_email}
              </p>
              <p className="font-medium">{detail.subject}</p>
              {detail.email_body && (
                <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-4">
                  {detail.email_body}
                </p>
              )}
            </div>
          )}

          {detail.our_response && (
            <div className="bg-green-50 dark:bg-green-950/20 rounded-md p-3 text-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Our reply
              </p>
              <p className="text-xs whitespace-pre-wrap line-clamp-3">
                {detail.our_response}
              </p>
            </div>
          )}

          {detail.related_jobs?.map((job) => (
            <div
              key={job.id}
              className="bg-muted/30 rounded-md p-2.5 text-sm"
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <ActionStatusIcon status={job.status} />
                <ActionTypeBadge type={job.action_type} />
              </div>
              <p
                className={`text-xs ${
                  job.status === "done"
                    ? "line-through text-muted-foreground"
                    : ""
                }`}
              >
                {job.description}
              </p>
              {job.comments.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {job.comments.map((c, i) => (
                    <p
                      key={i}
                      className="text-[10px] text-muted-foreground"
                    >
                      {c.author}: {c.text}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Comments / Activity */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          Activity
        </p>
        {detail.comments && detail.comments.length > 0 ? (
          <div className="space-y-2 mb-3">
            {detail.comments.map((c) => (
              <div key={c.id} className="bg-muted/50 rounded-md p-2.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium">{c.author}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {formatTime(c.created_at)}
                  </span>
                </div>
                <p className="text-sm">{c.text}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground mb-3">
            No comments yet
          </p>
        )}
        <div className="flex gap-2 items-end">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment..."
            className="text-sm min-h-[2.5rem] resize-none flex-1"
            rows={2}
          />
          <Button
            size="sm"
            className="h-9 flex-shrink-0"
            onClick={handleAddComment}
            disabled={posting || !comment.trim()}
          >
            {posting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              "Post"
            )}
          </Button>
        </div>
      </div>

      {/* Actions row */}
      {!followUp && !invoiceDraft && (
        <div className="pt-2 border-t flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraftFollowUp}
            disabled={draftingFollowUp}
          >
            {draftingFollowUp ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <Send className="h-3.5 w-3.5 mr-1.5" />
            )}
            Draft Follow-up
          </Button>
          {detail.invoice_id ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(`/invoices/${detail.invoice_id}`, "_self")}
            >
              <DollarSign className="h-3.5 w-3.5 mr-1.5" />
              View Estimate
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDraftInvoice}
              disabled={draftingInvoice}
            >
              {draftingInvoice ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              ) : (
                <DollarSign className="h-3.5 w-3.5 mr-1.5" />
              )}
              Create Estimate
            </Button>
          )}
        </div>
      )}

      {/* Invoice draft */}
      {invoiceDraft && (
        <div className="pt-2 border-t space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Invoice Draft
          </p>
          <div className="space-y-2">
            <div className="text-sm">
              <span className="text-muted-foreground">Customer: </span>
              <span className="font-medium">
                {invoiceDraft.customer_name}
              </span>
              {!invoiceDraft.customer_id && (
                <span className="text-red-600 text-xs ml-2">
                  (no match)
                </span>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">
                Subject
              </Label>
              <Input
                value={invoiceDraft.subject}
                onChange={(e) =>
                  setInvoiceDraft({
                    ...invoiceDraft,
                    subject: e.target.value,
                  })
                }
                className="h-8 text-sm"
              />
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              Line Items
            </p>
            {invoiceDraft.line_items.map((li, i) => (
              <div
                key={i}
                className="flex gap-2 items-start bg-muted/50 rounded-md p-2"
              >
                <div className="flex-1 space-y-1">
                  <Input
                    value={li.description}
                    onChange={(e) => {
                      const items = [...invoiceDraft.line_items];
                      items[i] = {
                        ...items[i],
                        description: e.target.value,
                      };
                      setInvoiceDraft({
                        ...invoiceDraft,
                        line_items: items,
                      });
                    }}
                    className="h-7 text-sm"
                    placeholder="Description"
                  />
                  <div className="flex gap-2">
                    <Input
                      type="number"
                      value={li.quantity}
                      onChange={(e) => {
                        const items = [...invoiceDraft.line_items];
                        items[i] = {
                          ...items[i],
                          quantity: parseFloat(e.target.value) || 0,
                        };
                        setInvoiceDraft({
                          ...invoiceDraft,
                          line_items: items,
                        });
                      }}
                      className="h-7 text-sm w-16"
                      placeholder="Qty"
                    />
                    <Input
                      type="number"
                      value={li.unit_price}
                      onChange={(e) => {
                        const items = [...invoiceDraft.line_items];
                        items[i] = {
                          ...items[i],
                          unit_price: parseFloat(e.target.value) || 0,
                        };
                        setInvoiceDraft({
                          ...invoiceDraft,
                          line_items: items,
                        });
                      }}
                      className="h-7 text-sm w-24"
                      placeholder="Price"
                      step="0.01"
                    />
                    <span className="text-sm text-muted-foreground self-center w-20 text-right">
                      ${(li.quantity * li.unit_price).toFixed(2)}
                    </span>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive mt-1"
                  onClick={() => {
                    const items = invoiceDraft.line_items.filter(
                      (_, j) => j !== i
                    );
                    setInvoiceDraft({
                      ...invoiceDraft,
                      line_items: items,
                    });
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={() =>
                setInvoiceDraft({
                  ...invoiceDraft,
                  line_items: [
                    ...invoiceDraft.line_items,
                    { description: "", quantity: 1, unit_price: 0 },
                  ],
                })
              }
            >
              <Plus className="h-3 w-3 mr-1" />
              Add Line
            </Button>
          </div>

          <div className="flex items-center justify-between text-sm font-medium pt-1 border-t">
            <span>Total</span>
            <span>
              $
              {invoiceDraft.line_items
                .reduce((sum, li) => sum + li.quantity * li.unit_price, 0)
                .toFixed(2)}
            </span>
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleCreateInvoice}
              disabled={creatingInvoice || !invoiceDraft.customer_id}
            >
              {creatingInvoice ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <DollarSign className="h-4 w-4 mr-2" />
              )}
              Create Estimate
            </Button>
            <Button
              variant="ghost"
              onClick={() => setInvoiceDraft(null)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {followUp && (
        <div className="pt-2 border-t space-y-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">
              Follow-up Draft
            </p>
            <p className="text-xs text-muted-foreground mb-2">
              To: {followUp.to} — Re: {followUp.subject}
            </p>
            <Textarea
              value={followUpText}
              onChange={(e) => setFollowUpText(e.target.value)}
              rows={6}
              className="text-sm"
            />
          </div>
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                value={reviseInstruction}
                onChange={(e) => setReviseInstruction(e.target.value)}
                placeholder="Tell AI how to change it..."
                className="text-sm h-8"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleRevise();
                  }
                }}
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={handleRevise}
              disabled={revising || !reviseInstruction.trim()}
            >
              {revising ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
              ) : null}
              Revise
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleSendFollowUp}
              disabled={sendingFollowUp || !followUpText.trim()}
            >
              {sendingFollowUp ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Send className="h-4 w-4 mr-2" />
              )}
              Send
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setFollowUp(null);
                setFollowUpText("");
                setReviseInstruction("");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Actions */}
      {(detail.status === "open" || detail.status === "in_progress") && (
        <div className="pt-3 border-t">
          <Button
            className="w-full bg-green-600 hover:bg-green-700"
            onClick={async () => {
              try {
                await api.put(`/v1/admin/agent-actions/${actionId}`, { status: "done" });
                toast.success("Job marked done");
                loadDetail();
                onUpdate();
              } catch { toast.error("Failed"); }
            }}
          >
            <CheckCircle2 className="h-4 w-4 mr-2" />
            Mark Done
          </Button>
        </div>
      )}

      {/* Delete */}
      {detail.status !== "cancelled" && (
        <div className="pt-2 flex justify-end">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-3 w-3 mr-1" />
                Delete Job
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this job?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove the action and all its
                  comments. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={async () => {
                    try {
                      await api.put(
                        `/v1/admin/agent-actions/${actionId}`,
                        { status: "cancelled" }
                      );
                      toast.success("Action deleted");
                      onClose();
                      onUpdate();
                    } catch {
                      toast.error("Failed");
                    }
                  }}
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────

export default function JobsPage() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const myName = user?.first_name || "";
  const teamMembers = useTeamMembers();
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(
    searchParams.get("action")
  );
  const [suggestion, setSuggestion] = useState<{
    id: string;
    action_type: string;
    description: string;
    reasoning: string;
  } | null>(null);
  const [newActionOpen, setNewActionOpen] = useState(false);
  const [newAction, setNewAction] = useState({
    action_type: "follow_up",
    description: "",
    assigned_to: "",
    due_days: "",
    customer_name: "",
    property_address: "",
  });
  const [jobFilter, setJobFilter] = useState<string>("mine");
  const [showCompleted, setShowCompleted] = useState(false);

  const handleToggleAction = async (
    actionId: string,
    currentStatus: string
  ) => {
    const newStatus = currentStatus === "done" ? "open" : "done";
    try {
      const result = await api.put<{
        suggestion?: {
          id: string;
          action_type: string;
          description: string;
          reasoning: string;
        };
      }>(`/v1/admin/agent-actions/${actionId}`, { status: newStatus });
      if (result.suggestion) {
        setSuggestion(result.suggestion);
      }
      load();
    } catch {
      toast.error("Failed to update");
    }
  };

  const load = useCallback(async () => {
    try {
      const assigneeParam =
        jobFilter === "mine" && myName
          ? `&assigned_to=${encodeURIComponent(myName)}`
          : jobFilter !== "mine" && jobFilter !== "all"
            ? `&assigned_to=${encodeURIComponent(jobFilter)}`
            : "";
      const statuses = showCompleted
        ? ["open", "in_progress", "done"]
        : ["open", "in_progress"];
      const [st, ...actionResults] = await Promise.all([
        api.get<AgentStats>("/v1/admin/agent-stats"),
        ...statuses.map((s) =>
          api
            .get<AgentAction[]>(
              `/v1/admin/agent-actions?status=${s}${assigneeParam}`
            )
            .catch(() => [] as AgentAction[])
        ),
      ]);
      setStats(st);
      setActions(actionResults.flat());
    } catch {
      toast.error("Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [jobFilter, showCompleted, myName]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll every 30s
  useEffect(() => {
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Group actions by parent message (event) or standalone
  const grouped = new Map<
    string,
    { label: string; from: string; actions: AgentAction[] }
  >();
  for (const a of actions) {
    const key = a.agent_message_id || `standalone-${a.id}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        label: a.subject || "Unknown",
        from: a.customer_name || a.from_email || "",
        actions: [],
      });
    }
    grouped.get(key)!.actions.push(a);
  }
  const groups = Array.from(grouped.entries());

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ClipboardList className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Jobs</h1>
      </div>

      {/* Open Jobs tile + New Job */}
      <div className="flex items-center justify-between gap-4">
        {stats && (
          <Card className={`shadow-sm py-3 px-4 ${stats.overdue_actions > 0 ? "border-l-4 border-red-500" : ""}`}>
            <div className="flex items-center gap-3">
              <ClipboardList className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-medium">Open Jobs</span>
              <span className="text-2xl font-bold">{stats.open_actions}</span>
              {stats.overdue_actions > 0 && (
                <Badge variant="destructive" className="text-[10px]">{stats.overdue_actions} overdue</Badge>
              )}
            </div>
          </Card>
        )}
        <Button onClick={() => setNewActionOpen(!newActionOpen)}>
          <Plus className="h-4 w-4 mr-2" />
          New Job
        </Button>
      </div>

      {/* AI Suggestion banner */}
      {suggestion && (
        <Card className="shadow-sm border-l-4 border-blue-500 bg-blue-50/50 dark:bg-blue-950/20">
          <CardContent className="py-3 px-4">
            <div className="flex items-start gap-3">
              <Bot className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">
                  Suggested next step
                </p>
                <p className="text-sm mt-0.5">
                  {suggestion.description}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {suggestion.reasoning}
                </p>
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
                <Button
                  size="sm"
                  className="h-7"
                  onClick={async () => {
                    try {
                      await api.put(
                        `/v1/admin/agent-actions/${suggestion.id}`,
                        { status: "open" }
                      );
                      toast.success("Action accepted");
                      setSuggestion(null);
                      load();
                    } catch {
                      toast.error("Failed");
                    }
                  }}
                >
                  Accept
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7"
                  onClick={async () => {
                    try {
                      await api.put(
                        `/v1/admin/agent-actions/${suggestion.id}`,
                        { status: "cancelled" }
                      );
                      setSuggestion(null);
                      load();
                    } catch {
                      toast.error("Failed");
                    }
                  }}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Job filters + New Job */}
      <div className="flex flex-col sm:flex-row gap-3 justify-between">
        <div className="flex gap-2 items-center">
          <Button
            variant={jobFilter === "mine" ? "default" : "outline"}
            size="sm"
            className="h-7"
            onClick={() => setJobFilter("mine")}
          >
            My Jobs
          </Button>
          <Button
            variant={jobFilter === "all" ? "default" : "outline"}
            size="sm"
            className="h-7"
            onClick={() => setJobFilter("all")}
          >
            All
          </Button>
          {teamMembers.length > 0 && (
            <Select
              value={teamMembers.includes(jobFilter) ? jobFilter : ""}
              onValueChange={(v) => setJobFilter(v)}
            >
              <SelectTrigger className="h-7 w-40 text-xs">
                <SelectValue placeholder="Team member..." />
              </SelectTrigger>
              <SelectContent>
                {teamMembers.map((name) => (
                  <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={showCompleted}
              onChange={(e) => setShowCompleted(e.target.checked)}
              className="rounded"
            />
            Done
          </label>
        </div>
      </div>

      {/* New Job form */}
      {newActionOpen && (
        <>
        <div className="fixed inset-0 z-30" onClick={() => setNewActionOpen(false)} />
        <Card className="shadow-sm relative z-40">
          <CardContent className="py-3 px-4 space-y-3">
            <Input
              value={newAction.description}
              onChange={(e) =>
                setNewAction({
                  ...newAction,
                  description: e.target.value,
                })
              }
              placeholder="What needs to be done?"
              className="text-sm"
              autoFocus
            />
            <Select
              value={newAction.action_type}
              onValueChange={(v) => setNewAction({ ...newAction, action_type: v })}
            >
              <SelectTrigger className="h-8 text-sm w-40">
                <SelectValue placeholder="Job type..." />
              </SelectTrigger>
              <SelectContent>
                {ACTION_TYPES.map((t) => (
                  <SelectItem key={t} value={t} className="text-sm capitalize">{t.replace("_", " ")}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ClientPropertySearch
              customerName={newAction.customer_name}
              propertyAddress={newAction.property_address}
              onChange={(name, addr) =>
                setNewAction({
                  ...newAction,
                  customer_name: name,
                  property_address: addr,
                })
              }
            />
            <div className="flex flex-wrap gap-2 items-end">
              <div className="w-48">
                <Select
                  value={newAction.assigned_to || ""}
                  onValueChange={(v) =>
                    setNewAction({ ...newAction, assigned_to: v })
                  }
                >
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue placeholder="Assign..." />
                  </SelectTrigger>
                  <SelectContent>
                    {teamMembers.map((name) => (
                      <SelectItem
                        key={name}
                        value={name}
                        className="text-sm"
                      >
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-36">
                <Input
                  type="date"
                  value={newAction.due_days}
                  onChange={(e) =>
                    setNewAction({
                      ...newAction,
                      due_days: e.target.value,
                    })
                  }
                  className="h-8 text-sm"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!newAction.description.trim()}
                onClick={async () => {
                  const dueDate = newAction.due_days
                    ? new Date(newAction.due_days + "T23:59:59").toISOString()
                    : undefined;
                  try {
                    await api.post("/v1/admin/agent-actions", {
                      action_type: newAction.action_type,
                      description: newAction.description,
                      assigned_to: newAction.assigned_to || undefined,
                      due_date: dueDate,
                      customer_name: newAction.customer_name || undefined,
                      property_address: newAction.property_address || undefined,
                    });
                    setNewAction({ action_type: "follow_up", description: "", assigned_to: "", due_days: "", customer_name: "", property_address: "" });
                    setNewActionOpen(false);
                    load();
                    toast.success("Job created");
                  } catch { toast.error("Failed to create"); }
                }}
              >
                Create
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setNewActionOpen(false)}
              >
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
        </>
      )}

      {/* Grouped jobs list */}
      <Card className="shadow-sm">
        <CardContent className="p-0">
          {actions.length === 0 && !newActionOpen ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <CheckCircle2 className="h-10 w-10 mb-3 opacity-40" />
              <p className="text-sm">All caught up — no open jobs</p>
            </div>
          ) : (
            <div className="divide-y">
              {groups.map(([msgId, group]) => {
                const hasOverdue = group.actions.some(
                  (a) =>
                    a.status !== "done" &&
                    a.status !== "cancelled" &&
                    isOverdue(a.due_date)
                );
                return (
                  <div
                    key={msgId}
                    className={
                      hasOverdue
                        ? "bg-red-50/50 dark:bg-red-950/10"
                        : ""
                    }
                  >
                    {/* Event header */}
                    <div className="flex items-center justify-between px-4 pt-3 pb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {group.from}
                        </p>
                        <span className="text-xs text-muted-foreground truncate hidden sm:inline">
                          — {group.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                      </div>
                    </div>
                    {/* Actions under this event */}
                    <div className="px-4 pb-3 space-y-1">
                      {group.actions.map((a) => {
                        const overdue =
                          a.status !== "done" &&
                          a.status !== "cancelled" &&
                          isOverdue(a.due_date);
                        return (
                          <div
                            key={a.id}
                            className={`flex items-start gap-2 py-1.5 pl-2 rounded cursor-pointer ${
                              overdue
                                ? "bg-red-50 dark:bg-red-950/20"
                                : "hover:bg-muted/50"
                            }`}
                            onClick={() => setSelectedActionId(a.id)}
                          >
                            <ActionStatusIcon status={a.status} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <ActionTypeBadge
                                  type={a.action_type}
                                />
                                {overdue && (
                                  <Badge
                                    variant="destructive"
                                    className="text-[10px] px-1.5"
                                  >
                                    Overdue
                                  </Badge>
                                )}
                                {a.due_date && (
                                  <span
                                    className={`text-[10px] ${
                                      overdue
                                        ? "text-red-600 font-medium"
                                        : "text-muted-foreground"
                                    }`}
                                  >
                                    {formatDueDate(a.due_date)}
                                  </span>
                                )}
                              </div>
                              <p
                                className={`text-sm mt-0.5 ${
                                  a.status === "done"
                                    ? "line-through text-muted-foreground"
                                    : ""
                                }`}
                              >
                                {a.description}
                              </p>
                              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                                <Select
                                  value={a.assigned_to || ""}
                                  onValueChange={async (v) => {
                                    try {
                                      await api.put(
                                        `/v1/admin/agent-actions/${a.id}`,
                                        { assigned_to: v }
                                      );
                                      load();
                                    } catch {
                                      toast.error(
                                        "Failed to assign"
                                      );
                                    }
                                  }}
                                >
                                  <SelectTrigger className="h-5 w-auto border-none bg-transparent p-0 text-xs gap-1 shadow-none">
                                    <SelectValue placeholder="Assign..." />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {teamMembers.map((name) => (
                                      <SelectItem
                                        key={name}
                                        value={name}
                                        className="text-xs"
                                      >
                                        {name}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0">
                              {a.assigned_to && (
                                <span className="text-[10px] text-muted-foreground">{a.assigned_to}</span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action detail sheet */}
      <Sheet
        open={!!selectedActionId}
        onOpenChange={(open) => {
          if (!open) setSelectedActionId(null);
        }}
      >
        <SheetContent className="w-full sm:max-w-md flex flex-col h-full">
          <SheetHeader className="px-4 sm:px-6 flex-shrink-0">
            <SheetTitle className="text-lg">Job Detail</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 pb-6">
            {selectedActionId && (
              <ActionDetailSheet
                actionId={selectedActionId}
                onClose={() => setSelectedActionId(null)}
                onUpdate={load}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
