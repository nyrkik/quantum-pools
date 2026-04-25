"use client";

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
import Link from "next/link";
import {
  CheckCircle2,
  History,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

// --- Types ---

export interface InvoiceLineItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
  is_taxed: boolean;
  sort_order: number;
}

export interface Invoice {
  id: string;
  case_id: string | null;
  case_number?: string | null;
  case_title?: string | null;
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
  internal_notes: string | null;
  sent_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  revision_count: number;
  revised_at: string | null;
  created_at: string;
  line_items: InvoiceLineItem[];
}

export interface Revision {
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

export interface Payment {
  id: string;
  amount: number;
  payment_method: string;
  payment_date: string;
  status: string;
  reference_number: string | null;
  notes: string | null;
  created_at: string;
}

// --- Details Card ---

interface DetailsCardProps {
  invoice: Invoice;
  isEstimate: boolean;
  docLabel: string;
}

export function DetailsCard({ invoice, isEstimate, docLabel }: DetailsCardProps) {
  return (
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
  );
}

// --- Financial Summary Card ---

interface FinancialSummaryCardProps {
  invoice: Invoice;
  isEstimate: boolean;
}

export function FinancialSummaryCard({ invoice, isEstimate }: FinancialSummaryCardProps) {
  return (
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
  );
}

// --- Line Items Table ---

interface LineItemsTableProps {
  lineItems: InvoiceLineItem[];
}

export function LineItemsTable({ lineItems }: LineItemsTableProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Line Items</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Description</TableHead>
              <TableHead className="text-right hidden sm:table-cell">Qty</TableHead>
              <TableHead className="text-right hidden sm:table-cell">Unit Price</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="hidden sm:table-cell">Tax</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lineItems.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="text-center py-4 text-muted-foreground"
                >
                  No line items
                </TableCell>
              </TableRow>
            ) : (
              lineItems.map((li, i) => (
                <TableRow key={li.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                  {/* Description wraps so long item text doesn't push the
                      table off-screen on mobile (FB-51). On phones Qty /
                      Unit Price / Tax columns are hidden because the
                      space they ate left description with no room to
                      wrap usefully — those columns return at sm+. */}
                  <TableCell className="whitespace-normal">
                    <div>{li.description}</div>
                    <div className="text-[11px] text-muted-foreground sm:hidden mt-0.5">
                      {li.quantity} × ${li.unit_price.toFixed(2)}
                      {li.is_taxed && <span className="ml-1.5">· Taxed</span>}
                    </div>
                  </TableCell>
                  <TableCell className="text-right hidden sm:table-cell">{li.quantity}</TableCell>
                  <TableCell className="text-right hidden sm:table-cell">
                    ${li.unit_price.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right">
                    ${li.amount.toFixed(2)}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
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
  );
}

// --- Revision History ---

interface RevisionHistoryProps {
  revisions: Revision[];
  expandedRevision: string | null;
  onToggleRevision: (id: string) => void;
}

export function RevisionHistory({ revisions, expandedRevision, onToggleRevision }: RevisionHistoryProps) {
  if (revisions.length === 0) return null;

  return (
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
              onClick={() => onToggleRevision(rev.id)}
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
  );
}

// --- Payment History ---

interface PaymentHistoryProps {
  payments: Payment[];
}

export function PaymentHistory({ payments }: PaymentHistoryProps) {
  return (
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
  );
}
