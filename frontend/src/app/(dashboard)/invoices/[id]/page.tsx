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
  invoice_number: string;
  customer_id: string;
  customer_name: string;
  subject: string | null;
  status: string;
  issue_date: string;
  due_date: string;
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
  created_at: string;
  line_items: InvoiceLineItem[];
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
  const [payments, setPayments] = useState<Payment[]>([]);
  const [payDialogOpen, setPayDialogOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("check");

  const fetchData = useCallback(async () => {
    try {
      const [inv, payData] = await Promise.all([
        api.get<Invoice>(`/v1/invoices/${id}`),
        api.get<{ items: Payment[] }>(`/v1/payments?invoice_id=${id}`),
      ]);
      setInvoice(inv);
      setPayments(payData.items);
    } catch {
      toast.error("Failed to load invoice");
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSend = async () => {
    try {
      await api.post(`/v1/invoices/${id}/send`);
      toast.success("Invoice sent");
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

  if (!invoice) {
    return (
      <div className="flex items-center justify-center py-20">Loading...</div>
    );
  }

  const canSend = ["draft", "sent"].includes(invoice.status);
  const canPay = ["sent", "overdue"].includes(invoice.status);
  const canVoid = ["draft", "sent", "overdue"].includes(invoice.status);
  const canWriteOff = ["sent", "overdue"].includes(invoice.status);
  const today = new Date().toISOString().split("T")[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              {invoice.invoice_number}
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
          </div>
          <InvoiceStatusBadge status={invoice.status} />
        </div>
        <div className="flex items-center gap-2">
          {canSend && (
            <Button variant="outline" size="sm" onClick={handleSend}>
              <Send className="mr-2 h-4 w-4" />
              {invoice.status === "sent" ? "Resend" : "Send"}
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
                        <SelectContent>
                          <SelectItem value="check">Check</SelectItem>
                          <SelectItem value="cash">Cash</SelectItem>
                          <SelectItem value="credit_card">
                            Credit Card
                          </SelectItem>
                          <SelectItem value="ach">ACH</SelectItem>
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
                        Void Invoice
                      </DropdownMenuItem>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Void Invoice?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will void invoice {invoice.invoice_number}. This
                          action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleVoid}>
                          Void Invoice
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

      {/* Payment History */}
      <Card>
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
      </Card>
    </div>
  );
}
