"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
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
  first_name: string | null;
  last_name: string | null;
  display_name: string | null;
  email: string | null;
  phone: string | null;
  role: string;
  receives_estimates: boolean;
  receives_invoices: boolean;
  receives_service_updates: boolean;
  is_primary: boolean;
  notes: string | null;
}

interface ContactForm {
  id: string | null;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  role: string;
  receives_estimates: boolean;
  receives_invoices: boolean;
  receives_service_updates: boolean;
  is_primary: boolean;
  _delete?: boolean;
}

const ROLE_LABELS: Record<string, string> = {
  billing: "Billing",
  property_manager: "Property Mgr",
  regional_manager: "Regional Mgr",
  maintenance: "Maintenance",
};

const ROLE_COLORS: Record<string, string> = {
  billing: "bg-green-100 text-green-700",
  property_manager: "bg-purple-100 text-purple-700",
  regional_manager: "bg-indigo-100 text-indigo-700",
  maintenance: "bg-orange-100 text-orange-700",
};

function contactToForm(c: Contact): ContactForm {
  return {
    id: c.id,
    first_name: c.first_name || "",
    last_name: c.last_name || "",
    email: c.email || "",
    phone: c.phone || "",
    role: c.role,
    receives_estimates: c.receives_estimates,
    receives_invoices: c.receives_invoices,
    receives_service_updates: c.receives_service_updates,
    is_primary: c.is_primary,
  };
}

function newContactForm(): ContactForm {
  return {
    id: null,
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    role: "other",
    receives_estimates: false,
    receives_invoices: false,
    receives_service_updates: false,
    is_primary: false,
  };
}

interface ContactsTileProps {
  customerId: string;
  canEdit?: boolean;
}

