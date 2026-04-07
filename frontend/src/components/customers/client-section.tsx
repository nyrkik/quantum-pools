"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { ArrowUp, ArrowDown, ArrowUpDown, Loader2 } from "lucide-react";
import { usePermissions } from "@/lib/permissions";

export interface CustomerListItem {
  id: string;
  first_name: string;
  last_name: string;
  display_name: string | null;
  company_name: string | null;
  customer_type: string;
  email: string | null;
  phone: string | null;
  monthly_rate: number;
  balance: number;
  status: string;
  is_active: boolean;
  property_count: number;
  first_property_address: string | null;
  first_property_pool_type: string | null;
  wf_summary: string | null;
  first_property_id: string | null;
}

export type SortKey = "name" | "property" | "company" | "pool" | "rate" | "balance" | "status";
export type SortDir = "asc" | "desc";

const PAGE_SIZE = 50;

function customerDisplayName(c: CustomerListItem) {
  return c.display_name || c.first_name;
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3.5 w-3.5 ml-1 text-muted-foreground/40" />;
  return dir === "asc"
    ? <ArrowUp className="h-3.5 w-3.5 ml-1" />
    : <ArrowDown className="h-3.5 w-3.5 ml-1" />;
}

interface ClientSectionProps {
  customerType: "commercial" | "residential";
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  perms: ReturnType<typeof usePermissions>;
  search: string;
  statusFilter: Set<string>;
  sortKey: SortKey;
  sortDir: SortDir;
  onToggleSort: (key: SortKey) => void;
  techAssignments: Record<string, Array<{ tech_name: string; color: string }>>;
  onSelectCustomer: (id: string) => void;
}

export function ClientSection({
  customerType,
  title,
  icon: Icon,
  perms,
  search,
  statusFilter,
  sortKey,
  sortDir,
  onToggleSort,
  techAssignments,
  onSelectCustomer,
}: ClientSectionProps) {
  const [items, setItems] = useState<CustomerListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchPage = useCallback(async (skip: number, append: boolean) => {
    if (skip === 0) setLoading(true);
    else setLoadingMore(true);
    try {
      const params = new URLSearchParams();
      params.set("customer_type", customerType);
      params.set("sort_by", sortKey);
      params.set("sort_dir", sortDir);
      params.set("skip", String(skip));
      params.set("limit", String(PAGE_SIZE));
      if (search) params.set("search", search);
      statusFilter.forEach(s => params.append("status", s));

      const data = await api.get<{ items: CustomerListItem[]; total: number }>(
        `/v1/customers?${params}`
      );
      setItems(prev => append ? [...prev, ...data.items] : data.items);
      setTotal(data.total);
    } catch {
      toast.error(`Failed to load ${title.toLowerCase()}`);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [customerType, search, sortKey, sortDir, [...statusFilter].sort().join(",")]);

  useEffect(() => {
    fetchPage(0, false);
  }, [fetchPage]);

  useEffect(() => {
    const handleFocus = () => fetchPage(0, false);
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [fetchPage]);

  const hasMore = items.length < total;
  const thClass = "cursor-pointer select-none";
  const colSpan = 6 + (perms.canViewRates ? 1 : 0) + (perms.canViewBalance ? 1 : 0);

  return (
    <div className="rounded-lg border shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2.5">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{title}</h2>
        <span className="text-[11px] text-muted-foreground/50">({total})</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="bg-slate-100 dark:bg-slate-800">
            <TableHead className={`text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => onToggleSort("name")}>
              <div className="flex items-center">Name<SortIcon active={sortKey === "name"} dir={sortDir} /></div>
            </TableHead>
            <TableHead className={`hidden md:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`}>
              Property
            </TableHead>
            <TableHead className={`hidden lg:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => onToggleSort("company")}>
              <div className="flex items-center">Mgmt Company<SortIcon active={sortKey === "company"} dir={sortDir} /></div>
            </TableHead>
            <TableHead className={`hidden sm:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`}>
              Pool Type
            </TableHead>
            <TableHead className="hidden lg:table-cell text-xs font-medium uppercase tracking-wide">
              Tech
            </TableHead>
            {perms.canViewRates && (
              <TableHead className={`text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => onToggleSort("rate")}>
                <div className="flex items-center">Rate<SortIcon active={sortKey === "rate"} dir={sortDir} /></div>
              </TableHead>
            )}
            {perms.canViewBalance && (
              <TableHead className={`hidden sm:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => onToggleSort("balance")}>
                <div className="flex items-center">Balance<SortIcon active={sortKey === "balance"} dir={sortDir} /></div>
              </TableHead>
            )}
            <TableHead className={`text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => onToggleSort("status")}>
              <div className="flex items-center">Status<SortIcon active={sortKey === "status"} dir={sortDir} /></div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={colSpan} className="text-center py-6">
                <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
              </TableCell>
            </TableRow>
          ) : items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={colSpan} className="text-center py-6 text-muted-foreground text-sm">
                No {title.toLowerCase()} clients
              </TableCell>
            </TableRow>
          ) : (
            items.map((c, i) => (
              <TableRow key={c.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                <TableCell>
                  <button onClick={() => onSelectCustomer(c.id)} className="font-medium hover:underline text-left">
                    {customerDisplayName(c)}
                  </button>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground hidden md:table-cell">
                  {c.first_property_address || "\u2014"}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground hidden lg:table-cell">
                  {c.company_name || "\u2014"}
                </TableCell>
                <TableCell className="hidden sm:table-cell text-sm text-muted-foreground capitalize">
                  {c.wf_summary || c.first_property_pool_type || "\u2014"}
                </TableCell>
                <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                  {(() => {
                    const tech = c.first_property_id ? techAssignments[c.first_property_id]?.[0] : null;
                    return tech ? (
                      <div className="flex items-center gap-1.5">
                        <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: tech.color }} />
                        <span className="truncate">{tech.tech_name.split(" ")[0]}</span>
                      </div>
                    ) : "\u2014";
                  })()}
                </TableCell>
                {perms.canViewRates && (
                  <TableCell>${c.monthly_rate.toFixed(2)}</TableCell>
                )}
                {perms.canViewBalance && (
                  <TableCell className={`hidden sm:table-cell ${c.balance > 0 ? "text-red-600 font-medium" : ""}`}>
                    ${c.balance.toFixed(2)}
                  </TableCell>
                )}
                <TableCell>
                  <Badge variant={c.status === "active" ? "default" : c.status === "service_call" ? "outline" : c.status === "lead" || c.status === "pending" ? "outline" : "secondary"}
                    className={c.status === "service_call" ? "border-blue-400 text-blue-600" : c.status === "lead" || c.status === "pending" ? "border-amber-400 text-amber-600" : c.status === "one_time" ? "border-blue-400 text-blue-600" : ""}>
                    {c.status === "service_call" ? "Service Call" : c.status === "one_time" ? "One-time" : c.status.charAt(0).toUpperCase() + c.status.slice(1)}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      {hasMore && !loading && (
        <div className="border-t px-4 py-2 text-center">
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => fetchPage(items.length, true)} disabled={loadingMore}>
            {loadingMore ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
            Load More ({total - items.length} remaining)
          </Button>
        </div>
      )}
    </div>
  );
}
