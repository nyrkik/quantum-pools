"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { PageLayout, PageTabs } from "@/components/layout/page-layout";
import {
  MonthlyChart,
  CreateInvoiceDialog,
  InvoiceTable,
  ApproveEstimateDialog,
  type Invoice,
  type InvoiceStats,
  type MonthlyData,
  type Customer,
  type LineItem,
} from "@/components/invoices/invoice-list-components";

const OPEN_STATUSES = "draft,sent,revised,viewed,overdue,approved";

type DocView = "invoices" | "estimates";
type TabFilter = "open" | "all" | "paid" | "overdue" | "void";

export default function InvoicesPage() {
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const [docView, setDocView] = useState<DocView>(tabParam === "estimates" ? "estimates" : "invoices");

  // Sync docView when URL tab param changes (e.g. back navigation)
  useEffect(() => {
    setDocView(tabParam === "estimates" ? "estimates" : "invoices");
  }, [tabParam]);
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
      document_type: docView === "estimates" ? "estimate" : "invoice",
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
      toast.success(docView === "estimates" ? "Estimate created" : "Invoice created");
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
  const currentMonth = new Date().getMonth();

  const [hoveredMonth, setHoveredMonth] = useState<number | null>(null);

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
        <CreateInvoiceDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          docView={docView}
          customers={customers}
          selectedCustomerId={selectedCustomerId}
          setSelectedCustomerId={setSelectedCustomerId}
          lineItems={lineItems}
          addLineItem={addLineItem}
          removeLineItem={removeLineItem}
          updateLineItem={updateLineItem}
          taxRate={taxRate}
          setTaxRate={setTaxRate}
          discount={discount}
          setDiscount={setDiscount}
          subtotal={subtotal}
          taxAmount={taxAmount}
          computedTotal={computedTotal}
          today={today}
          onSubmit={handleCreate}
        />
      }
      tabs={[
        { key: "invoices", label: "Invoices" },
        { key: "estimates", label: "Estimates" },
      ]}
      activeTab={docView}
      onTabChange={(key) => { setDocView(key as DocView); setSearch(""); setSelectedMonth(null); setChartSegment("all"); setActiveTab("open"); }}
      context={docView === "invoices" ? (
        <>
          <MonthlyChart
            monthlyData={monthlyData}
            stats={stats}
            chartYear={chartYear}
            setChartYear={setChartYear}
            selectedMonth={selectedMonth}
            setSelectedMonth={setSelectedMonth}
            chartSegment={chartSegment}
            setChartSegment={setChartSegment}
            hoveredMonth={hoveredMonth}
            setHoveredMonth={setHoveredMonth}
            currentYear={currentYear}
            currentMonth={currentMonth}
          />
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

      <InvoiceTable
        invoices={invoices}
        loading={loading}
        docView={docView}
        onApprove={(id) => { setApproveDialogId(id); setApproveNote(""); }}
      />

      <ApproveEstimateDialog
        approveDialogId={approveDialogId}
        setApproveDialogId={setApproveDialogId}
        approveNote={approveNote}
        setApproveNote={setApproveNote}
        approving={approving}
        onApprove={handleApproveEstimate}
      />
    </PageLayout>
  );
}
