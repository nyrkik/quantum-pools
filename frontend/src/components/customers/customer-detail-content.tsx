"use client";

import { useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowLeft,
  Loader2,
  Building2,
  Home,
  MapPin,
  Phone,
  Play,
  Pencil,
  X,
  Check,
} from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import { AlertsSection } from "@/components/customers/sections/alerts-section";
import { AccessTile } from "@/components/customers/tiles/access-tile";
import { WaterFeaturesTile } from "@/components/customers/tiles/water-features-tile";
import { InspectionsTile } from "@/components/customers/tiles/inspections-tile";
import { CommunicationsTile } from "@/components/customers/tiles/communications-tile";
import { InvoicesTile } from "@/components/customers/tiles/invoices-tile";
import { VisitsTile } from "@/components/customers/tiles/visits-tile";
import { ContactsTile } from "@/components/customers/tiles/contacts-tile";
import type { Customer, Property } from "@/components/customers/customer-types";

type RoleKey = "tech" | "manager" | "admin";

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

interface TileDef {
  id: string;
  component: ReactNode;
  order: Record<RoleKey, number>;
  column: "left" | "right";
}

interface CustomerDetailContentProps {
  id: string;
  onClose?: () => void;  // If provided, renders close button instead of back button
  compact?: boolean;     // If true, uses single-column layout
}

