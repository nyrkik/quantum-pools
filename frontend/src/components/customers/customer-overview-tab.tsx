"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DollarSign,
  Receipt,
  Droplets,
  Clock,
  MapPin,
  ClipboardCheck,
  Mail,
  FileText,
  Pencil,
  Check,
  X,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useCompose } from "@/components/email/compose-provider";
import type { Permissions } from "@/lib/permissions";
import type { Customer, Property, Invoice } from "./customer-types";
import type { ViewTab } from "./customer-sidebar";

interface CustomerOverviewTabProps {
  customer: Customer;
  properties: Property[];
  invoices: Invoice[];
  perms: Permissions;
  onTabChange: (tab: ViewTab) => void;
  onCustomerUpdate?: (customer: Customer) => void;
}

export function CustomerOverviewTab({
  customer,
  properties,
  invoices,
  perms,
  onTabChange,
  onCustomerUpdate,
}: CustomerOverviewTabProps) {
  const router = useRouter();
  const { openCompose } = useCompose();
  const outstandingTotal = invoices.reduce((sum, inv) => sum + inv.balance, 0);
  const allWfs = properties.flatMap(p => p.water_features || []);
  const wfCount = allWfs.length;
  const displayName = (customer as { display_name?: string }).display_name || customer.first_name;

  // Notes inline edit
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState(customer.notes ?? "");
  const [notesSaving, setNotesSaving] = useState(false);

  const saveNotes = useCallback(async () => {
    setNotesSaving(true);
    try {
      await api.put(`/v1/customers/${customer.id}`, { notes: notesValue });
      onCustomerUpdate?.({ ...customer, notes: notesValue });
      setEditingNotes(false);
      toast.success("Notes saved");
    } catch {
      toast.error("Failed to save notes");
    } finally {
      setNotesSaving(false);
    }
  }, [customer, notesValue, onCustomerUpdate]);

  const cancelNotes = () => {
    setNotesValue(customer.notes ?? "");
    setEditingNotes(false);
  };

  // Quick action handlers
  const handleLogVisit = () => {
    const propId = properties[0]?.id;
    if (propId) router.push(`/visits/new?property=${propId}`);
  };

  const handleNewEmail = () => {
    openCompose({
      to: customer.email || undefined,
      customerId: customer.id,
      customerName: displayName,
    });
  };

  const handleCreateInvoice = () => {
    router.push(`/invoices/new?customer=${customer.id}`);
  };

  // Alerts
  const alerts: Array<{ message: string; severity: "warning" | "error" }> = [];
  if (outstandingTotal > 0) {
    alerts.push({ message: `Overdue balance: $${outstandingTotal.toFixed(2)}`, severity: "error" });
  }

  return (
    <div className="space-y-4">
      {/* Metric tiles */}
      <div className={`grid grid-cols-2 ${perms.canViewRates ? "sm:grid-cols-4" : "sm:grid-cols-3"} gap-3`}>
        {perms.canViewRates && (
          <Link href={`/profitability/${customer.id}`}>
            <MetricCard icon={DollarSign} label="Monthly Rate" value={`$${customer.monthly_rate.toFixed(2)}`} />
          </Link>
        )}
        {perms.canViewBalance && (
          <button className="text-left" onClick={() => onTabChange("invoices")}>
            <MetricCard
              icon={Receipt}
              label="Balance"
              value={`$${customer.balance.toFixed(2)}`}
              highlight={outstandingTotal > 0}
            />
          </button>
        )}
        <button className="text-left" onClick={() => onTabChange("wfs")}>
          <MetricCard icon={Droplets} label="Water Features" value={String(wfCount)} />
        </button>
        <MetricCard icon={MapPin} label="Properties" value={String(properties.length)} />
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        {properties.length > 0 && (
          <Button variant="outline" size="sm" onClick={handleLogVisit}>
            <ClipboardCheck className="h-3.5 w-3.5 mr-1.5" />
            Log Visit
          </Button>
        )}
        {customer.email && (
          <Button variant="outline" size="sm" onClick={handleNewEmail}>
            <Mail className="h-3.5 w-3.5 mr-1.5" />
            New Email
          </Button>
        )}
        {perms.canViewInvoices && (
          <Button variant="outline" size="sm" onClick={handleCreateInvoice}>
            <FileText className="h-3.5 w-3.5 mr-1.5" />
            Create Invoice
          </Button>
        )}
      </div>

      {/* Active alerts */}
      {alerts.length > 0 && (
        <Card className="shadow-sm border-amber-200">
          <CardContent className="pt-3 pb-3 space-y-1.5">
            {alerts.map((alert, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <AlertTriangle className={`h-3.5 w-3.5 shrink-0 ${alert.severity === "error" ? "text-red-500" : "text-amber-500"}`} />
                <span className={alert.severity === "error" ? "text-red-600 font-medium" : "text-amber-600"}>
                  {alert.message}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Notes */}
      <Card className="shadow-sm">
        <CardHeader className="pb-0">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Notes</CardTitle>
            {!editingNotes && perms.canEditCustomers && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setNotesValue(customer.notes ?? ""); setEditingNotes(true); }}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
            {editingNotes && (
              <div className="flex gap-1">
                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-green-600" onClick={saveNotes} disabled={notesSaving}>
                  {notesSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                </Button>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={cancelNotes}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {editingNotes ? (
            <Textarea
              value={notesValue}
              onChange={(e) => setNotesValue(e.target.value)}
              rows={3}
              placeholder="Add notes about this customer..."
              className="text-sm"
            />
          ) : customer.notes ? (
            <p className="text-sm whitespace-pre-wrap">{customer.notes}</p>
          ) : (
            <p className="text-sm text-muted-foreground">No notes</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, highlight }: {
  icon: typeof DollarSign;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <Card className="shadow-sm hover:bg-muted/50 transition-colors">
      <CardContent className="pt-3 pb-3">
        <div className="flex items-center gap-2 mb-1">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</p>
        </div>
        <p className={`text-2xl font-bold ${highlight ? "text-red-600" : ""}`}>{value}</p>
      </CardContent>
    </Card>
  );
}
