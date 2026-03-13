"use client";

import { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface Invoice {
  id: string;
  invoice_number: string;
  customer_id: string;
  customer_name: string;
  subject: string | null;
  status: string;
  issue_date: string;
  due_date: string;
  total: number;
  balance: number;
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

const STATUS_COLORS: Record<string, string> = {
  draft: "secondary",
  sent: "outline",
  paid: "default",
  overdue: "destructive",
  void: "secondary",
  written_off: "outline",
};

function StatusBadge({ status }: { status: string }) {
  const variant = STATUS_COLORS[status] || "secondary";
  const colorClass =
    status === "sent"
      ? "border-blue-400 text-blue-600"
      : status === "paid"
        ? "bg-green-600"
        : status === "written_off"
          ? "border-yellow-500 text-yellow-600"
          : "";
  return (
    <Badge variant={variant as "default"} className={colorClass}>
      {status.replace("_", " ")}
    </Badge>
  );
}

const OPEN_STATUSES = "draft,sent,viewed,overdue";

type TabFilter = "open" | "all" | "paid" | "overdue" | "void";

export default function InvoicesPage() {
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
  const [discount, setDiscount] = useState(0);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
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
      params.set("limit", "100");
      const data = await api.get<{ items: Invoice[]; total: number }>(
        `/v1/invoices?${params}`
      );
      let items = data.items;
      if (effectiveFilter === "open") {
        items = items.filter((inv) =>
          OPEN_STATUSES.split(",").includes(inv.status)
        );
      }
      setInvoices(items);
      setTotal(effectiveFilter === "open" ? items.length : data.total);
    } catch {
      toast.error("Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }, [search, activeTab, selectedMonth, chartYear, chartSegment]);

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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Invoices</h1>
          <p className="text-muted-foreground">{total} total invoices</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Create Invoice
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
      </div>

      {/* Chart + Summary — PSS-inspired layout */}
      <div className="grid gap-4 md:grid-cols-[280px_1fr]">
        {/* Summary Card */}
        {stats && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">Total Open</p>
                <p className="text-2xl font-bold">
                  ${stats.total_outstanding.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Paid (this month)</p>
                <p className="text-2xl font-bold">
                  ${stats.monthly_revenue.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </p>
              </div>
              {stats.total_overdue > 0 && (
                <div>
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3 text-destructive" />
                    Overdue
                  </p>
                  <p className="text-2xl font-bold text-destructive">
                    ${stats.total_overdue.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {stats.overdue_count} invoice{stats.overdue_count !== 1 ? "s" : ""}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Monthly Chart */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-base">
              Invoices issued in {chartYear}
            </CardTitle>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => { setChartYear((y) => y - 1); setSelectedMonth(null); setChartSegment("all"); }}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => { setChartYear(currentYear); setSelectedMonth(null); setChartSegment("all"); }}
              >
                This Year
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => { setChartYear((y) => y + 1); setSelectedMonth(null); setChartSegment("all"); }}
                disabled={chartYear >= currentYear}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={monthlyData} style={{ cursor: "pointer" }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v) =>
                    v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`
                  }
                />
                <Tooltip
                  formatter={(value) => [
                    `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
                  ]}
                />
                <Legend
                  onClick={(e) => {
                    if (selectedMonth === null) return;
                    const key = e.dataKey as string;
                    const seg = key === "paid" ? "paid" : "open";
                    setChartSegment(chartSegment === seg ? "all" : seg);
                  }}
                  formatter={(value) => (
                    <span
                      style={{
                        cursor: selectedMonth !== null ? "pointer" : "default",
                        textDecoration:
                          selectedMonth !== null &&
                          chartSegment !== "all" &&
                          ((value === "Paid" && chartSegment !== "paid") ||
                            (value === "Open" && chartSegment !== "open"))
                            ? "line-through"
                            : "none",
                        opacity:
                          selectedMonth !== null &&
                          chartSegment !== "all" &&
                          ((value === "Paid" && chartSegment !== "paid") ||
                            (value === "Open" && chartSegment !== "open"))
                            ? 0.4
                            : 1,
                      }}
                    >
                      {value}
                    </span>
                  )}
                />
                <Bar
                  dataKey="paid"
                  name="Paid"
                  stackId="a"
                  radius={[0, 0, 0, 0]}
                  onClick={(_, idx) => {
                    if (selectedMonth === idx) {
                      if (chartSegment === "paid") {
                        // Already on paid — clear entirely
                        setSelectedMonth(null);
                        setChartSegment("all");
                      } else {
                        // Was on open or all — narrow to paid
                        setChartSegment("paid");
                      }
                    } else {
                      setSelectedMonth(idx);
                      setChartSegment("paid");
                    }
                  }}
                >
                  {monthlyData.map((_, i) => {
                    if (selectedMonth === null) return <Cell key={i} fill="#16a34a" opacity={1} />;
                    const isMonth = selectedMonth === i;
                    const dimmed = chartSegment === "open";
                    return <Cell key={i} fill="#16a34a" opacity={!isMonth ? 0.15 : dimmed ? 0.3 : 1} />;
                  })}
                </Bar>
                <Bar
                  dataKey="open"
                  name="Open"
                  stackId="a"
                  radius={[4, 4, 0, 0]}
                  onClick={(_, idx) => {
                    if (selectedMonth === idx) {
                      if (chartSegment === "open") {
                        setSelectedMonth(null);
                        setChartSegment("all");
                      } else {
                        setChartSegment("open");
                      }
                    } else {
                      setSelectedMonth(idx);
                      setChartSegment("open");
                    }
                  }}
                >
                  {monthlyData.map((_, i) => {
                    if (selectedMonth === null) return <Cell key={i} fill="#86efac" opacity={1} />;
                    const isMonth = selectedMonth === i;
                    const dimmed = chartSegment === "paid";
                    return <Cell key={i} fill="#86efac" opacity={!isMonth ? 0.15 : dimmed ? 0.3 : 1} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Month filter indicator */}
      {selectedMonth !== null && (
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              chartSegment === "open"
                ? "bg-[#86efac] text-[#14532d]"
                : "bg-[#16a34a] text-white"
            }`}
          >
            {monthlyData[selectedMonth]?.month} {chartYear}
            {chartSegment !== "all" && (
              <span className="font-semibold">
                {" \u2014 "}{chartSegment === "paid" ? "Paid" : "Unpaid"}
              </span>
            )}
            <button
              onClick={() => { setSelectedMonth(null); setChartSegment("all"); }}
              className="ml-1 opacity-70 hover:opacity-100"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        </div>
      )}

      {/* Tab Filters + Search */}
      <div className="flex items-center justify-between">
        <div className="flex border-b">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="ml-1.5 text-xs text-muted-foreground">
                  ({tab.count})
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search invoices..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64"
          />
        </div>
      </div>

      {/* Invoices Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Status</TableHead>
              <TableHead>Issue Date</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead>Client</TableHead>
              <TableHead>Subject</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="text-right">Balance</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : invoices.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-center py-8 text-muted-foreground"
                >
                  No invoices found
                </TableCell>
              </TableRow>
            ) : (
              invoices.map((inv) => (
                <TableRow key={inv.id}>
                  <TableCell>
                    <StatusBadge status={inv.status} />
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
                  <TableCell
                    className={`text-right ${inv.balance > 0 ? "text-red-600 font-medium" : ""}`}
                  >
                    ${inv.balance.toFixed(2)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
