"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import {
  ArrowLeft,
  Loader2,
  Building2,
  Home,
  MapPin,
  Phone,
  Mail,
  ClipboardCheck,
  FileText,
  Copy,
  Play,
  Activity,
  Droplets,
  UserCog,
} from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import { useCompose } from "@/components/email/compose-provider";
import { AlertsSection } from "@/components/customers/sections/alerts-section";
import { ActivityTimelineSection } from "@/components/customers/sections/activity-timeline-section";
import { WaterFeaturesSection } from "@/components/customers/sections/water-features-section";
import { AccountDetailsSection } from "@/components/customers/sections/account-details-section";
import type { Customer, Property, Invoice } from "@/components/customers/customer-types";

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

  const handleCreateInvoice = () => {
    router.push(`/invoices/new?customer=${id}`);
  };

  if (loading || !customer) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="pb-20 sm:pb-0">
      {/* Back button */}
      <div className="mb-4">
        <Button variant="ghost" size="sm" className="shrink-0" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
      </div>

      {/* Identity Header */}
      <div className="mb-6 space-y-3">
        <div className="flex items-center gap-3">
          <TypeIcon className="h-6 w-6 sm:h-7 sm:w-7 text-muted-foreground shrink-0" />
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight truncate flex-1">
            {displayName}
          </h1>
          <div className="flex items-center gap-1.5 shrink-0">
            {customer.company_name && (
              <Badge variant="outline" className="text-xs hidden sm:inline-flex">
                {customer.company_name}
              </Badge>
            )}
            <Badge
              variant={
                customer.status === "active"
                  ? "default"
                  : customer.status === "service_call" || customer.status === "one_time"
                    ? "outline"
                    : customer.status === "lead" || customer.status === "pending"
                      ? "outline"
                      : "secondary"
              }
              className={
                customer.status === "service_call"
                  ? "border-blue-400 text-blue-600"
                  : customer.status === "lead" || customer.status === "pending"
                    ? "border-amber-400 text-amber-600"
                    : customer.status === "one_time"
                      ? "border-blue-400 text-blue-600"
                      : ""
              }
            >
              {customer.status === "service_call"
                ? "Service Call"
                : customer.status === "one_time"
                  ? "One-time"
                  : (customer.status ?? "active").charAt(0).toUpperCase() +
                    (customer.status ?? "active").slice(1)}
            </Badge>
          </div>
        </div>

        {/* Contact + address + balance row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {customer.phone && (
            <a
              href={`tel:${customer.phone}`}
              className="flex items-center gap-1 hover:text-foreground transition-colors"
            >
              <Phone className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{customer.phone}</span>
              <span className="sm:hidden">Call</span>
            </a>
          )}
          {customer.email && (
            <a
              href={`mailto:${customer.email}`}
              className="flex items-center gap-1 hover:text-foreground transition-colors"
            >
              <Mail className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{customer.email}</span>
              <span className="sm:hidden">Email</span>
            </a>
          )}
          {primaryAddress && (
            <Link
              href={`/map?wf=${properties[0].water_features?.[0]?.id || ""}`}
              className="flex items-center gap-1 hover:text-foreground transition-colors"
            >
              <MapPin className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{primaryAddress}</span>
              <span className="sm:hidden">{properties[0]?.city}</span>
            </Link>
          )}
          {perms.canViewRates && (
            <span className="font-medium text-foreground">
              ${customer.monthly_rate.toFixed(2)}/mo
            </span>
          )}
          {perms.canViewBalance && customer.balance !== 0 && (
            <Link
              href={`/invoices?customer_id=${id}`}
              className={`font-medium hover:underline ${customer.balance > 0 ? "text-red-600" : "text-green-600"}`}
            >
              Bal: ${Math.abs(customer.balance).toFixed(2)}
              {customer.balance > 0 ? " due" : " credit"}
            </Link>
          )}
        </div>

        {/* Tech: gate code banner -- mobile only */}
        {isTech && properties[0]?.gate_code && (
          <div className="sm:hidden bg-amber-50 dark:bg-amber-950/30 border border-amber-200 rounded-lg px-4 py-3 flex items-center justify-between">
            <div>
              <span className="text-xs text-amber-600 font-medium">Gate Code</span>
              <p className="text-lg font-bold">{properties[0].gate_code}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                navigator.clipboard.writeText(properties[0].gate_code!);
                toast.success("Copied");
              }}
            >
              <Copy className="h-3.5 w-3.5 mr-1" />
              Copy
            </Button>
          </div>
        )}

        {/* Tech: gate code -- desktop */}
        {isTech && properties[0]?.gate_code && (
          <div className="hidden sm:flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Gate:</span>
            <span className="text-lg font-bold tracking-wider">{properties[0].gate_code}</span>
            {properties[0].dog_on_property && (
              <Badge variant="outline" className="border-amber-400 text-amber-600 text-xs">
                Dog
              </Badge>
            )}
          </div>
        )}

        {/* Quick actions */}
        <div className="flex flex-wrap gap-2">
          {properties.length > 0 && (
            <Button variant="outline" size="sm" onClick={handleLogVisit}>
              <Play className="h-3.5 w-3.5 mr-1.5" />
              Log Visit
            </Button>
          )}
          {customer.email && (
            <Button variant="outline" size="sm" onClick={handleNewEmail}>
              <Mail className="h-3.5 w-3.5 mr-1.5" />
              Email
            </Button>
          )}
          {perms.canViewInvoices && (
            <Button variant="outline" size="sm" onClick={() => router.push(`/invoices?customer_id=${id}`)}>
              <FileText className="h-3.5 w-3.5 mr-1.5" />
              Invoices
            </Button>
          )}
        </div>
      </div>

      {/* Alerts (auto-hides when no alerts) */}
      <AlertsSection customerId={id} />

      {/* Sections */}
      <div className="space-y-4 mt-4">
        {/* Activity Timeline */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <Activity className="h-4 w-4 text-muted-foreground" />
              Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ActivityTimelineSection
              customerId={id}
              customerEmail={customer.email || undefined}
              customerName={displayName}
              properties={properties}
            />
          </CardContent>
        </Card>

        {/* Properties & Pools */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <Droplets className="h-4 w-4 text-muted-foreground" />
              Properties & Pools
            </CardTitle>
          </CardHeader>
          <CardContent>
            <WaterFeaturesSection
              customer={customer}
              properties={properties}
              perms={perms}
              onUpdate={load}
            />
          </CardContent>
        </Card>

        {/* Account Details */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <UserCog className="h-4 w-4 text-muted-foreground" />
              Account
            </CardTitle>
          </CardHeader>
          <CardContent>
            <AccountDetailsSection
              customer={customer}
              perms={perms}
              onUpdate={(c) => setCustomer(c)}
            />
          </CardContent>
        </Card>
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
