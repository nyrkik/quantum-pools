"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Info } from "lucide-react";
import { LineItemsEditor, type LineItem } from "@/components/invoices/line-items-editor";
import { InvoiceSummary } from "@/components/invoices/invoice-summary";

function today() {
  return new Date().toISOString().split("T")[0];
}

function plus30() {
  return new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0];
}

interface InvoiceResponse {
  id: string;
  customer_id: string;
  subject: string | null;
  issue_date: string;
  due_date: string;
  tax_rate: number;
  discount: number;
  notes: string | null;
  line_items: {
    description: string;
    quantity: number;
    unit_price: number;
    is_taxed: boolean;
    sort_order: number;
  }[];
}

interface DraftResponse {
  customer_id: string | null;
  customer_name: string;
  subject: string;
  line_items: { description: string; quantity: number; unit_price: number }[];
  notes: string;
}

function NewInvoiceForm() {
  const router = useRouter();
  const params = useSearchParams();

  const jobId = params.get("job");
  const editId = params.get("edit");
  const preCustomer = params.get("customer");
  const preType = params.get("type") as "estimate" | "invoice" | null;

  const [docType, setDocType] = useState<"estimate" | "invoice">(preType || "invoice");
  const [customerId, setCustomerId] = useState(preCustomer || "");
  const [subject, setSubject] = useState("");
  const [issueDate, setIssueDate] = useState(today());
  const [dueDate, setDueDate] = useState(plus30());
  const [taxRate, setTaxRate] = useState(0);
  const [discount, setDiscount] = useState(0);
  const [notes, setNotes] = useState("");
  const [lineItems, setLineItems] = useState<LineItem[]>([
    { description: "", quantity: 1, unit_price: 0, is_taxed: false },
  ]);
  const [sendTo, setSendTo] = useState("");
  const [aiDrafted, setAiDrafted] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(false);

  const isEdit = !!editId;
  const label = docType === "estimate" ? "Estimate" : "Invoice";

  // Load existing invoice for editing
  const loadExisting = useCallback(async () => {
    if (!editId) return;
    setLoadingEdit(true);
    try {
      const inv = await api.get<InvoiceResponse>(`/v1/invoices/${editId}`);
      setCustomerId(inv.customer_id);
      setSubject(inv.subject || "");
      setIssueDate(inv.issue_date);
      setDueDate(inv.due_date);
      setTaxRate(inv.tax_rate || 0);
      setDiscount(inv.discount || 0);
      setNotes(inv.notes || "");
      if (inv.line_items.length > 0) {
        setLineItems(
          inv.line_items.map((li) => ({
            description: li.description,
            quantity: li.quantity,
            unit_price: li.unit_price,
            is_taxed: li.is_taxed,
          }))
        );
      }
    } catch {
      toast.error("Failed to load invoice");
    } finally {
      setLoadingEdit(false);
    }
  }, [editId]);

  // AI draft from job
  const loadAiDraft = useCallback(async () => {
    if (!jobId || editId) return;
    setDraftLoading(true);
    try {
      const result = await api.post<DraftResponse>(
        `/v1/admin/agent-actions/${jobId}/draft-invoice`,
        {}
      );
      if (result.customer_id) setCustomerId(result.customer_id);
      if (result.subject) setSubject(result.subject);
      if (result.notes) setNotes(result.notes);
      if (result.line_items?.length > 0) {
        setLineItems(
          result.line_items.map((li) => ({
            description: li.description,
            quantity: li.quantity,
            unit_price: li.unit_price,
            is_taxed: false,
          }))
        );
      }
      setAiDrafted(true);
    } catch {
      toast.error("AI draft failed — fill in manually");
    } finally {
      setDraftLoading(false);
    }
  }, [jobId, editId]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  useEffect(() => {
    loadAiDraft();
  }, [loadAiDraft]);

  // Fetch customer email when customer changes
  useEffect(() => {
    if (!customerId) { setSendTo(""); return; }
    api.get<{ email: string | null }>(`/v1/customers/${customerId}`)
      .then((c) => { if (c.email && !sendTo) setSendTo(c.email); })
      .catch(() => {});
  }, [customerId]);

  const handleSubmit = async () => {
    if (!customerId) {
      toast.error("Select a client");
      return;
    }
    const validItems = lineItems.filter((li) => li.description.trim());
    if (validItems.length === 0) {
      toast.error("Add at least one line item");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        customer_id: customerId,
        document_type: docType,
        subject: subject || undefined,
        issue_date: issueDate,
        due_date: dueDate,
        tax_rate: taxRate,
        discount,
        notes: notes || undefined,
        line_items: validItems.map((li, i) => ({
          description: li.description,
          quantity: li.quantity,
          unit_price: li.unit_price,
          is_taxed: li.is_taxed,
          sort_order: i,
        })),
      };

      let invoiceId: string;

      if (isEdit) {
        await api.put(`/v1/invoices/${editId}`, payload);
        invoiceId = editId;
        toast.success(`${label} updated`);
      } else {
        const result = await api.post<{ id: string }>("/v1/invoices", payload);
        invoiceId = result.id;
        toast.success(`${label} created`);

        // Link to job if applicable
        if (jobId && invoiceId) {
          await api
            .put(`/v1/admin/agent-actions/${jobId}`, { invoice_id: invoiceId } as Record<string, string>)
            .catch(() => {});
        }
      }

      router.push(`/invoices/${invoiceId}`);
    } catch (err: unknown) {
      toast.error((err as { message?: string })?.message || `Failed to ${isEdit ? "update" : "create"} ${label.toLowerCase()}`);
    } finally {
      setSaving(false);
    }
  };

  const handleBack = () => {
    if (window.history.length > 1) {
      router.back();
    } else {
      router.push(jobId ? "/jobs" : "/invoices");
    }
  };

  if (loadingEdit) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="pb-24">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="icon" onClick={() => handleBack()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">
            {isEdit ? `Edit ${label}` : `New ${label}`}
          </h1>
        </div>
        {/* Document type toggle */}
        {!isEdit && (
          <div className="flex rounded-md border">
            <button
              type="button"
              className={`px-3 py-1.5 text-sm font-medium rounded-l-md transition-colors ${
                docType === "estimate"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setDocType("estimate")}
            >
              Estimate
            </button>
            <button
              type="button"
              className={`px-3 py-1.5 text-sm font-medium rounded-r-md transition-colors ${
                docType === "invoice"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setDocType("invoice")}
            >
              Invoice
            </button>
          </div>
        )}
      </div>

      {/* AI draft banner */}
      {aiDrafted && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/30 p-3">
          <Info className="h-4 w-4 text-blue-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-blue-800 dark:text-blue-200">
            AI drafted this {label.toLowerCase()} from job context. Review and edit before {isEdit ? "saving" : "creating"}.
          </p>
        </div>
      )}

      {/* Draft loading */}
      {draftLoading && (
        <div className="mb-4 flex items-center gap-2 rounded-md border p-3">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">AI is drafting the {label.toLowerCase()}...</p>
        </div>
      )}

      {/* Main layout — single column, logical order */}
      <div className="max-w-2xl space-y-4">
        {/* 1. Client + Details */}
        <InvoiceSummary
          customerId={customerId}
          onCustomerChange={setCustomerId}
          subject={subject}
          onSubjectChange={setSubject}
          issueDate={issueDate}
          onIssueDateChange={setIssueDate}
          dueDate={dueDate}
          onDueDateChange={setDueDate}
          taxRate={taxRate}
          onTaxRateChange={setTaxRate}
          discount={discount}
          onDiscountChange={setDiscount}
          notes={notes}
          onNotesChange={setNotes}
          lineItems={lineItems}
          section="top"
        />

        {/* Send To — for estimates */}
        {docType === "estimate" && (
          <Card className="shadow-sm">
            <CardContent className="py-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Send Estimate To</label>
                <input
                  type="email"
                  value={sendTo}
                  onChange={(e) => setSendTo(e.target.value)}
                  placeholder="recipient@email.com"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
            </CardContent>
          </Card>
        )}

        {/* 2. Line Items */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Line Items</CardTitle>
              {lineItems.length > 0 && (
                <Badge variant="secondary" className="text-xs">
                  {lineItems.filter((li) => li.description.trim()).length} item{lineItems.filter((li) => li.description.trim()).length !== 1 ? "s" : ""}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <LineItemsEditor items={lineItems} onChange={setLineItems} />
          </CardContent>
        </Card>

        {/* 3. Tax/Discount, Notes, Totals */}
        <InvoiceSummary
          customerId={customerId}
          onCustomerChange={setCustomerId}
          subject={subject}
          onSubjectChange={setSubject}
          issueDate={issueDate}
          onIssueDateChange={setIssueDate}
          dueDate={dueDate}
          onDueDateChange={setDueDate}
          taxRate={taxRate}
          onTaxRateChange={setTaxRate}
          discount={discount}
          onDiscountChange={setDiscount}
          notes={notes}
          onNotesChange={setNotes}
          lineItems={lineItems}
          section="bottom"
        />
      </div>

      {/* Sticky footer */}
      <div className="fixed bottom-0 left-0 right-0 border-t bg-background z-40">
        <div className="flex items-center justify-between flex-wrap gap-2 px-4 sm:px-6 py-3 max-w-screen-2xl mx-auto">
          <Button variant="ghost" onClick={() => handleBack()}>
            Cancel
          </Button>
          <div className="flex flex-wrap gap-2">
            {docType === "estimate" && !isEdit && (
              <Button variant="outline" onClick={async () => {
                const validItems = lineItems.filter((li) => li.description.trim());
                if (!customerId) { toast.error("Select a client"); return; }
                setSaving(true);
                try {
                  const result = await api.post<{ id: string }>("/v1/invoices", {
                    customer_id: customerId, document_type: "estimate", subject: subject || undefined,
                    issue_date: issueDate, due_date: dueDate, status: "draft",
                    tax_rate: taxRate, discount, notes: notes || undefined,
                    line_items: validItems.map((li, i) => ({ description: li.description, quantity: li.quantity, unit_price: li.unit_price, is_taxed: li.is_taxed, sort_order: i })),
                  });
                  if (jobId) await api.put(`/v1/admin/agent-actions/${jobId}`, { invoice_id: result.id }).catch(() => {});
                  toast.success("Draft saved");
                  router.push(jobId ? "/jobs" : "/invoices");
                } catch { toast.error("Failed to save draft"); }
                finally { setSaving(false); }
              }} disabled={saving || !customerId}>
                Save Draft
              </Button>
            )}
            <Button variant="outline" onClick={handleSubmit} disabled={saving || !customerId}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              {isEdit ? "Save Changes" : `Create ${label}`}
            </Button>
            {docType === "estimate" && !isEdit && jobId && (
              <Button onClick={async () => {
                if (!customerId) { toast.error("Select a client"); return; }
                const validItems = lineItems.filter((li) => li.description.trim());
                if (validItems.length === 0) { toast.error("Add at least one line item"); return; }
                setSaving(true);
                try {
                  // Create the estimate
                  const result = await api.post<{ id: string }>("/v1/invoices", {
                    customer_id: customerId, document_type: "estimate", subject: subject || undefined,
                    issue_date: issueDate, due_date: dueDate,
                    tax_rate: taxRate, discount, notes: notes || undefined,
                    line_items: validItems.map((li, i) => ({ description: li.description, quantity: li.quantity, unit_price: li.unit_price, is_taxed: li.is_taxed, sort_order: i })),
                  });
                  // Link to job
                  await api.put(`/v1/admin/agent-actions/${jobId}`, { invoice_id: result.id }).catch(() => {});
                  // Send to customer
                  await api.post(`/v1/admin/agent-actions/${jobId}/send-estimate`, { to_email: sendTo || undefined });
                  toast.success("Estimate created & sent to customer");
                  router.push("/jobs");
                } catch {
                  toast.error("Failed to create & send");
                } finally {
                  setSaving(false);
                }
              }} disabled={saving || !customerId}>
                {saving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                Create & Send
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function NewInvoicePage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <NewInvoiceForm />
    </Suspense>
  );
}
