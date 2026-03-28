"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FileText, Plus } from "lucide-react";
import type { Customer, Invoice } from "../customer-types";

interface BillingSectionProps {
  customerId: string;
  customer: Customer;
  invoices: Invoice[];
}

export function BillingSection({ customerId, customer, invoices }: BillingSectionProps) {
  const router = useRouter();
  const outstandingTotal = invoices.reduce((sum, inv) => sum + inv.balance, 0);

  return (
    <div className="space-y-4">
      {/* Balance callout */}
      {outstandingTotal > 0 && (
        <div className="flex items-center justify-between bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              Outstanding Balance: ${outstandingTotal.toFixed(2)}
            </p>
            <p className="text-xs text-red-600 dark:text-red-400">
              {invoices.filter(i => i.balance > 0).length} invoice{invoices.filter(i => i.balance > 0).length !== 1 ? "s" : ""} with balance
            </p>
          </div>
        </div>
      )}

      {/* Billing info */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Monthly Rate</p>
          <p className="font-medium">${customer.monthly_rate.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Billing Frequency</p>
          <p className="font-medium capitalize">{customer.billing_frequency}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Payment Method</p>
          <p className="font-medium capitalize">{customer.payment_method || "Not set"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Terms</p>
          <p className="font-medium">Net {customer.payment_terms_days}</p>
        </div>
      </div>

      {/* Invoice table + create button */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Invoices</p>
        <Button variant="outline" size="sm" onClick={() => router.push(`/invoices/new?customer=${customerId}`)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Create Invoice
        </Button>
      </div>

      {invoices.length === 0 ? (
        <div className="text-center py-6">
          <FileText className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
          <p className="text-sm text-muted-foreground">No invoices yet</p>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-100 dark:bg-slate-800">
                <TableHead className="text-xs font-medium uppercase tracking-wide">Invoice #</TableHead>
                <TableHead className="hidden sm:table-cell text-xs font-medium uppercase tracking-wide">Subject</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                <TableHead className="hidden sm:table-cell text-xs font-medium uppercase tracking-wide">Issue Date</TableHead>
                <TableHead className="text-right text-xs font-medium uppercase tracking-wide">Total</TableHead>
                <TableHead className="text-right text-xs font-medium uppercase tracking-wide">Balance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.map((inv, i) => (
                <TableRow key={inv.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                  <TableCell>
                    <Link href={`/invoices/${inv.id}`} className="font-medium hover:underline">{inv.invoice_number}</Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground hidden sm:table-cell">{inv.subject || "\u2014"}</TableCell>
                  <TableCell>
                    <Badge
                      variant={inv.status === "paid" ? "default" : inv.status === "overdue" ? "destructive" : "secondary"}
                      className={inv.status === "paid" ? "bg-green-600" : inv.status === "sent" ? "border-blue-400 text-blue-600" : ""}
                    >{inv.status.replace("_", " ")}</Badge>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">{inv.issue_date}</TableCell>
                  <TableCell className="text-right">${inv.total.toFixed(2)}</TableCell>
                  <TableCell className={`text-right ${inv.balance > 0 ? "text-red-600 font-medium" : ""}`}>${inv.balance.toFixed(2)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
