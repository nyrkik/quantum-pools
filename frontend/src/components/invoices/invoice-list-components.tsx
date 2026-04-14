"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Plus,
  Trash2,
  ChevronLeft,
  ChevronRight,
  X,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { InvoiceStatusBadge } from "@/components/badges/invoice-status-badge";

// ── Shared types ──────────────────────────────────────────────────────

export interface Invoice {
  id: string;
  invoice_number: string | null;
  customer_id: string;
  customer_name: string;
  subject: string | null;
  status: string;
  document_type: string;
  issue_date: string;
  due_date: string;
  total: number;
  balance: number;
  approved_at: string | null;
  approved_by: string | null;
}

export interface InvoiceStats {
  total_outstanding: number;
  total_overdue: number;
  monthly_revenue: number;
  invoice_count: number;
  paid_count: number;
  overdue_count: number;
  void_count?: number;
}

export interface MonthlyData {
  month: string;
  paid: number;
  open: number;
}

export interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  company_name: string | null;
}

export interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
  is_taxed: boolean;
}

// ── Monthly Chart ─────────────────────────────────────────────────────

interface MonthlyChartProps {
  monthlyData: MonthlyData[];
  stats: InvoiceStats | null;
  chartYear: number;
  setChartYear: (fn: (y: number) => number) => void;
  selectedMonth: number | null;
  setSelectedMonth: (m: number | null) => void;
  chartSegment: "all" | "paid" | "open";
  setChartSegment: (s: "all" | "paid" | "open") => void;
  hoveredMonth: number | null;
  setHoveredMonth: (m: number | null) => void;
  currentYear: number;
  currentMonth: number;
}

