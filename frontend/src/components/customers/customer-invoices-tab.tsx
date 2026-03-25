"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Invoice } from "./customer-types";

interface CustomerInvoicesTabProps {
  invoices: Invoice[];
}

export function CustomerInvoicesTab({ invoices }: CustomerInvoicesTabProps) {
  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Invoices</CardTitle>
      </CardHeader>
      <CardContent>
        {invoices.length === 0 ? (
          <p className="text-center text-muted-foreground py-4 text-sm">No invoices yet</p>
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
      </CardContent>
    </Card>
  );
}
