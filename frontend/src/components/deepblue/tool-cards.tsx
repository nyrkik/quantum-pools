"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Mail, Send, Loader2, FolderOpen } from "lucide-react";
import { api } from "@/lib/api";

export function ToolResultCard({ name, result, stale = false, isLastOfType = true }: { name: string; result: Record<string, unknown>; stale?: boolean; isLastOfType?: boolean }) {
  if (name === "chemical_dosing_calculator") {
    const dosing = result.dosing as Array<Record<string, unknown>> | undefined;
    if (!dosing?.length) return null;
    const issues = dosing.filter((d) => d.status !== "ok");
    return (
      <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-1">
        <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
          Dosing — {result.pool_gallons?.toLocaleString()} gal
        </p>
        {issues.length === 0 ? (
          <p className="text-green-600">All readings in range</p>
        ) : (
          issues.map((d, i) => (
            <div key={i} className="flex justify-between items-start gap-2">
              <div>
                <span className={`font-medium ${d.status === "high" ? "text-red-600" : "text-amber-600"}`}>
                  {d.parameter as string}: {String(d.current)}
                </span>
                <span className="text-muted-foreground ml-1">(target: {d.target as string})</span>
              </div>
              {d.amount ? (
                <span className="text-right shrink-0 font-mono">{String(d.amount)}</span>
              ) : null}
            </div>
          ))
        )}
      </div>
    );
  }

  if (name === "get_equipment") {
    const equipment = result.equipment as Array<Record<string, unknown>> | undefined;
    if (!equipment?.length) return <p className="text-xs text-muted-foreground mt-1">No equipment found.</p>;
    return (
      <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-0.5">
        <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">Equipment</p>
        {equipment.map((e, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-muted-foreground w-16 shrink-0">{e.type as string}</span>
            <span className="font-medium">{e.name as string}</span>
          </div>
        ))}
      </div>
    );
  }

  if (name === "find_replacement_parts") {
    const mode = result.mode as string | undefined;
    const matched = result.equipment_matched as string | undefined;
    const partSearched = result.part_searched as string | undefined;

    if (mode === "compare_retailers") {
      const vendors = result.vendors as Array<Record<string, unknown>> | undefined;
      if (!vendors?.length) return <p className="text-xs text-muted-foreground mt-1">No retailers found.</p>;
      return (
        <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-1">
          <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
            Price Comparison{matched ? ` — ${matched}` : ""}{partSearched ? ` (${partSearched})` : ""}
          </p>
          {vendors.map((v, i) => (
            <div key={i} className="flex items-center justify-between gap-2 py-0.5">
              <div className="min-w-0 flex-1">
                {v.url ? (
                  <a href={String(v.url)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline truncate block">
                    {String(v.vendor || "Unknown")}
                  </a>
                ) : (
                  <span className="truncate block">{String(v.vendor || "Unknown")}</span>
                )}
                <span className="text-[10px] text-muted-foreground truncate block">{String(v.name || "")}</span>
              </div>
              {v.price ? <span className="font-mono shrink-0 font-medium">${Number(v.price).toFixed(2)}</span> : null}
            </div>
          ))}
        </div>
      );
    }

    const catalogParts = result.catalog_parts as Array<Record<string, unknown>> | undefined;
    const webResults = result.web_results as Array<Record<string, unknown>> | undefined;
    const hasParts = (catalogParts?.length || 0) + (webResults?.length || 0) > 0;
    return (
      <div className="bg-muted/50 rounded-md p-2 mt-1 text-xs space-y-1">
        {matched && (
          <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
            Parts — {matched}{partSearched ? ` (${partSearched})` : ""}
          </p>
        )}
        {!hasParts ? (
          <p className="text-muted-foreground">No parts found.</p>
        ) : (
          <>
            {catalogParts && catalogParts.length > 0 && catalogParts.slice(0, 5).map((p, i) => (
              <div key={`c${i}`} className="flex justify-between gap-2">
                <span>{p.name as string}</span>
                {p.sku ? <span className="text-muted-foreground shrink-0">{String(p.sku)}</span> : null}
              </div>
            ))}
            {webResults && webResults.length > 0 && (
              <>
                <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground mt-1.5">Online</p>
                {webResults.slice(0, 5).map((r, i) => (
                  <div key={`w${i}`} className="flex justify-between gap-2">
                    {r.url ? (
                      <a href={String(r.url)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline truncate">
                        {r.name as string}
                      </a>
                    ) : (
                      <span className="truncate">{r.name as string}</span>
                    )}
                    {r.price ? <span className="font-mono shrink-0">${Number(r.price).toFixed(2)}</span> : null}
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>
    );
  }

  if (name === "draft_broadcast_email" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    return <BroadcastPreviewCard preview={preview} stale={stale} isLastOfType={isLastOfType} />;
  }

  if (name === "draft_customer_email" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    return <CustomerEmailPreviewCard preview={preview} stale={stale} isLastOfType={isLastOfType} />;
  }

  if (name === "add_equipment_to_pool" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    return <ConfirmCard
      title="Add equipment"
      endpoint="/v1/deepblue/confirm-add-equipment"
      payload={preview}
      summary={`${preview.equipment_type}: ${preview.brand} ${preview.model}`}
      subtitle={`On ${preview.bow_name} — ${preview.property_address}`}
      stale={stale}
      isLastOfType={isLastOfType}
    />;
  }

  if (name === "log_chemical_reading" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    const readings = preview.readings as Record<string, number>;
    const summary = Object.entries(readings).map(([k, v]) => `${k}: ${v}`).join(", ");
    return <ConfirmCard
      title="Log chemical reading"
      endpoint="/v1/deepblue/confirm-log-reading"
      payload={preview}
      summary={summary}
      subtitle={preview.property_address as string}
      stale={stale}
      isLastOfType={isLastOfType}
    />;
  }

  if (name === "update_customer_note" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    return <ConfirmCard
      title="Add note to customer"
      endpoint="/v1/deepblue/confirm-update-note"
      payload={preview}
      summary={preview.appending as string}
      subtitle={`For ${preview.customer_name}`}
      stale={stale}
      isLastOfType={isLastOfType}
    />;
  }

  if (name === "create_case" && result.requires_confirmation) {
    const preview = result.preview as Record<string, unknown> | undefined;
    if (!preview) return null;
    return <CreateCaseCard preview={preview} stale={stale} isLastOfType={isLastOfType} />;
  }

  return null;
}

function CreateCaseCard({ preview, stale = false, isLastOfType = true }: { preview: Record<string, unknown>; stale?: boolean; isLastOfType?: boolean }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [caseResult, setCaseResult] = useState<{ case_id: string; case_number: number } | null>(null);
  const locked = saved || stale;

  const handleConfirm = async () => {
    setSaving(true);
    try {
      const res = await api.post<{ case_id: string; case_number: number; title: string }>(
        "/v1/deepblue/confirm-create-case",
        {
          title: preview.title,
          customer_id: preview.customer_id,
          priority: preview.priority || "normal",
        }
      );
      setCaseResult(res);
      setSaved(true);
      toast.success(`Case #${res.case_number} created`);
    } catch {
      toast.error("Failed to create case");
    } finally {
      setSaving(false);
    }
  };

  const priorityLabel = String(preview.priority || "normal").replace(/\b\w/g, c => c.toUpperCase());

  return (
    <div className="bg-muted/50 rounded-md p-2.5 mt-1.5 text-xs space-y-2 border border-primary/20">
      <div className="flex items-center gap-1.5">
        <FolderOpen className="h-3 w-3 text-primary" />
        <span className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">Create Case</span>
      </div>
      <div>
        <p className="font-medium">{String(preview.title)}</p>
        <p className="text-muted-foreground mt-0.5">
          {String(preview.customer_name)} · {priorityLabel} priority
        </p>
      </div>
      {saved && caseResult ? (
        <p className="text-green-600 text-[10px] font-medium pt-1 border-t">
          Case #{caseResult.case_number} created ✓
        </p>
      ) : stale ? (
        <p className={`text-[10px] pt-1 border-t ${isLastOfType ? "text-green-600 font-medium" : "text-muted-foreground"}`}>
          {isLastOfType ? "Created ✓" : "Revised below"}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" className="h-8 flex-1" onClick={handleConfirm} disabled={saving}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
            Create Case
          </Button>
        </div>
      )}
    </div>
  );
}

export function ConfirmCard({
  title, endpoint, payload, summary, subtitle, stale = false, isLastOfType = true,
}: {
  title: string;
  endpoint: string;
  payload: Record<string, unknown>;
  summary: string;
  subtitle?: string;
  stale?: boolean;
  isLastOfType?: boolean;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const locked = saved || cancelled || stale;

  const handleConfirm = async () => {
    setSaving(true);
    try {
      const resp = await fetch(`/api${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error();
      setSaved(true);
      toast.success("Saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-muted/50 rounded-md p-2.5 mt-1.5 text-xs space-y-2 border border-primary/20">
      <p className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">{title}</p>
      <div>
        <p className="font-medium whitespace-pre-wrap">{summary}</p>
        {subtitle && <p className="text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
      {saved ? (
        <p className="text-green-600 text-[10px] font-medium pt-1 border-t">Saved ✓</p>
      ) : cancelled ? (
        <p className="text-muted-foreground text-[10px] pt-1 border-t">Cancelled</p>
      ) : stale ? (
        <p className={`text-[10px] pt-1 border-t ${isLastOfType ? "text-green-600 font-medium" : "text-muted-foreground"}`}>
          {isLastOfType ? "Saved ✓" : "Revised below"}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" className="h-8 flex-1" onClick={handleConfirm} disabled={saving}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
            Confirm
          </Button>
          <Button variant="ghost" size="sm" className="h-8" onClick={() => setCancelled(true)}>Cancel</Button>
        </div>
      )}
    </div>
  );
}

export function BroadcastPreviewCard({ preview, stale = false, isLastOfType = true }: { preview: Record<string, unknown>; stale?: boolean; isLastOfType?: boolean }) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [result, setResult] = useState<{ sent_count: number; failed_count: number } | null>(null);
  const [subject, setSubject] = useState(String(preview.subject));
  const [body, setBody] = useState(String(preview.body));
  const edited = subject !== String(preview.subject) || body !== String(preview.body);

  const handleConfirm = async () => {
    setSending(true);
    try {
      const res = await api.post<{ sent_count: number; failed_count: number; recipient_count: number }>(
        "/v1/deepblue/confirm-broadcast",
        {
          subject,
          body,
          filter_type: preview.filter_type,
          customer_ids: preview.customer_ids,
          test_recipient: preview.test_recipient,
        }
      );
      setResult(res);
      setSent(true);
      toast.success(res.sent_count > 0 ? `Sent to ${res.sent_count}` : "Send failed");
    } catch {
      toast.error("Failed to send broadcast");
    } finally {
      setSending(false);
    }
  };

  const isTest = preview.filter_type === "test";
  const customerNames = preview.customer_names as string[] | undefined;
  const count = Number(preview.recipient_count || 0);
  const locked = sent || cancelled || stale;

  return (
    <div className={`bg-muted/50 rounded-md p-2.5 mt-1.5 text-xs space-y-2 border ${edited && !locked ? "border-amber-400" : "border-primary/20"}`}>
      <div className="flex items-center gap-1.5">
        <Mail className="h-3 w-3 text-primary" />
        <span className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
          {isTest ? "Test Email Preview" : "Broadcast Preview"}
          {edited && !locked && <span className="text-amber-600 ml-1">(edited)</span>}
        </span>
      </div>
      <div className="space-y-1.5">
        {locked ? (
          <>
            <p className="font-medium">{subject}</p>
            <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{body}</p>
          </>
        ) : (
          <>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full font-medium bg-background border rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={Math.min(Math.max(body.split("\n").length, 3), 10)}
              className="w-full text-muted-foreground bg-background border rounded px-2 py-1.5 text-xs leading-relaxed focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none"
            />
          </>
        )}
      </div>
      <div className="pt-1 border-t space-y-1">
        <p className="text-muted-foreground">
          Sending to: <span className="font-medium text-foreground">{String(preview.filter_label)}</span>
        </p>
        {customerNames && customerNames.length > 0 && !isTest && (
          <p className="text-[10px] text-muted-foreground">
            {customerNames.slice(0, 8).join(", ")}
            {customerNames.length > 8 ? ` and ${customerNames.length - 8} more` : ""}
          </p>
        )}
      </div>
      {sent && result ? (
        <p className="text-green-600 text-[10px] font-medium pt-1 border-t">
          {isTest
            ? (result.sent_count > 0 ? "Test email sent ✓" : "Test email failed")
            : `Sent to ${result.sent_count} customer${result.sent_count !== 1 ? "s" : ""}${result.failed_count > 0 ? ` (${result.failed_count} failed)` : ""} ✓`
          }
        </p>
      ) : cancelled ? (
        <p className="text-muted-foreground text-[10px] pt-1 border-t">Cancelled</p>
      ) : stale ? (
        <p className={`text-[10px] pt-1 border-t ${isLastOfType ? "text-green-600 font-medium" : "text-muted-foreground"}`}>
          {isLastOfType ? "Sent ✓" : "Revised below"}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" className="h-8 flex-1" onClick={handleConfirm} disabled={sending || !subject.trim() || !body.trim()}>
            {sending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Send className="h-3 w-3 mr-1" />}
            {isTest ? "Send test email" : `Send to ${count} customer${count !== 1 ? "s" : ""}`}
          </Button>
          <Button variant="ghost" size="sm" className="h-8" onClick={() => setCancelled(true)}>Cancel</Button>
        </div>
      )}
    </div>
  );
}

export function CustomerEmailPreviewCard({ preview, stale = false, isLastOfType = true }: { preview: Record<string, unknown>; stale?: boolean; isLastOfType?: boolean }) {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [subject, setSubject] = useState(String(preview.subject));
  const [body, setBody] = useState(String(preview.body));
  const edited = subject !== String(preview.subject) || body !== String(preview.body);
  const locked = sent || cancelled || stale;

  const handleSend = async () => {
    setSending(true);
    try {
      await api.post("/v1/deepblue/confirm-customer-email", {
        customer_id: preview.customer_id,
        subject,
        body,
      });
      setSent(true);
      toast.success(`Email sent to ${preview.customer_name}`);
    } catch {
      toast.error("Failed to send email");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={`bg-muted/50 rounded-md p-2.5 mt-1.5 text-xs space-y-2 border ${edited && !locked ? "border-amber-400" : "border-primary/20"}`}>
      <div className="flex items-center gap-1.5">
        <Mail className="h-3 w-3 text-primary" />
        <span className="font-medium text-[10px] uppercase tracking-wide text-muted-foreground">
          Email to {String(preview.customer_name)}
          {edited && !locked && <span className="text-amber-600 ml-1">(edited)</span>}
        </span>
      </div>
      <p className="text-[10px] text-muted-foreground">{String(preview.to_email)}</p>
      <div className="space-y-1.5">
        {locked ? (
          <>
            <p className="font-medium">{subject}</p>
            <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{body}</p>
          </>
        ) : (
          <>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full font-medium bg-background border rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={Math.min(Math.max(body.split("\n").length, 3), 10)}
              className="w-full text-muted-foreground bg-background border rounded px-2 py-1.5 text-xs leading-relaxed focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none"
            />
          </>
        )}
      </div>
      {sent ? (
        <p className="text-green-600 text-[10px] font-medium pt-1 border-t">Sent to {String(preview.customer_name)} ✓</p>
      ) : cancelled ? (
        <p className="text-muted-foreground text-[10px] pt-1 border-t">Cancelled</p>
      ) : stale ? (
        <p className={`text-[10px] pt-1 border-t ${isLastOfType ? "text-green-600 font-medium" : "text-muted-foreground"}`}>
          {isLastOfType ? `Sent to ${String(preview.customer_name)} ✓` : "Revised below"}
        </p>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" className="h-8 flex-1" onClick={handleSend} disabled={sending || !subject.trim() || !body.trim()}>
            {sending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Send className="h-3 w-3 mr-1" />}
            Send Email
          </Button>
          <Button variant="ghost" size="sm" className="h-8" onClick={() => setCancelled(true)}>Cancel</Button>
        </div>
      )}
    </div>
  );
}