export function MonthlyChart({
  monthlyData,
  stats,
  chartYear,
  setChartYear,
  selectedMonth,
  setSelectedMonth,
  chartSegment,
  setChartSegment,
  hoveredMonth,
  setHoveredMonth,
  currentYear,
  currentMonth,
}: MonthlyChartProps) {
  const chartData = monthlyData.map((m, i) => ({
    ...m,
    isFuture: chartYear > currentYear || (chartYear === currentYear && i > currentMonth),
  }));

  return (
    <Card>
      <CardContent className="pt-4 px-3 sm:px-6">
        <div className="flex items-center justify-between mb-2">
          {/* Paid/Open — left */}
          <div className="flex items-baseline gap-3 sm:gap-5">
            {(() => {
              const activeIdx = selectedMonth ?? hoveredMonth;
              const paid = activeIdx !== null ? (monthlyData[activeIdx]?.paid || 0) : monthlyData.reduce((s, m) => s + m.paid, 0);
              const open = activeIdx !== null ? (monthlyData[activeIdx]?.open || 0) : monthlyData.reduce((s, m) => s + m.open, 0);
              return (
                <>
                  <span className="text-green-700 text-base sm:text-lg font-bold">Paid ${paid.toLocaleString("en-US", { minimumFractionDigits: 0 })}</span>
                  <span className="text-amber-600 text-base sm:text-lg font-bold">Open ${open.toLocaleString("en-US", { minimumFractionDigits: 0 })}</span>
                  {stats && stats.total_overdue > 0 && selectedMonth === null && hoveredMonth === null && (
                    <span className="text-destructive text-base sm:text-lg font-bold">Overdue ${stats.total_overdue.toLocaleString("en-US", { minimumFractionDigits: 0 })}</span>
                  )}
                </>
              );
            })()}
          </div>
          {/* Selected month + year nav — right */}
          <div className="flex items-center gap-2">
            {selectedMonth !== null && (
              <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-green-600 text-white">
                {monthlyData[selectedMonth]?.month}
                <button onClick={() => { setSelectedMonth(null); setChartSegment("all"); }} className="ml-0.5 opacity-70 hover:opacity-100"><X className="h-3 w-3" /></button>
              </span>
            )}
            <div className="flex items-center gap-0.5">
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => { setChartYear((y) => y - 1); setSelectedMonth(null); setChartSegment("all"); }}>
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-sm font-semibold w-10 text-center">{chartYear}</span>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => { setChartYear((y) => y + 1); setSelectedMonth(null); setChartSegment("all"); }} disabled={chartYear >= currentYear}>
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
        {/* Pure CSS bar chart */}
        {(() => {
          const maxVal = Math.max(...chartData.map(d => d.paid + d.open), 1);
          const chartHeight = 160;
          return (
            <div className="flex gap-1 sm:gap-2" style={{ height: chartHeight }} onMouseLeave={() => setHoveredMonth(null)}>
              {chartData.map((d, i) => {
                const total = d.paid + d.open;
                const paidPct = total > 0 ? (d.paid / maxVal) * 100 : 0;
                const openPct = total > 0 ? (d.open / maxVal) * 100 : 0;
                const greyPct = d.isFuture ? 100 : 100 - paidPct - openPct;

                const isSelected = selectedMonth === i;
                const isHovered = hoveredMonth === i;
                const highlighted = isSelected || isHovered;
                const faded = (selectedMonth !== null && !isSelected) || (hoveredMonth !== null && selectedMonth === null && !isHovered);

                return (
                  <div
                    key={i}
                    className={`relative flex-1 flex flex-col items-stretch ${d.isFuture ? "cursor-default" : "cursor-pointer"}`}
                    onMouseEnter={() => !d.isFuture && setHoveredMonth(i)}
                    onMouseLeave={() => setHoveredMonth(null)}
                    onClick={() => {
                      if (d.isFuture) return;
                      setHoveredMonth(null);
                      setSelectedMonth(selectedMonth === i ? null : i);
                      setChartSegment("all");
                    }}
                  >
                    {/* Tooltip on hover */}
                    {isHovered && !d.isFuture && (
                      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-popover/95 backdrop-blur-sm border rounded shadow-md px-2.5 py-1.5 text-[11px] whitespace-nowrap z-20 pointer-events-none">
                        <div className="font-medium mb-0.5">{d.month}</div>
                        <div className="text-green-700">Paid ${d.paid.toLocaleString("en-US", { minimumFractionDigits: 0 })}</div>
                        <div className="text-amber-600">Open ${d.open.toLocaleString("en-US", { minimumFractionDigits: 0 })}</div>
                      </div>
                    )}
                    {/* Bar container — absolute positioning for precise height */}
                    <div className={`flex-1 relative rounded-t overflow-hidden transition-opacity duration-150 ${d.isFuture ? "opacity-40" : highlighted ? "opacity-100" : faded ? "opacity-40" : "opacity-100"}`}>
                      {/* Grey background fills entire bar */}
                      <div className={`absolute inset-0 ${highlighted ? "bg-slate-300" : "bg-slate-200"} transition-colors duration-150`} />
                      {/* Colored segments anchored to bottom */}
                      {(openPct > 0 || paidPct > 0) && (
                        <div className="absolute bottom-0 left-0 right-0 flex flex-col">
                          {openPct > 0 && <div className="bg-amber-400" style={{ height: `${(openPct / 100) * chartHeight}px` }} />}
                          {paidPct > 0 && <div className="bg-green-600" style={{ height: `${(paidPct / 100) * chartHeight}px` }} />}
                        </div>
                      )}
                    </div>
                    <p className="text-[10px] sm:text-[11px] text-center text-muted-foreground mt-1.5 select-none">{d.month}</p>
                  </div>
                );
              })}
            </div>
          );
        })()}
      </CardContent>
    </Card>
  );
}

// ── Create Invoice/Estimate Dialog ────────────────────────────────────

interface CreateInvoiceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  docView: "invoices" | "estimates";
  customers: Customer[];
  selectedCustomerId: string;
  setSelectedCustomerId: (id: string) => void;
  isNonClient: boolean;
  setIsNonClient: (v: boolean) => void;
  billingName: string;
  setBillingName: (v: string) => void;
  billingEmail: string;
  setBillingEmail: (v: string) => void;
  lineItems: LineItem[];
  addLineItem: () => void;
  removeLineItem: (index: number) => void;
  updateLineItem: (index: number, field: keyof LineItem, value: string | number | boolean) => void;
  taxRate: number;
  setTaxRate: (rate: number) => void;
  discount: number;
  setDiscount: (d: number) => void;
  subtotal: number;
  taxAmount: number;
  computedTotal: number;
  today: string;
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
}

