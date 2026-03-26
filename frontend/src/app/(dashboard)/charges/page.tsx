"use client";

import { useState, useEffect, useCallback } from "react";
import { api, getBackendOrigin } from "@/lib/api";
import { toast } from "sonner";
import { usePermissions } from "@/lib/permissions";
import { PendingCharges } from "@/components/charges/pending-charges";
import { AddChargeSheet } from "@/components/charges/add-charge-sheet";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Receipt, Loader2, ImageIcon } from "lucide-react";

interface Charge {
  id: string;
  description: string;
  amount: number;
  category: string;
  status: string;
  photo_url: string | null;
  notes: string | null;
  customer_name: string | null;
  property_address: string | null;
  creator_name: string | null;
  created_at: string | null;
  requires_approval: boolean;
}

const STATUS_BADGES: Record<string, { variant: "default" | "secondary" | "outline" | "destructive"; label: string }> = {
  pending: { variant: "outline", label: "Pending" },
  approved: { variant: "default", label: "Approved" },
  rejected: { variant: "destructive", label: "Rejected" },
  invoiced: { variant: "secondary", label: "Invoiced" },
};

export default function ChargesPage() {
  const perms = usePermissions();
  const [charges, setCharges] = useState<Charge[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const loadCharges = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      params.set("limit", "200");
      const data = await api.get<Charge[]>(`/v1/visit-charges?${params}`);
      setCharges(data);
    } catch {
      // Techs may not have list permission — that's OK
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadCharges();
  }, [loadCharges, refreshKey]);

  const refresh = () => setRefreshKey((k) => k + 1);

  const canApprove = perms.can("invoices.edit") || perms.role === "owner" || perms.role === "admin";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Charges</h1>
          {pendingCount > 0 && (
            <Badge variant="outline" className="border-amber-400 text-amber-600">
              {pendingCount} pending
            </Badge>
          )}
        </div>
        {/* The AddChargeSheet needs a property/customer — it's mainly used from visit pages.
            On this page we show a disabled hint. */}
      </div>

      {/* Pending approval */}
      {canApprove && (
        <PendingCharges
          onCountChange={setPendingCount}
          refreshKey={refreshKey}
        />
      )}

      {/* Recent charges table */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Recent Charges</CardTitle>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[140px] h-8 text-sm">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
                <SelectItem value="invoiced">Invoiced</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : charges.length === 0 ? (
            <div className="text-center py-8">
              <Receipt className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No charges found</p>
            </div>
          ) : (
            <div className="overflow-x-auto -mx-6">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-100 dark:bg-slate-800">
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Description</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Customer</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Amount</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Category</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Status</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Tech</TableHead>
                    <TableHead className="text-xs font-medium uppercase tracking-wide">Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {charges.map((charge, idx) => {
                    const sb = STATUS_BADGES[charge.status] || STATUS_BADGES.pending;
                    return (
                      <TableRow
                        key={charge.id}
                        className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                      >
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {charge.photo_url && (
                              <img
                                src={`${getBackendOrigin()}${charge.photo_url}`}
                                alt=""
                                className="h-8 w-8 rounded object-cover flex-shrink-0"
                              />
                            )}
                            <span className="text-sm">{charge.description}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {charge.customer_name || "—"}
                        </TableCell>
                        <TableCell className="text-sm font-medium text-right">
                          ${charge.amount.toFixed(2)}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-[10px]">
                            {charge.category}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={sb.variant}
                            className={
                              charge.status === "pending"
                                ? "border-amber-400 text-amber-600"
                                : ""
                            }
                          >
                            {sb.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {charge.creator_name || "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {charge.created_at
                            ? new Date(charge.created_at).toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                              })
                            : "—"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
