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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Loader2, FolderOpen, Search, Plus } from "lucide-react";
import { toast } from "sonner";
import type { ServiceCase } from "@/types/agent";
import { CustomerPicker } from "@/components/cases/customer-picker";
import { CaseOwner } from "@/components/cases/case-owner";

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
  const [createOpen, setCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [newCustomerId, setNewCustomerId] = useState<string | null>(null);
  const [newBillingName, setNewBillingName] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const result = await api.post<{ id: string; case_number: number }>("/v1/cases", {
        title: newTitle.trim(),
        customer_id: newCustomerId,
        billing_name: newBillingName,
      });
      toast.success(`Case #${result.case_number} created`);
      setCreateOpen(false);
      setNewTitle("");
      setNewCustomerId(null);
      setNewBillingName(null);
      router.push(`/cases/${result.id}`);
    } catch {
      toast.error("Failed to create case");
    } finally {
      setCreating(false);
    }
  };

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
      action={
        <Button size="sm" className="gap-1.5" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" />
          New Case
        </Button>
      }
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
                <TableHead className="text-xs font-medium uppercase tracking-wide hidden sm:table-cell">Status</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide hidden sm:table-cell">Owner</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide text-right hidden sm:table-cell">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.map((c, i) => {
                const flags = c.flags || {};
                const activeFlags: { label: string; color: string }[] = [];
                if (flags.estimate_approved) activeFlags.push({ label: "Estimate approved", color: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400" });
                if (flags.estimate_rejected) activeFlags.push({ label: "Estimate rejected", color: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400" });
                if (flags.customer_replied) activeFlags.push({ label: "Customer replied", color: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400" });
                if (flags.jobs_complete) activeFlags.push({ label: "Jobs complete", color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400" });
                if (flags.payment_received) activeFlags.push({ label: "Payment received", color: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400" });
                if (flags.invoice_overdue) activeFlags.push({ label: "Invoice overdue", color: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400" });
                if (flags.stale) activeFlags.push({ label: "Stale", color: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400" });

                return (
                  <TableRow
                    key={c.id}
                    className={`cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                    onClick={() => router.push(`/cases/${c.id}`)}
                  >
                    <TableCell>
                      <div>
                        <span className="text-xs font-mono text-muted-foreground">
                          {c.case_number}
                          {(c.customer_name || c.billing_name) && (
                            <span className="font-sans ml-1.5">({c.customer_name || c.billing_name})</span>
                          )}
                        </span>
                        <p className="text-sm font-medium truncate max-w-[400px]">{c.title}</p>
                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                          {/* Mobile-only: status + owner inline */}
                          <span className="sm:hidden"><CaseStatusBadge status={c.status} /></span>
                          <span className="sm:hidden" onClick={(e) => e.stopPropagation()}>
                            <CaseOwner
                              caseId={c.id}
                              managerName={c.manager_name}
                              currentActor={c.current_actor_name}
                              onReassigned={() => load()}
                            />
                          </span>
                          {c.open_job_count > 0 && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400">
                              {c.open_job_count} open job{c.open_job_count !== 1 ? "s" : ""}
                            </span>
                          )}
                          {c.thread_count > 0 && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                              {c.thread_count} email{c.thread_count !== 1 ? "s" : ""}
                            </span>
                          )}
                          {c.total_invoiced > 0 && (
                            <span className="text-[10px] text-muted-foreground">
                              ${c.total_invoiced.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                            </span>
                          )}
                          {activeFlags.map((f) => (
                            <span key={f.label} className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${f.color}`}>
                              {f.label}
                            </span>
                          ))}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell"><CaseStatusBadge status={c.status} /></TableCell>
                    <TableCell className="hidden sm:table-cell" onClick={(e) => e.stopPropagation()}>
                      <CaseOwner
                        caseId={c.id}
                        managerName={c.manager_name}
                        currentActor={c.current_actor_name}
                        onReassigned={() => load()}
                      />
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground hidden sm:table-cell">{formatDate(c.updated_at)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>New Case</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="case-title" className="text-xs">Subject</Label>
              <Input
                id="case-title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="What is this case about?"
                onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Customer</Label>
              <CustomerPicker
                onChange={(cid, bn) => { setNewCustomerId(cid); setNewBillingName(bn); }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button size="sm" onClick={handleCreate} disabled={creating || !newTitle.trim()}>
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
