"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft, Eye, Link2, Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import type { LinkableEntityType } from "./link-case-picker";

interface Candidate {
  id: string;
  label: string;
  sublabel?: string;
  case_id?: string | null;
}

interface ThreadPreview {
  id: string;
  subject: string | null;
  contact_email: string;
  customer_name: string | null;
  timeline: Array<{
    id: string;
    direction: string;
    from_email: string;
    subject: string | null;
    body: string | null;
    received_at: string | null;
    sent_at: string | null;
  }>;
}

interface Props {
  caseId: string;
  customerId?: string | null;
  onAttached?: () => void;
  label?: string;
}

/**
 * AttachExistingDialog — inverse picker. Opens from the case detail page and
 * lets the user attach an existing entity (invoice, thread, job, etc.) to
 * this case.
 *
 * UX: row click attaches immediately (fast path). The eye icon drills into a
 * preview view without attaching — useful when the subject alone isn't enough
 * to identify the right thread. Preview is wired for email threads today;
 * other entity types can reuse the same drill-in shell.
 */
export function AttachExistingDialog({ caseId, customerId, onAttached, label }: Props) {
  const [open, setOpen] = useState(false);
  const [entityType, setEntityType] = useState<LinkableEntityType>("invoice");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [preview, setPreview] = useState<ThreadPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchCandidates = useCallback(async (type: LinkableEntityType, q: string) => {
    setLoading(true);
    try {
      let items: Candidate[] = [];
      if (type === "invoice") {
        const params = new URLSearchParams({ limit: "25" });
        if (customerId) params.set("customer_id", customerId);
        if (q.trim()) params.set("search", q.trim());
        const data = await api.get<{ items: { id: string; invoice_number: string | null; subject: string | null; document_type: string; total: number; case_id: string | null; status: string }[] }>(
          `/v1/invoices?${params}`
        );
        items = data.items.map((i) => ({
          id: i.id,
          label: `${i.invoice_number || "Draft"} — ${i.subject || "(no subject)"}`,
          sublabel: `${i.document_type} · $${i.total.toFixed(2)} · ${i.status}`,
          case_id: i.case_id,
        }));
      } else if (type === "thread") {
        // folder=all so threads routed to custom folders (Clients, Billing, etc.)
        // are searchable — default endpoint filters to Inbox only, which hides
        // most real candidates.
        const params = new URLSearchParams({ limit: "50", folder: "all" });
        if (customerId) params.set("customer_id", customerId);
        if (q.trim()) params.set("search", q.trim());
        const data = await api.get<{ items: { id: string; subject: string | null; contact_email: string; customer_name: string | null; case_id: string | null }[] }>(
          `/v1/admin/agent-threads?${params}`
        );
        items = data.items.map((t) => ({
          id: t.id,
          label: t.subject || "(no subject)",
          sublabel: `${t.contact_email}${t.customer_name ? ` · ${t.customer_name}` : ""}`,
          case_id: t.case_id,
        }));
      } else if (type === "job") {
        if (!customerId) {
          toast.error("Pick jobs from a case with a customer");
          items = [];
        } else {
          const data = await api.get<{ id: string; description: string; action_type: string; status: string }[]>(
            `/v1/invoices/suggest-jobs?customer_id=${customerId}`
          );
          items = data
            .filter((j) => !q.trim() || j.description.toLowerCase().includes(q.trim().toLowerCase()))
            .map((j) => ({
              id: j.id,
              label: j.description,
              sublabel: `${j.action_type} · ${j.status}`,
            }));
        }
      } else if (type === "internal_thread") {
        const data = await api.get<{ threads: { id: string; subject: string | null; customer_name: string | null; case_id: string | null; last_message: string | null }[] }>(
          "/v1/messages?limit=50"
        );
        items = data.threads
          .filter((t) => !q.trim() || (t.subject || "").toLowerCase().includes(q.trim().toLowerCase()))
          .map((t) => ({
            id: t.id,
            label: t.subject || "(no subject)",
            sublabel: t.customer_name || undefined,
            case_id: t.case_id,
          }));
      } else if (type === "deepblue_conversation") {
        const data = await api.get<{ conversations: { id: string; title: string | null; case_id: string | null; updated_at: string }[] }>(
          "/v1/deepblue/conversations?scope=mine&limit=50"
        );
        items = data.conversations
          .filter((c) => !q.trim() || (c.title || "").toLowerCase().includes(q.trim().toLowerCase()))
          .map((c) => ({
            id: c.id,
            label: c.title || "Untitled conversation",
            case_id: c.case_id,
          }));
      }
      setCandidates(items);
    } catch {
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void fetchCandidates(entityType, query), 200);
  }, [open, entityType, query, fetchCandidates]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setPreview(null);
    }
  }, [open]);

  // Reset preview when type changes.
  useEffect(() => {
    setPreview(null);
  }, [entityType]);

  const attach = async (candidateId: string) => {
    setWorking(candidateId);
    try {
      await api.post(`/v1/cases/${caseId}/link`, { type: entityType, id: candidateId });
      toast.success("Attached to case");
      setOpen(false);
      onAttached?.();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err.message || "Failed to attach");
    } finally {
      setWorking(null);
    }
  };

  const previewThread = async (threadId: string) => {
    setPreviewLoading(true);
    try {
      const data = await api.get<ThreadPreview>(`/v1/admin/agent-threads/${threadId}`);
      setPreview(data);
    } catch {
      toast.error("Couldn't load preview");
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-6 text-[10px] px-1.5 gap-0.5">
          <Link2 className="h-3 w-3" />
          {label || "Attach"}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[28rem] p-0" align="end">
        {preview ? renderPreview() : renderList()}
      </PopoverContent>
    </Popover>
  );

  function renderPreview() {
    if (!preview) return null;
    const messages = [...(preview.timeline || [])]
      .sort((a, b) => {
        const ta = a.received_at || a.sent_at || "";
        const tb = b.received_at || b.sent_at || "";
        return tb.localeCompare(ta);
      })
      .slice(0, 3);
    return (
      <div>
        <div className="flex items-center gap-2 p-2 border-b">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground"
            onClick={() => setPreview(null)}
            title="Back to list"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
          </Button>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">
              {preview.subject || "(no subject)"}
            </div>
            <div className="text-xs text-muted-foreground truncate">
              {preview.contact_email}
              {preview.customer_name && ` · ${preview.customer_name}`}
            </div>
          </div>
          <Button
            size="sm"
            onClick={() => attach(preview.id)}
            disabled={working !== null}
          >
            {working === preview.id && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />}
            Attach
          </Button>
        </div>
        <div className="max-h-80 overflow-y-auto p-2 space-y-2">
          {messages.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">
              No messages
            </div>
          ) : (
            messages.map((m) => (
              <div key={m.id} className="border rounded-md p-2 text-xs space-y-1 bg-muted/20">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium truncate">
                    {m.direction === "outbound" ? "Sent" : "Received"}: {m.from_email}
                  </span>
                  <span className="text-muted-foreground shrink-0">
                    {formatDate(m.received_at || m.sent_at)}
                  </span>
                </div>
                {m.subject && m.subject !== preview.subject && (
                  <div className="text-muted-foreground italic truncate">{m.subject}</div>
                )}
                <div className="text-foreground whitespace-pre-wrap line-clamp-4">
                  {(m.body || "").trim() || "(no body)"}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    );
  }

  function renderList() {
    return (
      <div>
        <div className="p-2 border-b space-y-2">
          <Select value={entityType} onValueChange={(v) => setEntityType(v as LinkableEntityType)}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="invoice">Invoice / Estimate</SelectItem>
              <SelectItem value="thread">Email thread</SelectItem>
              <SelectItem value="job">Job</SelectItem>
              <SelectItem value="internal_thread">Internal message</SelectItem>
              <SelectItem value="deepblue_conversation">DeepBlue conversation</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="h-8 pl-7 text-sm"
            />
          </div>
        </div>
        <div className="max-h-80 overflow-y-auto">
          {loading || previewLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : candidates.length === 0 ? (
            <div className="px-3 py-4 text-xs text-muted-foreground text-center">
              No matches
            </div>
          ) : (
            candidates.map((c) => {
              const alreadyAttachedHere = c.case_id === caseId;
              const canPreview = entityType === "thread";
              return (
                <div
                  key={c.id}
                  className="flex items-stretch border-b last:border-b-0 hover:bg-muted/50"
                >
                  <button
                    type="button"
                    className="flex-1 text-left px-3 py-2 text-sm disabled:opacity-40 min-w-0"
                    onClick={() => attach(c.id)}
                    disabled={working !== null || alreadyAttachedHere}
                  >
                    <div className="flex items-center gap-2">
                      <span className="truncate flex-1">{c.label}</span>
                      {alreadyAttachedHere && (
                        <span className="text-[10px] uppercase tracking-wide text-muted-foreground shrink-0">
                          attached
                        </span>
                      )}
                      {c.case_id && !alreadyAttachedHere && (
                        <span className="text-[10px] uppercase tracking-wide text-amber-600 shrink-0">
                          on another case
                        </span>
                      )}
                      {working === c.id && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    </div>
                    {c.sublabel && (
                      <div className="text-xs text-muted-foreground mt-0.5 truncate">
                        {c.sublabel}
                      </div>
                    )}
                  </button>
                  {canPreview && (
                    <button
                      type="button"
                      className="px-2 text-muted-foreground hover:text-foreground border-l disabled:opacity-40"
                      onClick={(e) => {
                        e.stopPropagation();
                        void previewThread(c.id);
                      }}
                      disabled={working !== null || previewLoading}
                      title="Preview before attaching"
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    );
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
    });
  } catch {
    return "";
  }
}
