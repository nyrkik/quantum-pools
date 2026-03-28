"use client";

import { useState, useEffect, useCallback, useMemo, use, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  ArrowLeft,
  Loader2,
  Building2,
  Home,
  MapPin,
  Mail,
  Play,
} from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import { useCompose } from "@/components/email/compose-provider";
import { AlertsSection } from "@/components/customers/sections/alerts-section";
import { AccountTile } from "@/components/customers/tiles/account-tile";
import { CommunicationsTile } from "@/components/customers/tiles/communications-tile";
import { InvoicesTile } from "@/components/customers/tiles/invoices-tile";
import { PropertyTile } from "@/components/customers/tiles/property-tile";
import type { Customer, Property } from "@/components/customers/customer-types";

type RoleKey = "tech" | "manager" | "admin";

interface TileDef {
  id: string;
  component: ReactNode;
  order: Record<RoleKey, number>;
}

export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const perms = usePermissions();
  const { openCompose } = useCompose();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);

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
  const primaryAddress = properties[0]
    ? `${properties[0].address}, ${properties[0].city}`
    : null;

  const handleLogVisit = () => {
    const propId = properties[0]?.id;
    if (propId) router.push(`/visits/new?property=${propId}`);
  };

  const handleNewEmail = () => {
    if (!customer) return;
    openCompose({
      to: customer.email || undefined,
      customerId: customer.id,
      customerName: displayName,
    });
  };

  const roleKey: RoleKey = isTech ? "tech" : isAdmin ? "admin" : "manager";

  const tiles = useMemo(() => {
    if (!customer) return [];

    const all: TileDef[] = [];

    // Always visible
    all.push({
      id: "account",
      component: (
        <AccountTile
          customer={customer}
          perms={perms}
          onUpdate={(c) => setCustomer(c)}
        />
      ),
      order: { tech: 4, manager: 1, admin: 1 },
    });
    all.push({
      id: "property",
      component: (
        <PropertyTile
          properties={properties}
          preferredDay={customer.preferred_day}
        />
      ),
      order: { tech: 1, manager: 3, admin: 4 },
    });

    // Permission-gated
    if (perms.canViewInbox) {
      all.push({
        id: "communications",
        component: <CommunicationsTile customerId={id} />,
        order: { tech: 5, manager: 2, admin: 2 },
      });
    }
    if (perms.canViewInvoices) {
      all.push({
        id: "invoices",
        component: <InvoicesTile customerId={id} />,
        order: { tech: 99, manager: 99, admin: 3 },
      });
    }

    return all
      .filter((t) => t.order[roleKey] < 99)
      .sort((a, b) => a.order[roleKey] - b.order[roleKey]);
  }, [customer, properties, perms, id, roleKey]);

  if (loading || !customer) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="pb-20 sm:pb-0">
      {/* Top bar */}
      <div className="mb-4 space-y-1">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <TypeIcon className="h-5 w-5 text-muted-foreground shrink-0" />
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight truncate">
                {displayName}
              </h1>
            </div>
            {primaryAddress && (
              <p className="text-sm text-muted-foreground ml-7 truncate">{primaryAddress}</p>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {perms.canViewBalance && customer.balance !== 0 && (
              <Link
                href={`/invoices?customer_id=${id}`}
                className={`text-sm font-medium hover:underline ${customer.balance > 0 ? "text-red-600" : "text-green-600"}`}
              >
                ${Math.abs(customer.balance).toFixed(2)}
                {customer.balance > 0 ? " due" : " cr"}
              </Link>
            )}
            {customer.email && perms.canViewInbox && (
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleNewEmail}>
                <Mail className="h-4 w-4" />
              </Button>
            )}
            {isTech && properties.length > 0 && (
              <Button size="sm" onClick={handleLogVisit}>
                <Play className="h-3.5 w-3.5 mr-1.5" />
                Start Visit
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Alerts */}
      <AlertsSection customerId={id} />

      {/* Tile grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {tiles.map((t) => (
          <div key={t.id}>{t.component}</div>
        ))}
      </div>

      {/* Floating Action Button -- tech mobile only */}
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
