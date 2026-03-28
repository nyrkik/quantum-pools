"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { UserCog, Phone, Pencil, Check, X, Loader2 } from "lucide-react";
import type { Permissions } from "@/lib/permissions";
import type { Customer } from "../customer-types";

interface AccountTileProps {
  customer: Customer;
  perms: Permissions;
  onUpdate: (customer: Customer) => void;
}

const STATUS_BADGE_MAP: Record<string, { variant: "default" | "secondary" | "outline"; className?: string }> = {
  active: { variant: "default" },
  inactive: { variant: "secondary" },
  lead: { variant: "outline", className: "border-amber-400 text-amber-600" },
  pending: { variant: "outline", className: "border-amber-400 text-amber-600" },
  service_call: { variant: "outline", className: "border-blue-400 text-blue-600" },
  one_time: { variant: "outline", className: "border-blue-400 text-blue-600" },
};

function statusLabel(s: string) {
  if (s === "service_call") return "Service Call";
  if (s === "one_time") return "One-time";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function AccountTile({ customer, perms, onUpdate }: AccountTileProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ ...customer });

  const displayName =
    (customer as { display_name?: string }).display_name ||
    `${customer.first_name} ${customer.last_name}`;
  const badge = STATUS_BADGE_MAP[customer.status] ?? { variant: "secondary" as const };

  const set = (field: string, value: unknown) =>
    setForm((f) => ({ ...f, [field]: value }));

  const dirty =
    form.first_name !== customer.first_name ||
    form.last_name !== customer.last_name ||
    form.company_name !== customer.company_name ||
    form.phone !== customer.phone ||
    form.customer_type !== customer.customer_type ||
    form.status !== customer.status ||
    form.notes !== customer.notes;

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/v1/customers/${customer.id}`, {
        first_name: form.first_name,
        last_name: form.last_name,
        company_name: form.company_name || null,
        customer_type: form.customer_type,
        phone: form.phone || null,
        status: form.status,
        is_active: form.status === "active",
        notes: form.notes || null,
      });
      toast.success("Account updated");
      setEditing(false);
      onUpdate({ ...customer, ...form });
    } catch {
      toast.error("Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setForm({ ...customer });
    setEditing(false);
  };

  if (editing) {
    return (
      <Card className={`shadow-sm ${dirty ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-primary"}`}>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm font-semibold">
            <span className="flex items-center gap-2">
              <UserCog className="h-4 w-4 text-muted-foreground" />
              Account
            </span>
            <div className="flex gap-1.5">
              {dirty && (
                <>
                  <Button variant="default" size="sm" className="h-7 px-2.5 text-xs" onClick={handleSave} disabled={saving}>
                    {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                  </Button>
                  <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={handleCancel}>Cancel</Button>
                </>
              )}
              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={handleCancel}>
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">First Name</Label>
              <Input value={form.first_name} onChange={(e) => set("first_name", e.target.value)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Last Name</Label>
              <Input value={form.last_name} onChange={(e) => set("last_name", e.target.value)} className="h-8 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Company</Label>
              <Input value={form.company_name ?? ""} onChange={(e) => set("company_name", e.target.value)} placeholder="Optional" className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Type</Label>
              <Select value={form.customer_type} onValueChange={(v) => set("customer_type", v)}>
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="residential">Residential</SelectItem>
                  <SelectItem value="commercial">Commercial</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Phone</Label>
              <Input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Status</Label>
              <Select value={form.status} onValueChange={(v) => set("status", v)}>
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                  <SelectItem value="lead">Lead</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="service_call">Service Call</SelectItem>
                  <SelectItem value="one_time">One-time</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Notes</Label>
            <Textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={3} className="text-sm" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <span className="flex items-center gap-2">
            <UserCog className="h-4 w-4 text-muted-foreground" />
            Account
          </span>
          <div className="flex items-center gap-1.5">
            <Badge variant={badge.variant} className={badge.className}>
              {statusLabel(customer.status)}
            </Badge>
            {perms.canEditCustomers && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setForm({ ...customer }); setEditing(true); }}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-sm space-y-1">
          <p className="font-medium">{displayName}</p>
          {customer.company_name && (
            <p className="text-muted-foreground">{customer.company_name}</p>
          )}
          <p className="text-xs text-muted-foreground capitalize">{customer.customer_type}</p>
        </div>
        {customer.phone && (
          <a
            href={`tel:${customer.phone}`}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <Phone className="h-3.5 w-3.5" />
            {customer.phone}
          </a>
        )}
        {customer.notes && (
          <p className="text-sm text-muted-foreground line-clamp-2 border-t pt-2">
            {customer.notes}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
