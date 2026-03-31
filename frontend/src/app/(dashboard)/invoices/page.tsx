"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
  Plus,
  Search,
  DollarSign,
  AlertTriangle,
  Trash2,
  ChevronLeft,
  ChevronRight,
  X,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface Invoice {
  id: string;
  invoice_number: string;
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

interface InvoiceStats {
  total_outstanding: number;
  total_overdue: number;
  monthly_revenue: number;
  invoice_count: number;
  paid_count: number;
  overdue_count: number;
}

interface MonthlyData {
  month: string;
  paid: number;
  open: number;
}

interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  company_name: string | null;
}

interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
  is_taxed: boolean;
}

import { InvoiceStatusBadge } from "@/components/badges/invoice-status-badge";
import { PageLayout, PageTabs } from "@/components/layout/page-layout";

const OPEN_STATUSES = "draft,sent,viewed,overdue";

type DocView = "invoices" | "estimates";
type TabFilter = "open" | "all" | "paid" | "overdue" | "void";

export default function InvoicesPage() {
  const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const [docView, setDocView] = useState<DocView>(urlParams?.get("tab") === "estimates" ? "estimates" : "invoices");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<InvoiceStats | null>(null);
  const [monthlyData, setMonthlyData] = useState<MonthlyData[]>([]);
  const [chartYear, setChartYear] = useState(new Date().getFullYear());
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [chartSegment, setChartSegment] = useState<"all" | "paid" | "open">("all");
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<TabFilter>("open");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [lineItems, setLineItems] = useState<LineItem[]>([
    { description: "", quantity: 1, unit_price: 0, is_taxed: false },
  ]);
  const [taxRate, setTaxRate] = useState(0);
  const [approveDialogId, setApproveDialogId] = useState<string | null>(null);
  const [approveNote, setApproveNote] = useState("");
  const [approving, setApproving] = useState(false);
  const [discount, setDiscount] = useState(0);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("document_type", docView === "estimates" ? "estimate" : "invoice");
      if (search) params.set("search", search);

      if (docView === "invoices") {
        // Chart segment overrides tab filter when a month is selected
        const effectiveFilter = selectedMonth !== null ? chartSegment : activeTab;
        if (effectiveFilter === "open") {
          // Backend only supports single status, so fetch all and filter client-side
        } else if (effectiveFilter === "paid") {
          params.set("status", "paid");
        } else if (effectiveFilter !== "all") {
          params.set("status", effectiveFilter);
        }
        if (selectedMonth !== null) {
          const y = chartYear;
          const m = selectedMonth;
          const from = `${y}-${String(m + 1).padStart(2, "0")}-01`;
          const lastDay = new Date(y, m + 1, 0).getDate();
          const to = `${y}-${String(m + 1).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
          params.set("date_from", from);
          params.set("date_to", to);
        }
      }

      params.set("limit", "100");
      const data = await api.get<{ items: Invoice[]; total: number }>(
        `/v1/invoices?${params}`
      );
      let items = data.items;
      if (docView === "invoices") {
        const effectiveFilter = selectedMonth !== null ? chartSegment : activeTab;
        if (effectiveFilter === "open") {
          items = items.filter((inv) =>
            OPEN_STATUSES.split(",").includes(inv.status)
          );
        }
        setTotal(effectiveFilter === "open" ? items.length : data.total);
      } else {
        setTotal(data.total);
      }
      setInvoices(items);
    } catch {
      toast.error("Failed to load");
    } finally {
      setLoading(false);
    }
  }, [search, activeTab, selectedMonth, chartYear, chartSegment, docView]);

  const fetchStats = useCallback(async () => {
    try {
      const data = await api.get<InvoiceStats>("/v1/invoices/stats");
      setStats(data);
    } catch {
      /* stats are non-critical */
    }
  }, []);

  const fetchMonthly = useCallback(async () => {
    try {
      const data = await api.get<MonthlyData[]>(
        `/v1/invoices/monthly?year=${chartYear}`
      );
      setMonthlyData(data);
    } catch {
      /* chart is non-critical */
    }
  }, [chartYear]);

  useEffect(() => {
    fetchInvoices();
    fetchStats();
  }, [fetchInvoices, fetchStats]);

  useEffect(() => {
    fetchMonthly();
  }, [fetchMonthly]);

  const fetchCustomers = useCallback(async () => {
    try {
      const data = await api.get<{ items: Customer[] }>(
        "/v1/customers?limit=100"
      );
      setCustomers(data.items);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    if (dialogOpen) fetchCustomers();
  }, [dialogOpen, fetchCustomers]);

  const addLineItem = () => {
    setLineItems([
      ...lineItems,
      { description: "", quantity: 1, unit_price: 0, is_taxed: false },
    ]);
  };

  const removeLineItem = (index: number) => {
    if (lineItems.length <= 1) return;
    setLineItems(lineItems.filter((_, i) => i !== index));
  };

  const updateLineItem = (
    index: number,
    field: keyof LineItem,
    value: string | number | boolean
  ) => {
    setLineItems(
      lineItems.map((item, i) =>
        i === index ? { ...item, [field]: value } : item
      )
    );
  };

  const subtotal = lineItems.reduce(
    (sum, li) => sum + li.quantity * li.unit_price,
    0
  );
  const taxableAmount = lineItems
    .filter((li) => li.is_taxed)
    .reduce((sum, li) => sum + li.quantity * li.unit_price, 0);
  const taxAmount = taxableAmount * (taxRate / 100);
  const computedTotal = subtotal + taxAmount - discount;

  const handleApproveEstimate = async () => {
    if (!approveDialogId) return;
    setApproving(true);
    try {
      await api.post(`/v1/invoices/${approveDialogId}/approve`, {});
      toast.success("Estimate approved");
      setApproveDialogId(null);
      setApproveNote("");
      fetchInvoices();
    } catch {
      toast.error("Failed to approve estimate");
    } finally {
      setApproving(false);
    }
  };

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = {
      customer_id: selectedCustomerId,
      subject: (form.get("subject") as string) || undefined,
      issue_date: form.get("issue_date") as string,
      due_date: form.get("due_date") as string,
      discount,
      tax_rate: taxRate,
      notes: (form.get("notes") as string) || undefined,
      line_items: lineItems
        .filter((li) => li.description.trim())
        .map((li, i) => ({
          description: li.description,
          quantity: li.quantity,
          unit_price: li.unit_price,
          is_taxed: li.is_taxed,
          sort_order: i,
        })),
    };
    try {
      await api.post("/v1/invoices", body);
      toast.success("Invoice created");
      setDialogOpen(false);
      setSelectedCustomerId("");
      setLineItems([
        { description: "", quantity: 1, unit_price: 0, is_taxed: false },
      ]);
      setTaxRate(0);
      setDiscount(0);
      fetchInvoices();
      fetchStats();
      fetchMonthly();
    } catch {
      toast.error("Failed to create invoice");
    }
  };

  const today = new Date().toISOString().split("T")[0];
  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth(); // 0-indexed

  const [hoveredMonth, setHoveredMonth] = useState<number | null>(null);
  const chartData = monthlyData.map((m, i) => ({
    ...m,
    isFuture: chartYear > currentYear || (chartYear === currentYear && i > currentMonth),
  }));

  const tabs: { key: TabFilter; label: string; count?: number }[] = [
    {
      key: "open",
      label: "Open",
      count: stats
        ? stats.invoice_count - stats.paid_count - stats.overdue_count
        : undefined,
    },
    { key: "all", label: "All Invoices", count: stats?.invoice_count },
    { key: "paid", label: "Paid", count: stats?.paid_count },
    { key: "overdue", label: "Overdue", count: stats?.overdue_count },
  ];

  return (
    <PageLayout
      title="Invoices"
      subtitle={undefined}
      action={
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              {docView === "estimates" ? "Create Estimate" : "Create Invoice"}
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>New Invoice</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>Client</Label>
                  <Select
                    value={selectedCustomerId}
                    onValueChange={setSelectedCustomerId}
                  >
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
                <div className="space-y-2">
                  <Label htmlFor="subject">Subject</Label>
                  <Input
                    id="subject"
                    name="subject"
                    placeholder="Monthly pool service"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="issue_date">Issue Date</Label>
                  <Input
                    id="issue_date"
                    name="issue_date"
                    type="date"
                    defaultValue={today}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="due_date">Due Date</Label>
                  <Input
                    id="due_date"
                    name="due_date"
                    type="date"
                    defaultValue={
                      new Date(Date.now() + 30 * 86400000)
                        .toISOString()
                        .split("T")[0]
                    }
                    required
                  />
                </div>
              </div>

              {/* Line Items */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Line Items</Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={addLineItem}
                  >
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
                        onChange={(e) =>
                          updateLineItem(index, "description", e.target.value)
                        }
                        required={index === 0}
                      />
                      <Input
                        type="number"
                        placeholder="Qty"
                        className="w-20"
                        min="0"
                        step="1"
                        value={item.quantity}
                        onChange={(e) =>
                          updateLineItem(
                            index,
                            "quantity",
                            parseFloat(e.target.value) || 0
                          )
                        }
                      />
                      <Input
                        type="number"
                        placeholder="Price"
                        className="w-28"
                        min="0"
                        step="0.01"
                        value={item.unit_price}
                        onChange={(e) =>
                          updateLineItem(
                            index,
                            "unit_price",
                            parseFloat(e.target.value) || 0
                          )
                        }
                      />
                      <div className="flex items-center gap-1 pt-2">
                        <Checkbox
                          checked={item.is_taxed}
                          onCheckedChange={(checked) =>
                            updateLineItem(
                              index,
                              "is_taxed",
                              checked === true
                            )
                          }
                        />
                        <span className="text-xs text-muted-foreground">
                          Tax
                        </span>
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
                    onChange={(e) =>
                      setTaxRate(parseFloat(e.target.value) || 0)
                    }
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
                    onChange={(e) =>
                      setDiscount(parseFloat(e.target.value) || 0)
                    }
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

              <Button
                type="submit"
                className="w-full"
                disabled={!selectedCustomerId}
              >
                Create Invoice
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      }
      tabs={[
        { key: "invoices", label: "Invoices" },
        { key: "estimates", label: "Estimates" },
      ]}
      activeTab={docView}
      onTabChange={(key) => { setDocView(key as DocView); setSearch(""); setSelectedMonth(null); setChartSegment("all"); setActiveTab("open"); }}
      context={docView === "invoices" ? (
        <>
      {/* Chart */}
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
                        {/* Tooltip on hover only */}
                        {isHovered && !d.isFuture && (
                          <div className="absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full bg-popover border rounded shadow-md px-2.5 py-1.5 text-[11px] whitespace-nowrap z-20 pointer-events-none">
                            <div className="font-medium mb-0.5">{d.month}</div>
                            <div className="text-green-700">Paid ${d.paid.toLocaleString("en-US", { minimumFractionDigits: 0 })}</div>
                            <div className="text-amber-600">Open ${d.open.toLocaleString("en-US", { minimumFractionDigits: 0 })}</div>
                          </div>
                        )}
                        {/* Bar container — always full height */}
                        <div className={`flex-1 flex flex-col justify-end rounded-t overflow-hidden transition-opacity duration-150 ${d.isFuture ? "opacity-40" : highlighted ? "opacity-100" : faded ? "opacity-40" : "opacity-100"}`}>
                          {/* Grey remainder — top */}
                          <div className={`${highlighted ? "bg-slate-300" : "bg-slate-200"} transition-colors duration-150`} style={{ flexBasis: `${greyPct}%`, minHeight: 0 }} />
                          {/* Open (amber) — middle */}
                          {openPct > 0 && <div className="bg-amber-400" style={{ flexBasis: `${openPct}%`, minHeight: 0 }} />}
                          {/* Paid (green) — bottom */}
                          {paidPct > 0 && <div className="bg-green-600" style={{ flexBasis: `${paidPct}%`, minHeight: 0 }} />}
                        </div>
                        {/* Month label */}
                        <p className="text-[10px] sm:text-[11px] text-center text-muted-foreground mt-1.5 select-none">{d.month}</p>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
        </CardContent>
      </Card>

      {/* Sub-tabs: Open / All / Paid / Overdue */}
      <PageTabs
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={(key) => setActiveTab(key as TabFilter)}
      />
        </>
      ) : undefined}
    >
      {/* Search */}
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={docView === "estimates" ? "Search estimates..." : "Search invoices..."}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
      </div>

      {/* Table */}
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
                <TableCell colSpan={docView === "invoices" ? 7 : 8} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : invoices.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={docView === "invoices" ? 7 : 8}
                  className="text-center py-8 text-muted-foreground"
                >
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
                    <Link
                      href={`/invoices/${inv.id}`}
                      className="font-medium hover:underline"
                    >
                      {inv.invoice_number}
                    </Link>
                  </TableCell>
                  <TableCell>{inv.customer_name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {inv.subject || "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    ${inv.total.toFixed(2)}
                  </TableCell>
                  {docView === "invoices" && (
                    <TableCell
                      className={`text-right ${inv.balance > 0 ? "text-red-600 font-medium" : ""}`}
                    >
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
                      ) : (
                        <span className="text-xs text-muted-foreground">Pending</span>
                      )}
                    </TableCell>
                  )}
                  {docView === "estimates" && (
                    <TableCell>
                      {!inv.approved_at && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => { setApproveDialogId(inv.id); setApproveNote(""); }}
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

      {/* Approve Estimate Dialog */}
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
              <Button size="sm" onClick={handleApproveEstimate} disabled={approving}>
                {approving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />}
                Approve
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
