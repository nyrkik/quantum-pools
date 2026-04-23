"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  Send,
  DollarSign,
  MoreHorizontal,
  Ban,
  XCircle,
  Pencil,
  CheckCircle2,
  ArrowRightLeft,
  Loader2,
  AlertTriangle,
  Trash2,
  ExternalLink,
  Download,
} from "lucide-react";
import { InvoiceStatusBadge } from "@/components/badges/invoice-status-badge";
import {
  DetailsCard,
  FinancialSummaryCard,
  LineItemsTable,
  RevisionHistory,
  PaymentHistory,
} from "@/components/invoices/invoice-detail-components";
import type { Invoice, Payment, Revision } from "@/components/invoices/invoice-detail-components";
import { LinkCasePicker } from "@/components/cases/link-case-picker";
import { BackButton } from "@/components/ui/back-button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [payDialogOpen, setPayDialogOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("check");
  const [converting, setConverting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [expandedRevision, setExpandedRevision] = useState<string | null>(null);
  const [approvalToken, setApprovalToken] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const inv = await api.get<Invoice>(`/v1/invoices/${id}`);
      setInvoice(inv);
      try {
        const payData = await api.get<{ items: Payment[] }>(`/v1/payments?invoice_id=${id}`);
        setPayments(payData.items);
      } catch { /* payments non-critical */ }
      try {
        const revData = await api.get<Revision[]>(`/v1/invoices/${id}/revisions`);
        setRevisions(revData);
      } catch { /* revisions non-critical */ }
      try {
        const approval = await api.get<{ has_approval_record?: boolean; approval_token?: string }>(`/v1/invoices/${id}/approval`);
        if (approval.has_approval_record) setApprovalToken(approval.approval_token || null);
      } catch { /* non-critical */ }
    } catch {
      setNotFound(true);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSend = async () => {
    try {
      await api.post(`/v1/invoices/${id}/send`);
      toast.success(`${invoice?.document_type === "estimate" ? "Estimate" : "Invoice"} sent`);
      fetchData();
    } catch {
      toast.error("Failed to send invoice");
    }
  };

  const handleVoid = async () => {
    try {
      await api.post(`/v1/invoices/${id}/void`);
      toast.success("Invoice voided");
      fetchData();
    } catch {
      toast.error("Failed to void invoice");
    }
  };

  const handleWriteOff = async () => {
    try {
      await api.post(`/v1/invoices/${id}/write-off`);
      toast.success("Invoice written off");
      fetchData();
    } catch {
      toast.error("Failed to write off invoice");
    }
  };

  const handlePayment = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = {
      customer_id: invoice!.customer_id,
      invoice_id: id,
      amount: parseFloat(form.get("amount") as string),
      payment_method: paymentMethod,
      payment_date: form.get("payment_date") as string,
      reference_number: (form.get("reference_number") as string) || undefined,
      notes: (form.get("notes") as string) || undefined,
    };
    try {
      await api.post("/v1/payments", body);
      toast.success("Payment recorded");
      setPayDialogOpen(false);
      fetchData();
    } catch {
      toast.error("Failed to record payment");
    }
  };

  const handleDelete = async () => {
    try {
      await api.delete(`/v1/invoices/${id}`);
      toast.success("Draft deleted");
      router.push(invoice?.document_type === "estimate" ? "/invoices?tab=estimates" : "/invoices");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const handleDownloadPdf = async () => {
    try {
      const res = await fetch(`/api/v1/invoices/${id}/pdf`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to generate PDF");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${invoice?.document_type || "invoice"}_${invoice?.invoice_number || "draft"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download PDF");
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      await api.post(`/v1/invoices/${id}/approve`, {});
      toast.success("Estimate approved");
      fetchData();
    } catch {
      toast.error("Failed to approve estimate");
    } finally {
      setApproving(false);
    }
  };

  const handleConvert = async () => {
    setConverting(true);
    try {
      await api.post(`/v1/invoices/${id}/convert-to-invoice`, {});
      toast.success("Converted to invoice");
      fetchData();
    } catch {
      toast.error("Failed to convert to invoice");
    } finally {
      setConverting(false);
    }
  };

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <p className="text-muted-foreground">Invoice not found</p>
        <Button variant="outline" size="sm" onClick={() => router.push("/invoices")}>Back to Invoices</Button>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="flex items-center justify-center py-20">Loading...</div>
    );
  }

  const isEstimate = invoice.document_type === "estimate";
  const docLabel = isEstimate ? "Estimate" : "Invoice";
  const canEdit = ["draft", "sent", "revised"].includes(invoice.status) && !(isEstimate && invoice.approved_at);
  const canSend = ["draft", "sent", "revised"].includes(invoice.status);
  const canPay = !isEstimate && ["sent", "overdue"].includes(invoice.status);
  const canDelete = invoice.status === "draft";
  // Void is available on anything past draft that isn't already finalized.
  // Backend rejects void on draft/paid; we also exclude already-void and
  // written-off here so the button doesn't show for no-op states.
  const canVoid = !["draft", "void", "paid", "written_off"].includes(invoice.status);
  const canWriteOff = !isEstimate && ["sent", "overdue"].includes(invoice.status);
  const canApprove = isEstimate && !invoice.approved_at && ["sent", "revised", "viewed"].includes(invoice.status);
  const canConvert = isEstimate && !!invoice.approved_at;
  const today = new Date().toISOString().split("T")[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <BackButton fallback={invoice?.document_type === "estimate" ? "/invoices?tab=estimates" : "/invoices"} />
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              {invoice.invoice_number || "Draft"}
            </h1>
            <p className="text-muted-foreground">
              <Link
                href={`/customers/${invoice.customer_id}`}
                className="hover:underline"
              >
                {invoice.customer_name}
              </Link>
              {invoice.subject && ` — ${invoice.subject}`}
            </p>
            <div className="mt-2">
              <LinkCasePicker
                entityType="invoice"
                entityId={invoice.id}
                customerId={invoice.customer_id}
                currentCaseId={invoice.case_id}
                currentCaseNumber={invoice.case_number}
                currentCaseTitle={invoice.case_title}
                onChange={fetchData}
              />
            </div>
          </div>
          <InvoiceStatusBadge status={invoice.status} />
        </div>
        <div className="flex items-center gap-2">
          {canEdit && !isEstimate && ["sent", "revised"].includes(invoice.status) ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm">
                  <Pencil className="mr-2 h-3.5 w-3.5" />
                  Edit
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Edit sent {docLabel.toLowerCase()}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This {docLabel.toLowerCase()} has been sent to the customer. Editing will create a revision and require re-sending the updated version.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => router.push(`/invoices/new?edit=${id}`)}>
                    Edit Anyway
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : canEdit ? (
            <Button variant="outline" size="sm" onClick={() => router.push(`/invoices/new?edit=${id}`)}>
              <Pencil className="mr-2 h-3.5 w-3.5" />
              Edit
            </Button>
          ) : null}
          {canApprove && (
            <Button size="sm" onClick={handleApprove} disabled={approving}>
              {approving ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="mr-2 h-3.5 w-3.5" />}
              Approve
            </Button>
          )}
          {canConvert && (
            <>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Pencil className="mr-2 h-3.5 w-3.5" />
                    Revise
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Revise approved estimate?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will clear the approval so you can make changes. The estimate will need to be re-approved after editing.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={async () => {
                      try {
                        await api.post(`/v1/invoices/${id}/revise`, {});
                        toast.success("Estimate reopened for revision");
                        fetchData();
                      } catch {
                        toast.error("Failed to revise estimate");
                      }
                    }}>
                      Revise
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <Button size="sm" onClick={handleConvert} disabled={converting}>
                {converting ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <ArrowRightLeft className="mr-2 h-3.5 w-3.5" />}
                Convert to Invoice
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" onClick={handleDownloadPdf}>
            <Download className="mr-2 h-3.5 w-3.5" />
            PDF
          </Button>
          {canSend && (
            <Button variant="outline" size="sm" onClick={handleSend}>
              <Send className="mr-2 h-4 w-4" />
              {invoice.status === "sent" ? "Resend" : "Send"}
            </Button>
          )}
          {isEstimate && approvalToken && (
            <Button variant="outline" size="sm" onClick={() => window.open(`/approve/${approvalToken}?view=admin`, "_blank")}>
              <ExternalLink className="mr-2 h-3.5 w-3.5" />
              Open
            </Button>
          )}
          {canPay && (
            <Dialog open={payDialogOpen} onOpenChange={setPayDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <DollarSign className="mr-2 h-4 w-4" />
                  Record Payment
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Record Payment</DialogTitle>
                </DialogHeader>
                <form onSubmit={handlePayment} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label htmlFor="amount">Amount</Label>
                      <Input
                        id="amount"
                        name="amount"
                        type="number"
                        step="0.01"
                        min="0.01"
                        defaultValue={invoice.balance.toFixed(2)}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Method</Label>
                      <Select
                        value={paymentMethod}
                        onValueChange={setPaymentMethod}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent position="popper">
                          <SelectItem value="check">Check</SelectItem>
                          <SelectItem value="cash">Cash</SelectItem>
                          <SelectItem value="credit_card">Credit Card</SelectItem>
                          <SelectItem value="ach">ACH</SelectItem>
                          <SelectItem value="venmo">Venmo</SelectItem>
                          <SelectItem value="zelle">Zelle</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label htmlFor="payment_date">Date</Label>
                      <Input
                        id="payment_date"
                        name="payment_date"
                        type="date"
                        defaultValue={today}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="reference_number">Reference #</Label>
                      <Input
                        id="reference_number"
                        name="reference_number"
                        placeholder="Check # or ref"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="pay_notes">Notes</Label>
                    <Textarea id="pay_notes" name="notes" rows={2} />
                  </div>
                  <Button type="submit" className="w-full">
                    Record Payment
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          )}
          {canDelete && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="text-destructive">
                  <Trash2 className="mr-2 h-3.5 w-3.5" />
                  Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete draft?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This draft has never been sent. It will be permanently deleted.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
          {(canVoid || canWriteOff) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {canVoid && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                        <Ban className="mr-2 h-4 w-4" />
                        Void {docLabel}
                      </DropdownMenuItem>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Void {docLabel}?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will void {docLabel.toLowerCase()} {invoice.invoice_number}. The record will be preserved for audit purposes.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleVoid}>
                          Void {docLabel}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
                {canWriteOff && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                        <XCircle className="mr-2 h-4 w-4" />
                        Write Off
                      </DropdownMenuItem>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Write Off Invoice?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will write off the remaining balance of $
                          {invoice.balance.toFixed(2)} on invoice{" "}
                          {invoice.invoice_number}.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleWriteOff}>
                          Write Off
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {/* Revised banner */}
      {invoice.status === "revised" && !isEstimate && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30 p-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <div className="text-sm">
            <p className="font-medium text-amber-800 dark:text-amber-200">
              Revised — must be re-sent
            </p>
            <p className="text-amber-700 dark:text-amber-300 text-xs mt-0.5">
              This {docLabel.toLowerCase()} was edited after being sent. The customer has an outdated version. Click Send to deliver the updated version.
            </p>
          </div>
        </div>
      )}

      {/* Info Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        <DetailsCard invoice={invoice} isEstimate={isEstimate} docLabel={docLabel} />
        <FinancialSummaryCard invoice={invoice} isEstimate={isEstimate} />
      </div>

      {/* Line Items */}
      <LineItemsTable lineItems={invoice.line_items} />

      {/* Notes */}
      {invoice.notes && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{invoice.notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Internal Notes */}
      {invoice.internal_notes && (
        <Card className="border-l-4 border-amber-400">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-1.5">Internal Notes <span className="text-xs font-normal text-muted-foreground">(not visible to client)</span></CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{invoice.internal_notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Revision History */}
      <RevisionHistory
        revisions={revisions}
        expandedRevision={expandedRevision}
        onToggleRevision={(id) => setExpandedRevision(expandedRevision === id ? null : id)}
      />

      {/* Payment History — invoices only */}
      {!isEstimate && <PaymentHistory payments={payments} />}

    </div>
  );
}
