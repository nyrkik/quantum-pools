"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Users,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Loader2,
  Mail,
  Phone,
  Star,
} from "lucide-react";

interface Contact {
  id: string;
  customer_id: string;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  role: string;
  receives_estimates: boolean;
  receives_invoices: boolean;
  receives_service_updates: boolean;
  is_primary: boolean;
  notes: string | null;
}

const ROLE_LABELS: Record<string, string> = {
  primary: "Primary",
  billing: "Billing",
  property_manager: "Property Mgr",
  maintenance: "Maintenance",
  other: "Other",
};

const ROLE_COLORS: Record<string, string> = {
  primary: "bg-blue-100 text-blue-700",
  billing: "bg-green-100 text-green-700",
  property_manager: "bg-purple-100 text-purple-700",
  maintenance: "bg-orange-100 text-orange-700",
  other: "bg-slate-100 text-slate-700",
};

const EMPTY_FORM = {
  name: "",
  title: "",
  email: "",
  phone: "",
  role: "primary",
  receives_estimates: false,
  receives_invoices: false,
  receives_service_updates: false,
  is_primary: false,
};

interface ContactsTileProps {
  customerId: string;
  canEdit?: boolean;
}

export function ContactsTile({ customerId, canEdit = true }: ContactsTileProps) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const load = useCallback(async () => {
    try {
      const data = await api.get<Contact[]>(`/v1/customers/${customerId}/contacts`);
      setContacts(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    load();
  }, [load]);

  const set = (field: string, value: unknown) =>
    setForm((f) => ({ ...f, [field]: value }));

  const startAdd = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setAdding(true);
  };

  const startEdit = (c: Contact) => {
    setAdding(false);
    setEditingId(c.id);
    setForm({
      name: c.name,
      title: c.title || "",
      email: c.email || "",
      phone: c.phone || "",
      role: c.role,
      receives_estimates: c.receives_estimates,
      receives_invoices: c.receives_invoices,
      receives_service_updates: c.receives_service_updates,
      is_primary: c.is_primary,
    });
  };

  const cancel = () => {
    setEditingId(null);
    setAdding(false);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("Name is required");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        title: form.title.trim() || null,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        role: form.role,
        receives_estimates: form.receives_estimates,
        receives_invoices: form.receives_invoices,
        receives_service_updates: form.receives_service_updates,
        is_primary: form.is_primary,
      };

      if (adding) {
        await api.post(`/v1/customers/${customerId}/contacts`, payload);
        toast.success("Contact added");
      } else if (editingId) {
        await api.put(`/v1/customers/${customerId}/contacts/${editingId}`, payload);
        toast.success("Contact updated");
      }
      cancel();
      load();
    } catch {
      toast.error("Failed to save contact");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/v1/customers/${customerId}/contacts/${id}`);
      toast.success("Contact removed");
      load();
    } catch {
      toast.error("Failed to delete");
    }
  };

  const renderForm = () => (
    <div className="space-y-3 p-3 bg-muted/50 rounded-md border">
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Name *</Label>
          <Input value={form.name} onChange={(e) => set("name", e.target.value)} className="h-8 text-sm" placeholder="Full name" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Title</Label>
          <Input value={form.title} onChange={(e) => set("title", e.target.value)} className="h-8 text-sm" placeholder="e.g. Facility Manager" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Email</Label>
          <Input value={form.email} onChange={(e) => set("email", e.target.value)} className="h-8 text-sm" type="email" placeholder="email@example.com" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Phone</Label>
          <Input value={form.phone} onChange={(e) => set("phone", e.target.value)} className="h-8 text-sm" placeholder="(555) 555-1234" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Role</Label>
          <Select value={form.role} onValueChange={(v) => set("role", v)}>
            <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="primary">Primary</SelectItem>
              <SelectItem value="billing">Billing</SelectItem>
              <SelectItem value="property_manager">Property Manager</SelectItem>
              <SelectItem value="maintenance">Maintenance</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={form.is_primary} onCheckedChange={(v) => set("is_primary", !!v)} />
            <span className="text-xs">Primary Contact</span>
          </label>
        </div>
      </div>

      <div className="space-y-2 pt-1">
        <Label className="text-xs text-muted-foreground">Receives</Label>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={form.receives_estimates} onCheckedChange={(v) => set("receives_estimates", !!v)} />
            <span className="text-xs">Estimates</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={form.receives_invoices} onCheckedChange={(v) => set("receives_invoices", !!v)} />
            <span className="text-xs">Invoices</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={form.receives_service_updates} onCheckedChange={(v) => set("receives_service_updates", !!v)} />
            <span className="text-xs">Service Updates</span>
          </label>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <Button size="sm" className="h-7 px-3 text-xs" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Check className="h-3 w-3 mr-1" />}
          {adding ? "Add" : "Save"}
        </Button>
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={cancel}>Cancel</Button>
      </div>
    </div>
  );

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            Contacts
          </div>
          {canEdit && !adding && !editingId && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={startAdd}>
              <Plus className="h-3.5 w-3.5" />
            </Button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : contacts.length === 0 && !adding ? (
          <p className="text-xs text-muted-foreground text-center py-3">No contacts yet</p>
        ) : (
          <>
            {contacts.map((c) =>
              editingId === c.id ? (
                <div key={c.id}>{renderForm()}</div>
              ) : (
                <div
                  key={c.id}
                  className="flex items-start gap-3 py-2 px-2 rounded-md hover:bg-muted/50 group"
                >
                  <div className="flex-1 min-w-0 space-y-0.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{c.name}</span>
                      {c.is_primary && (
                        <Star className="h-3 w-3 text-amber-500 fill-amber-500" />
                      )}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${ROLE_COLORS[c.role] || ROLE_COLORS.other}`}>
                        {ROLE_LABELS[c.role] || c.role}
                      </span>
                    </div>
                    {c.title && (
                      <p className="text-xs text-muted-foreground">{c.title}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                      {c.email && (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          <Mail className="h-3 w-3" />
                          {c.email}
                        </span>
                      )}
                      {c.phone && (
                        <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                          <Phone className="h-3 w-3" />
                          {c.phone}
                        </a>
                      )}
                    </div>
                    {(c.receives_estimates || c.receives_invoices || c.receives_service_updates) && (
                      <div className="flex flex-wrap gap-1 pt-0.5">
                        {c.receives_estimates && <Badge variant="outline" className="text-[9px] h-4 px-1">Estimates</Badge>}
                        {c.receives_invoices && <Badge variant="outline" className="text-[9px] h-4 px-1">Invoices</Badge>}
                        {c.receives_service_updates && <Badge variant="outline" className="text-[9px] h-4 px-1">Updates</Badge>}
                      </div>
                    )}
                  </div>
                  {canEdit && (
                    <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => startEdit(c)}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive">
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete contact?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Remove {c.name} from this customer&apos;s contacts. This cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleDelete(c.id)}>Delete</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  )}
                </div>
              )
            )}
          </>
        )}
        {adding && renderForm()}
      </CardContent>
    </Card>
  );
}