export function CustomerDetailContent({ id, onClose, compact }: CustomerDetailContentProps) {
  const router = useRouter();
  const perms = usePermissions();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    first_name: "", last_name: "", company_name: "", phone: "",
    customer_type: "", status: "", notes: "",
  });
  const originalForm = useRef("");

  const isDirty = useMemo(() => {
    if (!editing) return false;
    return JSON.stringify(form) !== originalForm.current;
  }, [editing, form]);

  const isTech = perms.role === "technician";
  const isAdmin = perms.role === "admin" || perms.role === "owner";

  const load = useCallback(async () => {
    try {
      const [c, p] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
      ]);
      setCustomer(c);
      setProperties(p.items);
    } catch {
      toast.error("Failed to load client");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const displayName = customer
    ? (customer as { display_name?: string }).display_name || customer.first_name
    : "";
  const TypeIcon = customer?.customer_type === "commercial" ? Building2 : Home;
  const statusBadge = STATUS_BADGE_MAP[customer?.status ?? ""] ?? { variant: "secondary" as const };
  const primaryAddress = properties[0]
    ? `${properties[0].address}, ${properties[0].city}`
    : null;

  const handleLogVisit = () => {
    const propId = properties[0]?.id;
    if (propId) router.push(`/visits/new?property=${propId}`);
  };

  const startEdit = () => {
    if (!customer) return;
    const initial = {
      first_name: customer.first_name,
      last_name: customer.last_name,
      company_name: customer.company_name || "",
      phone: customer.phone || "",
      customer_type: customer.customer_type,
      status: customer.status,
      notes: customer.notes || "",
    };
    setForm(initial);
    originalForm.current = JSON.stringify(initial);
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/v1/customers/${id}`, {
        first_name: form.first_name,
        last_name: form.last_name,
        company_name: form.company_name || null,
        phone: form.phone || null,
        customer_type: form.customer_type,
        status: form.status,
        is_active: form.status === "active",
        notes: form.notes || null,
      });
      toast.success("Client updated");
      setEditing(false);
      load();
    } catch {
      toast.error("Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const roleKey: RoleKey = isTech ? "tech" : isAdmin ? "admin" : "manager";

  const tiles = useMemo(() => {
    if (!customer) return [];

    const all: TileDef[] = [];

    all.push({
      id: "access",
      component: <AccessTile properties={properties} preferredDay={customer.preferred_day} />,
      order: { tech: 1, manager: 1, admin: 1 },
      column: "left",
    });
    all.push({
      id: "visits",
      component: <VisitsTile properties={properties} />,
      order: { tech: 2, manager: 2, admin: 2 },
      column: "left",
    });
    all.push({
      id: "water-features",
      component: <WaterFeaturesTile properties={properties} />,
      order: { tech: 3, manager: 3, admin: 3 },
      column: "left",
    });
    all.push({
      id: "inspections",
      component: <InspectionsTile properties={properties} />,
      order: { tech: 5, manager: 5, admin: 5 },
      column: "left",
    });

    if (perms.canViewInbox) {
      all.push({
        id: "communications",
        component: <CommunicationsTile customerId={id} customerEmail={customer.email} customerName={displayName} />,
        order: { tech: 4, manager: 4, admin: 4 },
        column: "right",
      });
    }
    if (perms.canEditCustomers) {
      all.push({
        id: "contacts",
        component: <ContactsTile customerId={id} canEdit={perms.canEditCustomers} />,
        order: { tech: 99, manager: 5, admin: 5 },
        column: "right",
      });
    }
    if (perms.canViewInvoices) {
      all.push({
        id: "invoices",
        component: <InvoicesTile customerId={id} />,
        order: { tech: 99, manager: 99, admin: 6 },
        column: "right",
      });
    }

    return all
      .filter((t) => t.order[roleKey] < 99)
      .sort((a, b) => a.order[roleKey] - b.order[roleKey]);
  }, [customer, properties, perms, id, roleKey, displayName]);

  if (loading || !customer) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="pb-20 sm:pb-0">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-start gap-2">
          {onClose ? (
            <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 mt-0.5" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          ) : (
            <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 mt-0.5" onClick={() => router.back()}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}
          {editing ? (
            /* Edit mode */
            <div className="flex-1 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs">First Name</Label>
                  <Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="h-8 text-sm" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Last Name</Label>
                  <Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="h-8 text-sm" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs">Phone</Label>
                  <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="h-8 text-sm" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Company</Label>
                  <Input value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} className="h-8 text-sm" placeholder="Optional" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs">Type</Label>
                  <Select value={form.customer_type} onValueChange={(v) => setForm({ ...form, customer_type: v })}>
                    <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="residential">Residential</SelectItem>
                      <SelectItem value="commercial">Commercial</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Status</Label>
                  <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
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
              <div className="flex gap-2">
                {isDirty ? (
                  <>
                    <Button size="sm" onClick={handleSave} disabled={saving}>
                      {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Check className="h-3 w-3 mr-1" />}
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                  </>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Done</Button>
                )}
              </div>
            </div>
          ) : (
            /* View mode */
            <>
              <div className="flex-1 min-w-0 space-y-0.5">
                <div className="flex items-center gap-2">
                  <TypeIcon className="h-5 w-5 text-muted-foreground shrink-0" />
                  <h1 className="text-xl sm:text-2xl font-bold tracking-tight truncate">
                    {displayName}
                  </h1>
                  <Badge variant={statusBadge.variant} className={`${statusBadge.className || ""} text-[10px] shrink-0`}>
                    {statusLabel(customer.status)}
                  </Badge>
                </div>
                {primaryAddress && (
                  <a
                    href={`https://maps.google.com/?q=${encodeURIComponent(primaryAddress)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors truncate"
                  >
                    <MapPin className="h-3.5 w-3.5 shrink-0" />
                    {primaryAddress}
                  </a>
                )}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5">
                  {customer.phone && (
                    <a href={`tel:${customer.phone}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
                      <Phone className="h-3.5 w-3.5" />
                      {customer.phone}
                    </a>
                  )}
                  {customer.company_name && (
                    <span className="text-sm text-muted-foreground">{customer.company_name}</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0 mt-1">
                {perms.canViewBalance && customer.balance !== 0 && (
                  <Link
                    href={`/invoices?customer_id=${id}`}
                    className={`text-sm font-medium hover:underline ${customer.balance > 0 ? "text-red-600" : "text-green-600"}`}
                  >
                    ${Math.abs(customer.balance).toFixed(2)}
                    {customer.balance > 0 ? " due" : " cr"}
                  </Link>
                )}
                {perms.canEditCustomers && (
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={startEdit}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                )}
                {isTech && properties.length > 0 && (
                  <Button size="sm" onClick={handleLogVisit}>
                    <Play className="h-3.5 w-3.5 mr-1.5" />
                    Start Visit
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <AlertsSection customerId={id} />

      {/* Single column for overlay/compact mode */}
      {compact ? (
        <div className="mt-4 space-y-4">
          {tiles.map((t) => (
            <div key={t.id}>{t.component}</div>
          ))}
        </div>
      ) : (
        <>
          {/* Mobile: single column */}
          <div className="mt-4 space-y-4 lg:hidden">
            {tiles.map((t) => (
              <div key={t.id}>{t.component}</div>
            ))}
          </div>

          {/* Desktop: two columns */}
          <div className="mt-4 hidden lg:grid gap-4" style={{ gridTemplateColumns: "2fr 3fr" }}>
            <div className="space-y-4 min-w-0">
              {tiles.filter((t) => t.column === "left").map((t) => (
                <div key={t.id}>{t.component}</div>
              ))}
            </div>
            {tiles.some((t) => t.column === "right") && (
              <div className="space-y-4 min-w-0">
                {tiles.filter((t) => t.column === "right").map((t) => (
                  <div key={t.id}>{t.component}</div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {isTech && properties.length > 0 && (
        <div className="fixed bottom-6 right-6 sm:hidden z-30">
          <Button size="lg" className="rounded-full h-14 w-14 shadow-lg" onClick={handleLogVisit}>
            <Play className="h-6 w-6" />
          </Button>
        </div>
      )}
    </div>
  );
}
