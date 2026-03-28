"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Pencil, Check, X, Loader2 } from "lucide-react";
import type { Permissions } from "@/lib/permissions";
import type { Customer } from "../customer-types";

interface AccountDetailsSectionProps {
  customer: Customer;
  perms: Permissions;
  onUpdate: (customer: Customer) => void;
}

export function AccountDetailsSection({ customer, perms, onUpdate }: AccountDetailsSectionProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ ...customer });
  const displayName = (customer as { display_name?: string }).display_name || `${customer.first_name} ${customer.last_name}`;

  const set = (field: string, value: unknown) => setForm((f) => ({ ...f, [field]: value }));

  const dirty =
    form.first_name !== customer.first_name ||
    form.last_name !== customer.last_name ||
    form.company_name !== customer.company_name ||
    form.email !== customer.email ||
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
        email: form.email || null,
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

  // Notes inline edit (separate from full edit)
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesValue, setNotesValue] = useState(customer.notes ?? "");
  const [notesSaving, setNotesSaving] = useState(false);

  const saveNotes = useCallback(async () => {
    setNotesSaving(true);
    try {
      await api.put(`/v1/customers/${customer.id}`, { notes: notesValue });
      onUpdate({ ...customer, notes: notesValue });
      setEditingNotes(false);
      toast.success("Notes saved");
    } catch {
      toast.error("Failed to save notes");
    } finally {
      setNotesSaving(false);
    }
  }, [customer, notesValue, onUpdate]);

  if (editing) {
    return (
      <div className={`space-y-3 ${dirty ? "border-l-4 border-l-amber-400 pl-3" : "border-l-4 border-l-primary pl-3"}`}>
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Edit Account</p>
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
        </div>
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
            <Label className="text-xs">Email</Label>
            <Input value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Phone</Label>
            <Input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} className="h-8 text-sm" />
          </div>
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
        <div className="space-y-1.5">
          <Label className="text-xs">Notes</Label>
          <Textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={3} className="text-sm" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Identity info */}
      <div className="flex items-start justify-between">
        <div className="text-sm space-y-1">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1">
            <div><span className="text-muted-foreground">Name: </span>{displayName}</div>
            <div><span className="text-muted-foreground">Type: </span><span className="capitalize">{customer.customer_type}</span></div>
            {customer.company_name && <div><span className="text-muted-foreground">Company: </span>{customer.company_name}</div>}
            <div><span className="text-muted-foreground">Email: </span>{customer.email || "\u2014"}</div>
            <div><span className="text-muted-foreground">Phone: </span>{customer.phone || "\u2014"}</div>
            <div><span className="text-muted-foreground">Status: </span><span className="capitalize">{customer.status}</span></div>
          </div>
          <div className="text-xs text-muted-foreground pt-1">
            Created {new Date(customer.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </div>
        </div>
        {perms.canEditCustomers && (
          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => { setForm({ ...customer }); setEditing(true); }}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Notes */}
      <div className="border-t pt-2">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Notes</p>
          {!editingNotes && perms.canEditCustomers && (
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => { setNotesValue(customer.notes ?? ""); setEditingNotes(true); }}>
              <Pencil className="h-3 w-3" />
            </Button>
          )}
          {editingNotes && (
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-green-600" onClick={saveNotes} disabled={notesSaving}>
                {notesSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              </Button>
              <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={() => { setNotesValue(customer.notes ?? ""); setEditingNotes(false); }}>
                <X className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>
        {editingNotes ? (
          <Textarea
            value={notesValue}
            onChange={(e) => setNotesValue(e.target.value)}
            rows={3}
            placeholder="Add notes..."
            className="text-sm"
          />
        ) : customer.notes ? (
          <p className="text-sm whitespace-pre-wrap">{customer.notes}</p>
        ) : (
          <p className="text-sm text-muted-foreground">No notes</p>
        )}
      </div>
    </div>
  );
}
