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
  Card,
  CardContent,
  CardHeader,
  CardTitle,
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
  ArrowLeft,
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
  History,
  ExternalLink,
  Download,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface InvoiceLineItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
  is_taxed: boolean;
  sort_order: number;
}

interface Invoice {
  id: string;
  case_id: string | null;
  invoice_number: string | null;
  customer_id: string;
  customer_name: string;
  subject: string | null;
  document_type: string;
  status: string;
  issue_date: string;
  due_date: string | null;
  paid_date: string | null;
  subtotal: number;
  discount: number;
  tax_rate: number;
  tax_amount: number;
  total: number;
  amount_paid: number;
  balance: number;
  notes: string | null;
  sent_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  revision_count: number;
  revised_at: string | null;
  created_at: string;
  line_items: InvoiceLineItem[];
}

interface Revision {
  id: string;
  revision_number: number;
  invoice_number: string | null;
  revised_by: string | null;
  created_at: string;
  snapshot: {
    total: number;
    subtotal: number;
    line_items: { description: string; quantity: number; unit_price: number; amount: number }[];
  };
}

interface Payment {
  id: string;
  amount: number;
  payment_method: string;
  payment_date: string;
  status: string;
  reference_number: string | null;
  notes: string | null;
  created_at: string;
}

import { InvoiceStatusBadge } from "@/components/badges/invoice-status-badge";

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
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/invoices/${id}/pdf`, {
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
  const canVoid = ["sent", "revised", "overdue"].includes(invoice.status);
  const canWriteOff = !isEstimate && ["sent", "overdue"].includes(invoice.status);
  const canApprove = isEstimate && !invoice.approved_at && ["sent", "revised", "viewed"].includes(invoice.status);
  const canConvert = isEstimate && !!invoice.approved_at;
  const today = new Date().toISOString().split("T")[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.push(invoice.document_type === "estimate" ? "/invoices?tab=estimates" : "/invoices")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
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
            {invoice.case_id && (
              <Badge
                variant="outline"
                className="text-[10px] px-1.5 border-blue-300 text-blue-600 cursor-pointer hover:bg-blue-50 mt-1 w-fit"
                onClick={() => router.push(`/cases/${invoice.case_id}`)}
              >
                View Case
              </Badge>
            )}
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
            <Button size="sm" onClick={handleConvert} disabled={converting}>
              {converting ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <ArrowRightLeft className="mr-2 h-3.5 w-3.5" />}
              Convert to Invoice
            </Button>
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
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>
              <span className="text-muted-foreground">Client: </span>
              <Link
                href={`/customers/${invoice.customer_id}`}
                className="hover:underline"
              >
                {invoice.customer_name}
              </Link>
            </div>
            <div>
              <span className="text-muted-foreground">Issue Date: </span>
              {invoice.issue_date}
            </div>
            {invoice.due_date && (
              <div>
                <span className="text-muted-foreground">Due Date: </span>
                {invoice.due_date}
              </div>
            )}
            {invoice.paid_date && (
              <div>
                <span className="text-muted-foreground">Paid Date: </span>
                {invoice.paid_date}
              </div>
            )}
            {invoice.sent_at && (
              <div>
                <span className="text-muted-foreground">Sent: </span>
                {new Date(invoice.sent_at).toLocaleString()}
              </div>
            )}
            {invoice.revision_count > 0 && (
              <div>
                <span className="text-muted-foreground">Revised: </span>
                {invoice.revision_count} time{invoice.revision_count > 1 ? "s" : ""}
                {invoice.revised_at && ` — ${new Date(invoice.revised_at).toLocaleString()}`}
              </div>
            )}
            {isEstimate && invoice.approved_at && (
              <div className="border-t pt-2 mt-2">
                <div className="flex items-center gap-1.5 text-green-600 font-medium">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Approved
                </div>
                <div className="mt-1">
                  <span className="text-muted-foreground">By: </span>
                  {invoice.approved_by}
                </div>
                <div>
                  <span className="text-muted-foreground">On: </span>
                  {new Date(invoice.approved_at).toLocaleString()}
                </div>
              </div>
            )}
            {isEstimate && !invoice.approved_at && invoice.status !== "void" && (
              <div className="border-t pt-2 mt-2">
                <span className="text-xs text-amber-600 font-medium">Pending Approval</span>
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Financial Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>${invoice.subtotal.toFixed(2)}</span>
            </div>
            {invoice.tax_amount > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  Tax ({invoice.tax_rate}%)
                </span>
                <span>${invoice.tax_amount.toFixed(2)}</span>
              </div>
            )}
            {(invoice.discount || 0) > 0 && (
              <div className="flex justify-between text-red-600">
                <span>Discount</span>
                <span>-${(invoice.discount || 0).toFixed(2)}</span>
              </div>
            )}
            <div className="flex justify-between font-bold border-t pt-2">
              <span>Total</span>
              <span>${invoice.total.toFixed(2)}</span>
            </div>
            {!isEstimate && (
              <>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Paid</span>
                  <span>${invoice.amount_paid.toFixed(2)}</span>
                </div>
                <div className="flex justify-between font-bold border-t pt-2">
                  <span>Balance Due</span>
                  <span
                    className={invoice.balance > 0 ? "text-red-600" : "text-green-600"}
                  >
                    ${invoice.balance.toFixed(2)}
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Line Items */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Line Items</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Unit Price</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Tax</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoice.line_items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center py-4 text-muted-foreground"
                  >
                    No line items
                  </TableCell>
                </TableRow>
              ) : (
                invoice.line_items.map((li, i) => (
                  <TableRow key={li.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                    <TableCell>{li.description}</TableCell>
                    <TableCell className="text-right">{li.quantity}</TableCell>
                    <TableCell className="text-right">
                      ${li.unit_price.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${li.amount.toFixed(2)}
                    </TableCell>
                    <TableCell>
                      {li.is_taxed && (
                        <Badge variant="outline" className="text-xs">
                          Taxed
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

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

      {/* Revision History */}
      {revisions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <History className="h-4 w-4" />
              Revision History ({revisions.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {revisions.map((rev) => (
              <div key={rev.id} className="border rounded-md">
                <button
                  className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-muted/50 transition-colors"
                  onClick={() => setExpandedRevision(expandedRevision === rev.id ? null : rev.id)}
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">{rev.invoice_number}</Badge>
                    <span className="text-muted-foreground">
                      ${rev.snapshot.total.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground text-xs">
                    <span>{rev.revised_by}</span>
                    <span>{new Date(rev.created_at).toLocaleDateString()}</span>
                    {expandedRevision === rev.id ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  </div>
                </button>
                {expandedRevision === rev.id && (
                  <div className="border-t px-3 py-2 bg-muted/30">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">Description</TableHead>
                          <TableHead className="text-xs text-right">Qty</TableHead>
                          <TableHead className="text-xs text-right">Price</TableHead>
                          <TableHead className="text-xs text-right">Amount</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {rev.snapshot.line_items.map((li, i) => (
                          <TableRow key={i}>
                            <TableCell className="text-sm">{li.description}</TableCell>
                            <TableCell className="text-sm text-right">{li.quantity}</TableCell>
                            <TableCell className="text-sm text-right">${li.unit_price.toFixed(2)}</TableCell>
                            <TableCell className="text-sm text-right">${li.amount.toFixed(2)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <div className="flex justify-between text-sm font-medium mt-2 pt-2 border-t">
                      <span>Total at revision</span>
                      <span>${rev.snapshot.total.toFixed(2)}</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Payment History — invoices only */}
      {!isEstimate && <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Payment History ({payments.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Method</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Reference</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center py-4 text-muted-foreground"
                  >
                    No payments recorded
                  </TableCell>
                </TableRow>
              ) : (
                payments.map((p, i) => (
                  <TableRow key={p.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                    <TableCell>{p.payment_date}</TableCell>
                    <TableCell className="capitalize">
                      {p.payment_method.replace("_", " ")}
                    </TableCell>
                    <TableCell className="text-right">
                      ${p.amount.toFixed(2)}
                    </TableCell>
                    <TableCell>{p.reference_number || "—"}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          p.status === "completed" ? "default" : "secondary"
                        }
                        className={
                          p.status === "completed" ? "bg-green-600" : ""
                        }
                      >
                        {p.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>}

    </div>
  );
}