export function CreateInvoiceDialog({
  open,
  onOpenChange,
  docView,
  customers,
  selectedCustomerId,
  setSelectedCustomerId,
  isNonClient,
  setIsNonClient,
  billingName,
  setBillingName,
  billingEmail,
  setBillingEmail,
  lineItems,
  addLineItem,
  removeLineItem,
  updateLineItem,
  taxRate,
  setTaxRate,
  discount,
  setDiscount,
  subtotal,
  taxAmount,
  computedTotal,
  today,
  onSubmit,
}: CreateInvoiceDialogProps) {
  const label = docView === "estimates" ? "Estimate" : "Invoice";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Create {label}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>New {label}</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {/* Client toggle */}
          <div className="flex items-center gap-2 text-sm">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={isNonClient}
                onChange={(e) => { setIsNonClient(e.target.checked); if (e.target.checked) setSelectedCustomerId(""); }}
                className="h-4 w-4 rounded border-slate-300"
              />
              <span className="text-muted-foreground">Bill a non-client</span>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {isNonClient ? (
              <>
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input value={billingName} onChange={(e) => setBillingName(e.target.value)} placeholder="Full name or company" required />
                </div>
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input type="email" value={billingEmail} onChange={(e) => setBillingEmail(e.target.value)} placeholder="email@example.com" required />
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <Label>Client</Label>
                <Select value={selectedCustomerId} onValueChange={setSelectedCustomerId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select client" />
                  </SelectTrigger>
                  <SelectContent>
                    {customers.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.first_name} {c.last_name}
                        {c.company_name ? ` (${c.company_name})` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="subject">Subject</Label>
              <Input id="subject" name="subject" placeholder="Monthly pool service" required />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="issue_date">Issue Date</Label>
              <Input id="issue_date" name="issue_date" type="date" defaultValue={today} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="due_date">Due Date</Label>
              <Input
                id="due_date"
                name="due_date"
                type="date"
                defaultValue={new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0]}
                required
              />
            </div>
          </div>

          {/* Line Items */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Line Items</Label>
              <Button type="button" variant="outline" size="sm" onClick={addLineItem}>
                <Plus className="mr-1 h-3 w-3" />
                Add Item
              </Button>
            </div>
            <div className="space-y-2">
              {lineItems.map((item, index) => (
                <div key={index} className="flex items-start gap-2">
                  <Input
                    placeholder="Description"
                    className="flex-1"
                    value={item.description}
                    onChange={(e) => updateLineItem(index, "description", e.target.value)}
                    required={index === 0}
                  />
                  <Input
                    type="number"
                    placeholder="Qty"
                    className="w-20"
                    min="0"
                    step="1"
                    value={item.quantity}
                    onChange={(e) => updateLineItem(index, "quantity", parseFloat(e.target.value) || 0)}
                  />
                  <Input
                    type="number"
                    placeholder="Price"
                    className="w-28"
                    min="0"
                    step="0.01"
                    value={item.unit_price}
                    onChange={(e) => updateLineItem(index, "unit_price", parseFloat(e.target.value) || 0)}
                  />
                  <div className="flex items-center gap-1 pt-2">
                    <Checkbox
                      checked={item.is_taxed}
                      onCheckedChange={(checked) => updateLineItem(index, "is_taxed", checked === true)}
                    />
                    <span className="text-xs text-muted-foreground">Tax</span>
                  </div>
                  <span className="w-20 pt-2 text-right text-sm">
                    ${(item.quantity * item.unit_price).toFixed(2)}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeLineItem(index)}
                    disabled={lineItems.length <= 1}
                    className="px-2"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="tax_rate">Tax Rate (%)</Label>
              <Input
                id="tax_rate"
                type="number"
                min="0"
                step="0.01"
                value={taxRate}
                onChange={(e) => setTaxRate(parseFloat(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount">Discount ($)</Label>
              <Input
                id="discount"
                type="number"
                min="0"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)}
              />
            </div>
          </div>

          <div className="bg-muted/50 rounded-md p-3 text-sm space-y-1">
            <div className="flex justify-between">
              <span>Subtotal</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            {taxRate > 0 && (
              <div className="flex justify-between">
                <span>Tax ({taxRate}%)</span>
                <span>${taxAmount.toFixed(2)}</span>
              </div>
            )}
            {discount > 0 && (
              <div className="flex justify-between text-red-600">
                <span>Discount</span>
                <span>-${discount.toFixed(2)}</span>
              </div>
            )}
            <div className="flex justify-between font-bold border-t pt-1">
              <span>Total</span>
              <span>${computedTotal.toFixed(2)}</span>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" name="notes" rows={2} />
          </div>

          <Button type="submit" className="w-full" disabled={
            (isNonClient ? (!billingName.trim() || !billingEmail.trim()) : !selectedCustomerId)
            || !lineItems.some(li => li.description.trim() && li.unit_price > 0)
          }>
            Create {label}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Invoice Table ─────────────────────────────────────────────────────

interface InvoiceTableProps {
  invoices: Invoice[];
  loading: boolean;
  docView: "invoices" | "estimates";
  onApprove: (id: string) => void;
}

export function InvoiceTable({ invoices, loading, docView, onApprove }: InvoiceTableProps) {
  const colSpan = docView === "invoices" ? 7 : 8;

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Status</TableHead>
            <TableHead>Date</TableHead>
            <TableHead>{docView === "estimates" ? "Estimate #" : "Invoice #"}</TableHead>
            <TableHead>Client</TableHead>
            <TableHead>Subject</TableHead>
            <TableHead className="text-right">Total</TableHead>
            {docView === "invoices" && <TableHead className="text-right">Balance</TableHead>}
            {docView === "estimates" && <TableHead>Approval</TableHead>}
            {docView === "estimates" && <TableHead></TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={colSpan} className="text-center py-8">
                Loading...
              </TableCell>
            </TableRow>
          ) : invoices.length === 0 ? (
            <TableRow>
              <TableCell colSpan={colSpan} className="text-center py-8 text-muted-foreground">
                No {docView === "estimates" ? "estimates" : "invoices"} found
              </TableCell>
            </TableRow>
          ) : (
            invoices.map((inv, i) => (
              <TableRow key={inv.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                <TableCell>
                  <InvoiceStatusBadge status={inv.status} />
                </TableCell>
                <TableCell>{inv.issue_date}</TableCell>
                <TableCell>
                  <Link href={`/invoices/${inv.id}`} className="font-medium hover:underline">
                    {inv.invoice_number || "Draft"}
                  </Link>
                </TableCell>
                <TableCell>{inv.customer_name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {inv.subject || "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  ${inv.total.toFixed(2)}
                </TableCell>
                {docView === "invoices" && (
                  <TableCell className={`text-right ${inv.balance > 0 ? "text-red-600 font-medium" : ""}`}>
                    ${inv.balance.toFixed(2)}
                  </TableCell>
                )}
                {docView === "estimates" && (
                  <TableCell>
                    {inv.approved_at ? (
                      <div className="flex items-center gap-1">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span className="text-xs text-green-700">{inv.approved_by}</span>
                      </div>
                    ) : ["sent", "revised", "viewed"].includes(inv.status) ? (
                      <span className="text-xs text-muted-foreground">Awaiting</span>
                    ) : null}
                  </TableCell>
                )}
                {docView === "estimates" && (
                  <TableCell>
                    {!inv.approved_at && ["sent", "revised", "viewed"].includes(inv.status) && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => onApprove(inv.id)}
                      >
                        Approve
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}

// ── Approve Estimate Dialog ───────────────────────────────────────────

interface ApproveEstimateDialogProps {
  approveDialogId: string | null;
  setApproveDialogId: (id: string | null) => void;
  approveNote: string;
  setApproveNote: (note: string) => void;
  approving: boolean;
  onApprove: () => void;
}

export function ApproveEstimateDialog({
  approveDialogId,
  setApproveDialogId,
  approveNote,
  setApproveNote,
  approving,
  onApprove,
}: ApproveEstimateDialogProps) {
  return (
    <Dialog open={!!approveDialogId} onOpenChange={(open) => { if (!open) setApproveDialogId(null); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Approve Estimate</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            This will approve the estimate on behalf of the client. A job will be created automatically.
          </p>
          <div className="space-y-1">
            <Label className="text-xs">Note (optional)</Label>
            <Input
              value={approveNote}
              onChange={(e) => setApproveNote(e.target.value)}
              placeholder="e.g. Client approved via email 3/30"
              className="text-sm"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setApproveDialogId(null)}>Cancel</Button>
            <Button size="sm" onClick={onApprove} disabled={approving}>
              {approving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />}
              Approve
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
