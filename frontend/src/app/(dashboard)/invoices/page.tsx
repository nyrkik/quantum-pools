"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { PageLayout, PageTabs } from "@/components/layout/page-layout";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { ArAgingTable } from "@/components/invoices/ar-aging-table";
import { ReconciliationContent } from "@/components/invoices/reconciliation-content";
import { DunningPreview } from "@/components/invoices/dunning-preview";

const OPEN_STATUSES = "draft,sent,revised,viewed,overdue,approved";

type DocView = "invoices" | "estimates" | "ar_aging" | "reconciliation" | "dunning";
type TabFilter = "open" | "all" | "paid" | "overdue" | "void";
type EstimateFilter =
  | "all" | "open" | "draft" | "sent" | "approved" | "rejected" | "expired";
// Approved is the highest-priority "needs action" state for an estimate
// (customer said yes; convert to invoice + schedule). Aligns with
// OPEN_STATUSES on the invoices side, which already includes approved.
// Once an estimate is converted, document_type flips to "invoice", so
// the row naturally falls out of this view.
const OPEN_ESTIMATE_STATUSES = ["draft", "sent", "revised", "viewed", "approved"];

// Sentinel for "no management-company filter" — the Radix Select
// won't accept empty-string values, so we route through this.
const MC_ALL = "__all__";

export default function InvoicesPage() {
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const initialView: DocView =
    tabParam === "estimates" ? "estimates" :
    tabParam === "ar_aging" ? "ar_aging" :
    tabParam === "reconciliation" ? "reconciliation" :
    tabParam === "dunning" ? "dunning" :
    "invoices";
  const [docView, setDocView] = useState<DocView>(initialView);

  // Sync docView when URL tab param changes (e.g. back navigation)
  useEffect(() => {
    setDocView(
      tabParam === "estimates" ? "estimates" :
      tabParam === "ar_aging" ? "ar_aging" :
      tabParam === "reconciliation" ? "reconciliation" :
      tabParam === "dunning" ? "dunning" :
      "invoices"
    );
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
  const [estimateFilter, setEstimateFilter] = useState<EstimateFilter>("open");
  const [managementCompany, setManagementCompany] = useState<string>(MC_ALL);
  const [companyOptions, setCompanyOptions] = useState<
    { name: string; customer_count: number }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [isNonClient, setIsNonClient] = useState(false);
  const [billingName, setBillingName] = useState("");
  const [billingEmail, setBillingEmail] = useState("");
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
      if (managementCompany && managementCompany !== MC_ALL) {
        params.set("management_company", managementCompany);
      }

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
      } else {
        // Estimates tab — single-status backend call unless "open"
        // (umbrella) or "all" (no filter).
        if (estimateFilter !== "all" && estimateFilter !== "open") {
          params.set("status", estimateFilter);
        }
      }

      params.set("limit", "100");
      const data = await api.get<{ items: Invoice[]; total: number }>(
        `/v1/invoices?${params}`
      );
      let items = data.items;
      // Search transcends the current tab — once the user types into the
      // search box, they want to see every match regardless of which
      // status filter the page happens to be on. Otherwise FB-47-style
      // misses recur (search "26024" while the Estimates tab is on its
      // default "open" view, miss the approved match client-side).
      const isSearching = !!search;
      if (docView === "invoices") {
        const effectiveFilter = selectedMonth !== null ? chartSegment : activeTab;
        if (effectiveFilter === "open" && !isSearching) {
          items = items.filter((inv) =>
            OPEN_STATUSES.split(",").includes(inv.status)
          );
        }
        setTotal(effectiveFilter === "open" && !isSearching ? items.length : data.total);
      } else {
        if (estimateFilter === "open" && !isSearching) {
          items = items.filter((inv) =>
            OPEN_ESTIMATE_STATUSES.includes(inv.status),
          );
          setTotal(items.length);
        } else {
          setTotal(data.total);
        }
      }
      setInvoices(items);
    } catch {
      toast.error("Failed to load");
    } finally {
      setLoading(false);
    }
  }, [
    search, activeTab, selectedMonth, chartYear, chartSegment, docView,
    estimateFilter, managementCompany,
  ]);

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

  // Management-company filter options — distinct list per org,
  // deduped case-insensitively on the server.
  useEffect(() => {
    api.get<{ items: { name: string; customer_count: number }[] }>(
      "/v1/invoices/management-companies",
    )
      .then((d) => setCompanyOptions(d.items || []))
      .catch(() => setCompanyOptions([]));
  }, []);

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
    const body: Record<string, unknown> = {
      customer_id: isNonClient ? undefined : selectedCustomerId,
      billing_name: isNonClient ? billingName : undefined,
      billing_email: isNonClient ? billingEmail : undefined,
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
      setIsNonClient(false);
      setBillingName("");
      setBillingEmail("");
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
        ? stats.invoice_count - stats.paid_count - stats.overdue_count - (stats.void_count || 0)
        : undefined,
    },
    { key: "all", label: "All Invoices", count: stats?.invoice_count },
    { key: "paid", label: "Paid", count: stats?.paid_count },
    { key: "overdue", label: "Overdue", count: stats?.overdue_count },
    { key: "void", label: "Voided", count: stats?.void_count },
  ];

  return (
    <PageLayout
      title="Invoices"
      subtitle={undefined}
      action={(docView === "ar_aging" || docView === "reconciliation" || docView === "dunning") ? undefined : (
        <CreateInvoiceDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          docView={docView}
          customers={customers}
          selectedCustomerId={selectedCustomerId}
          setSelectedCustomerId={setSelectedCustomerId}
          isNonClient={isNonClient}
          setIsNonClient={setIsNonClient}
          billingName={billingName}
          setBillingName={setBillingName}
          billingEmail={billingEmail}
          setBillingEmail={setBillingEmail}
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
      )}
      tabs={[
        { key: "invoices", label: "Invoices" },
        { key: "estimates", label: "Estimates" },
        { key: "ar_aging", label: "A/R Aging" },
        { key: "reconciliation", label: "Reconciliation" },
        { key: "dunning", label: "Payment reminders" },
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
      {docView === "ar_aging" ? (
        <ArAgingTable />
      ) : docView === "reconciliation" ? (
        <ReconciliationContent />
      ) : docView === "dunning" ? (
        <DunningPreview />
      ) : (
        <>
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={docView === "estimates" ? "Search estimates..." : "Search invoices..."}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64"
          />
        </div>

        {/* Estimates tab — status filter (Invoices tab has this already
            via the PageTabs above the chart). */}
        {docView === "estimates" && (
          <Select
            value={estimateFilter}
            onValueChange={(v) => setEstimateFilter(v as EstimateFilter)}
          >
            <SelectTrigger className="h-9 w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="sent">Sent</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
              <SelectItem value="expired">Expired</SelectItem>
            </SelectContent>
          </Select>
        )}

        {/* Management company — customers.company_name, deduped
            case-insensitively on the server. Only render the dropdown
            when the org actually has any. */}
        {companyOptions.length > 0 && (
          <Select value={managementCompany} onValueChange={setManagementCompany}>
            <SelectTrigger className="h-9 w-56">
              <SelectValue placeholder="All management companies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={MC_ALL}>All management companies</SelectItem>
              {companyOptions.map((c) => (
                <SelectItem key={c.name} value={c.name}>
                  {c.name}
                  <span className="text-muted-foreground ml-1">
                    ({c.customer_count})
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
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
        </>
      )}
    </PageLayout>
  );
}
