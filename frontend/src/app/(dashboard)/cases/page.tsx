"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageLayout } from "@/components/layout/page-layout";
import { Loader2, FolderOpen, Search } from "lucide-react";
import type { ServiceCase } from "@/types/agent";

const STATUS_LABELS: Record<string, string> = {
  new: "New",
  triaging: "Triaging",
  scoping: "Scoping",
  pending_approval: "Pending Approval",
  approved: "Approved",
  in_progress: "In Progress",
  pending_payment: "Pending Payment",
  closed: "Closed",
  cancelled: "Cancelled",
};

const STATUS_STYLES: Record<string, string> = {
  new: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  triaging: "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300",
  scoping: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  pending_approval: "border-amber-400 text-amber-600",
  approved: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  in_progress: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  pending_payment: "border-orange-400 text-orange-600",
  closed: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  cancelled: "bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400",
};

function CaseStatusBadge({ status }: { status: string }) {
  const isPending = status === "pending_approval" || status === "pending_payment";
  return (
    <Badge variant={isPending ? "outline" : "secondary"} className={`text-[10px] ${STATUS_STYLES[status] || ""}`}>
      {STATUS_LABELS[status] || status.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
    </Badge>
  );
}

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<ServiceCase[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("open");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter && statusFilter !== "all" && statusFilter !== "open") {
        params.set("status", statusFilter);
      }
      if (search) params.set("search", search);
      params.set("limit", "50");

      const data = await api.get<{ items: ServiceCase[]; total: number }>(`/v1/cases?${params}`);
      let items = data.items || [];
      if (statusFilter === "open") {
        items = items.filter(c => c.status !== "closed" && c.status !== "cancelled");
      }
      setCases(items);
      setTotal(data.total);
    } catch {
      setCases([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => { load(); }, [load]);

  const handleSearch = () => setSearch(searchInput);

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <PageLayout
      title="Cases"
      icon={<FolderOpen className="h-5 w-5 text-muted-foreground" />}
    >
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px] h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="scoping">Scoping</SelectItem>
            <SelectItem value="pending_approval">Pending Approval</SelectItem>
            <SelectItem value="pending_payment">Pending Payment</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex gap-1 flex-1 max-w-sm">
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
            placeholder="Search cases..."
            className="h-8 text-xs"
          />
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={handleSearch}>
            <Search className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : cases.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">No cases found</div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-100 dark:bg-slate-800">
                <TableHead className="text-xs font-medium uppercase tracking-wide">Case</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Customer</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide text-center">Jobs</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide text-center">Emails</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Invoiced</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.map((c, i) => (
                <TableRow
                  key={c.id}
                  className={`cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                  onClick={() => router.push(`/cases/${c.id}`)}
                >
                  <TableCell>
                    <div>
                      <span className="text-xs font-mono text-muted-foreground">{c.case_number}</span>
                      <p className="text-sm font-medium truncate max-w-[250px]">{c.title}</p>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{c.customer_name || "—"}</TableCell>
                  <TableCell><CaseStatusBadge status={c.status} /></TableCell>
                  <TableCell className="text-center text-sm">
                    {c.open_job_count > 0 ? (
                      <span className="font-medium">{c.open_job_count}<span className="text-muted-foreground">/{c.job_count}</span></span>
                    ) : (
                      <span className="text-muted-foreground">{c.job_count}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-center text-sm text-muted-foreground">{c.thread_count}</TableCell>
                  <TableCell className="text-right text-sm">
                    {c.total_invoiced > 0 ? `$${c.total_invoiced.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "—"}
                  </TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">{formatDate(c.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </PageLayout>
  );
}