export function ContactsTile({ customerId, canEdit = true }: ContactsTileProps) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [forms, setForms] = useState<ContactForm[]>([]);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const originalForms = useRef<string>("");

  const isDirty = useMemo(() => {
    if (!editing) return false;
    return JSON.stringify(forms) !== originalForms.current;
  }, [editing, forms]);

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

  const startEdit = () => {
    const initial = contacts.map(contactToForm);
    setForms(initial);
    originalForms.current = JSON.stringify(initial);
    setEditing(true);
  };

  const cancelEdit = () => {
    if (isDirty) {
      setConfirmCancel(true);
      return;
    }
    setEditing(false);
    setForms([]);
  };

  const confirmDiscardAndClose = () => {
    setConfirmCancel(false);
    setEditing(false);
    setForms([]);
  };

  const addContact = () => {
    setForms((f) => [...f, newContactForm()]);
  };

  const updateForm = (index: number, field: string, value: unknown) => {
    setForms((prev) =>
      prev.map((f, i) => {
        if (i !== index) {
          // If setting primary, clear it on others
          if (field === "is_primary" && value === true) {
            return { ...f, is_primary: false };
          }
          return f;
        }
        return { ...f, [field]: value };
      })
    );
  };

  const markDelete = (index: number) => {
    setForms((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    // Validate: each contact needs email or phone
    const active = forms.filter((f) => !f._delete);
    for (const f of active) {
      if (!f.email.trim() && !f.phone.trim()) {
        toast.error("Each contact needs an email or phone");
        return;
      }
    }

    setSaving(true);
    try {
      // Delete removed contacts
      const formIds = new Set(active.map((f) => f.id).filter(Boolean));
      for (const c of contacts) {
        if (!formIds.has(c.id)) {
          await api.delete(`/v1/customers/${customerId}/contacts/${c.id}`);
        }
      }

      // Create/update contacts
      for (const f of active) {
        const payload = {
          first_name: f.first_name.trim() || null,
          last_name: f.last_name.trim() || null,
          email: f.email.trim() || null,
          phone: f.phone.trim() || null,
          role: f.role,
          receives_estimates: f.receives_estimates,
          receives_invoices: f.receives_invoices,
          receives_service_updates: f.receives_service_updates,
          is_primary: f.is_primary,
        };

        if (f.id) {
          await api.put(`/v1/customers/${customerId}/contacts/${f.id}`, payload);
        } else {
          await api.post(`/v1/customers/${customerId}/contacts`, payload);
        }
      }

      toast.success("Contacts saved");
      setEditing(false);
      load();
    } catch {
      toast.error("Failed to save contacts");
    } finally {
      setSaving(false);
    }
  };

  // --- VIEW MODE ---
  const renderView = () => (
    <>
      {contacts.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-3">No contacts yet</p>
      ) : (
        contacts.map((c) => (
          <div key={c.id} className="py-2 px-2 space-y-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium">{c.display_name || c.email || c.phone || "Unknown"}</span>
              {c.is_primary && <Star className="h-3 w-3 text-amber-500 fill-amber-500" />}
              {c.role && c.role !== "other" && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${ROLE_COLORS[c.role] || ROLE_COLORS.other}`}>
                  {ROLE_LABELS[c.role] || c.role}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
              {c.email && c.display_name && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Mail className="h-3 w-3" /> {c.email}
                </span>
              )}
              {c.phone && (
                <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                  <Phone className="h-3 w-3" /> {c.phone}
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
        ))
      )}
    </>
  );

  // --- EDIT MODE ---
  const renderEditForm = (f: ContactForm, index: number) => (
    <div key={f.id || `new-${index}`} className="p-3 bg-background rounded-md border space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {f.is_primary && <Star className="h-3 w-3 text-amber-500 fill-amber-500" />}
          <span className="text-xs font-medium text-muted-foreground">
            {(f.role && ROLE_LABELS[f.role]) || "Contact"}
            {!f.id && " (new)"}
          </span>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => markDelete(index)}>
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">First Name</Label>
          <Input value={f.first_name} onChange={(e) => updateForm(index, "first_name", e.target.value)} className="h-8 text-sm" placeholder="If known" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Last Name</Label>
          <Input value={f.last_name} onChange={(e) => updateForm(index, "last_name", e.target.value)} className="h-8 text-sm" placeholder="If known" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Email</Label>
          <Input value={f.email} onChange={(e) => updateForm(index, "email", e.target.value)} className="h-8 text-sm" type="email" placeholder="email@example.com" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Phone</Label>
          <Input value={f.phone} onChange={(e) => updateForm(index, "phone", e.target.value)} className="h-8 text-sm" placeholder="(555) 555-1234" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Role</Label>
          <Select value={f.role || ""} onValueChange={(v) => updateForm(index, "role", v || null)}>
            <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="None" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="billing">Billing</SelectItem>
              <SelectItem value="property_manager">Property Manager</SelectItem>
              <SelectItem value="regional_manager">Regional Manager</SelectItem>
              <SelectItem value="maintenance">Maintenance</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={f.is_primary} onCheckedChange={(v) => updateForm(index, "is_primary", !!v)} />
            <span className="text-xs">Primary Contact</span>
          </label>
        </div>
      </div>
      <div className="space-y-2 pt-1">
        <Label className="text-xs text-muted-foreground">Receives</Label>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={f.receives_estimates} onCheckedChange={(v) => updateForm(index, "receives_estimates", !!v)} />
            <span className="text-xs">Estimates</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={f.receives_invoices} onCheckedChange={(v) => updateForm(index, "receives_invoices", !!v)} />
            <span className="text-xs">Invoices</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={f.receives_service_updates} onCheckedChange={(v) => updateForm(index, "receives_service_updates", !!v)} />
            <span className="text-xs">Service Updates</span>
          </label>
        </div>
      </div>
    </div>
  );

  return (
    <Card className={`shadow-sm ${editing ? (isDirty ? "border-l-4 border-amber-400" : "border-l-4 border-primary") : ""}`}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            Contacts
            {contacts.length > 0 && !editing && (
              <span className="text-xs font-normal text-muted-foreground">({contacts.length})</span>
            )}
          </div>
          {canEdit && !editing && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={startEdit}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
          )}
          {editing && isDirty && (
            <div className="flex items-center gap-1">
              <Button size="sm" variant="default" className="h-7 px-3 text-xs" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Check className="h-3 w-3 mr-1" />}
                Save
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={cancelEdit}>
                Cancel
              </Button>
            </div>
          )}
          {editing && !isDirty && (
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => { setEditing(false); setForms([]); }}>
              Done
            </Button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : editing ? (
          <div className="space-y-2 bg-muted/50 rounded-md p-2">
            {forms.map((f, i) => renderEditForm(f, i))}
            <Button variant="outline" size="sm" className="w-full h-8 text-xs" onClick={addContact}>
              <Plus className="h-3 w-3 mr-1" /> Add Contact
            </Button>
          </div>
        ) : (
          renderView()
        )}
      </CardContent>

      {/* Discard confirmation */}
      <AlertDialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard changes?</AlertDialogTitle>
            <AlertDialogDescription>
              You have unsaved changes to contacts. Discard them?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep Editing</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDiscardAndClose}>Discard</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
