"use client";

import { useState, useEffect, useCallback, useMemo, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  AlertTriangle,
  Wrench,
  Droplets,
  DoorOpen,
  DollarSign,
  MessageSquare,
  ClipboardList,
  UserCog,
  Package,
  ChevronDown,
  ChevronUp,
  Play,
  Copy,
} from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import { useCompose } from "@/components/email/compose-provider";
import { SectionJumpNav, type SectionNavItem } from "@/components/ui/section-jump-nav";
import { AlertsSection } from "@/components/customers/sections/alerts-section";
import { ServiceSummarySection } from "@/components/customers/sections/service-summary-section";
import { CommunicationSection } from "@/components/customers/sections/communication-section";
import { BillingSection } from "@/components/customers/sections/billing-section";
import { JobsSection } from "@/components/customers/sections/jobs-section";
import { WaterFeaturesSection } from "@/components/customers/sections/water-features-section";
import { SiteAccessSection } from "@/components/customers/sections/site-access-section";
import { AccountDetailsSection } from "@/components/customers/sections/account-details-section";
import { CustomerPartsTab } from "@/components/customers/customer-parts-tab";
import type { Customer, Property, Invoice } from "@/components/customers/customer-types";

interface SectionDef {
  id: string;
  label: string;
  icon: React.ElementType;
  defaultOpen: boolean;
  component: React.ReactNode;
}

function CollapsibleSectionWrapper({
  id,
  label,
  icon: Icon,
  defaultOpen,
  children,
}: {
  id: string;
  label: string;
  icon: React.ElementType;
  defaultOpen: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div id={id} className="scroll-mt-20">
      <Card className="shadow-sm">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors rounded-t-lg"
        >
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold">{label}</span>
          </div>
          {open ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </button>
        {open && <CardContent className="pt-0 pb-4">{children}</CardContent>}
      </Card>
    </div>
  );
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
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  const isTech = perms.role === "technician";
  const isAdmin = perms.canViewRates;
  const isManager = perms.role === "manager" || perms.role === "admin" || perms.role === "owner";

  const load = useCallback(async () => {
    try {
      const [c, p, inv] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
        perms.canViewInvoices
          ? api.get<{ items: Invoice[] }>(`/v1/invoices?customer_id=${id}`)
          : Promise.resolve({ items: [] as Invoice[] }),
      ]);
      setCustomer(c);
      setProperties(p.items);
      setInvoices(inv.items);
    } catch {
      toast.error("Failed to load client");
    } finally {
      setLoading(false);
    }
  }, [id, perms.canViewInvoices]);

  useEffect(() => { load(); }, [load]);

  // Identity
  const displayName = customer
    ? (customer as { display_name?: string }).display_name || customer.first_name
    : "";
  const TypeIcon = customer?.customer_type === "commercial" ? Building2 : Home;
  const primaryAddress = properties[0]
    ? `${properties[0].address}, ${properties[0].city}`
    : null;

  // Quick actions
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

  // Build section list based on role
  const sections = useMemo((): SectionDef[] => {
    if (!customer) return [];
    const all: SectionDef[] = [];

    // Alerts always first (renders nothing if no alerts)
    all.push({
      id: "alerts",
      label: "Alerts",
      icon: AlertTriangle,
      defaultOpen: true,
      component: <AlertsSection customerId={id} />,
    });

    if (isTech) {
      // Tech: site access first, then service, then water features
      all.push({
        id: "access",
        label: "Site Access",
        icon: DoorOpen,
        defaultOpen: true,
        component: <SiteAccessSection properties={properties} />,
      });
      all.push({
        id: "service",
        label: "Service",
        icon: Wrench,
        defaultOpen: true,
        component: <ServiceSummarySection customerId={id} customer={customer} properties={properties} />,
      });
      all.push({
        id: "wfs",
        label: "Water Features",
        icon: Droplets,
        defaultOpen: true,
        component: <WaterFeaturesSection customer={customer} properties={properties} perms={perms} onUpdate={load} />,
      });
      // Jobs — own only
      if (perms.can("jobs.view")) {
        all.push({
          id: "jobs",
          label: "Jobs",
          icon: ClipboardList,
          defaultOpen: false,
          component: <JobsSection customerId={id} />,
        });
      }
      all.push({
        id: "account",
        label: "Account Details",
        icon: UserCog,
        defaultOpen: false,
        component: <AccountDetailsSection customer={customer} perms={perms} onUpdate={(c) => setCustomer(c)} />,
      });
    } else {
      // Manager/Admin: service first, then communication, billing, etc.
      all.push({
        id: "service",
        label: "Service",
        icon: Wrench,
        defaultOpen: true,
        component: <ServiceSummarySection customerId={id} customer={customer} properties={properties} />,
      });
      if (perms.canViewInbox) {
        all.push({
          id: "communication",
          label: "Communication",
          icon: MessageSquare,
          defaultOpen: true,
          component: (
            <CommunicationSection
              customerId={id}
              customerEmail={customer.email || undefined}
              customerName={displayName}
            />
          ),
        });
      }
      if (isAdmin && perms.canViewInvoices) {
        all.push({
          id: "billing",
          label: "Invoices & Billing",
          icon: DollarSign,
          defaultOpen: true,
          component: <BillingSection customerId={id} customer={customer} invoices={invoices} />,
        });
      }
      if (perms.can("jobs.view")) {
        all.push({
          id: "jobs",
          label: "Jobs",
          icon: ClipboardList,
          defaultOpen: isManager && !isAdmin,
          component: <JobsSection customerId={id} />,
        });
      }
      if (perms.canViewProfitability) {
        all.push({
          id: "profitability",
          label: "Profitability",
          icon: DollarSign,
          defaultOpen: false,
          component: (
            <div className="text-sm text-muted-foreground py-2">
              <Link href={`/profitability/${id}`} className="text-primary hover:underline">
                View full profitability analysis
              </Link>
            </div>
          ),
        });
      }
      all.push({
        id: "wfs",
        label: "Water Features",
        icon: Droplets,
        defaultOpen: false,
        component: <WaterFeaturesSection customer={customer} properties={properties} perms={perms} onUpdate={load} />,
      });
      all.push({
        id: "access",
        label: "Site Access",
        icon: DoorOpen,
        defaultOpen: false,
        component: <SiteAccessSection properties={properties} />,
      });
      all.push({
        id: "account",
        label: "Account Details",
        icon: UserCog,
        defaultOpen: false,
        component: <AccountDetailsSection customer={customer} perms={perms} onUpdate={(c) => setCustomer(c)} />,
      });
      all.push({
        id: "parts",
        label: "Parts",
        icon: Package,
        defaultOpen: false,
        component: <CustomerPartsTab customer={customer} properties={properties} />,
      });
    }

    return all;
  }, [customer, id, properties, invoices, perms, isTech, isAdmin, isManager, displayName, load]);

  // Jump nav items (filter out alerts since it hides itself)
  const navItems = useMemo((): SectionNavItem[] =>
    sections
      .filter((s) => s.id !== "alerts")
      .map((s) => ({ id: s.id, label: s.label, icon: s.icon })),
    [sections]
  );

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
              <Badge variant="outline" className="text-xs hidden sm:inline-flex">{customer.company_name}</Badge>
            )}
            <Badge
              variant={customer.status === "active" ? "default" : customer.status === "service_call" ? "outline" : customer.status === "lead" || customer.status === "pending" ? "outline" : "secondary"}
              className={customer.status === "service_call" ? "border-blue-400 text-blue-600" : customer.status === "lead" || customer.status === "pending" ? "border-amber-400 text-amber-600" : customer.status === "one_time" ? "border-blue-400 text-blue-600" : ""}
            >
              {customer.status === "service_call" ? "Service Call" : customer.status === "one_time" ? "One-time" : (customer.status ?? "active").charAt(0).toUpperCase() + (customer.status ?? "active").slice(1)}
            </Badge>
          </div>
        </div>

        {/* Contact + address row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {customer.phone && (
            <a href={`tel:${customer.phone}`} className="flex items-center gap-1 hover:text-foreground transition-colors">
              <Phone className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{customer.phone}</span>
              <span className="sm:hidden">Call</span>
            </a>
          )}
          {customer.email && (
            <a href={`mailto:${customer.email}`} className="flex items-center gap-1 hover:text-foreground transition-colors">
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
            <span className="font-medium text-foreground">${customer.monthly_rate.toFixed(2)}/mo</span>
          )}
        </div>

        {/* Tech: gate code banner — mobile only */}
        {isTech && properties[0]?.gate_code && (
          <div className="sm:hidden bg-amber-50 dark:bg-amber-950/30 border border-amber-200 rounded-lg px-4 py-3 flex items-center justify-between">
            <div>
              <span className="text-xs text-amber-600 font-medium">Gate Code</span>
              <p className="text-lg font-bold">{properties[0].gate_code}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => { navigator.clipboard.writeText(properties[0].gate_code!); toast.success("Copied"); }}>
              <Copy className="h-3.5 w-3.5 mr-1" />
              Copy
            </Button>
          </div>
        )}

        {/* Tech: gate code — desktop */}
        {isTech && properties[0]?.gate_code && (
          <div className="hidden sm:flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Gate:</span>
            <span className="text-lg font-bold tracking-wider">{properties[0].gate_code}</span>
            {properties[0].dog_on_property && (
              <Badge variant="outline" className="border-amber-400 text-amber-600 text-xs">Dog</Badge>
            )}
          </div>
        )}

        {/* Quick actions — icon-only on mobile, text labels on desktop */}
        <div className="flex flex-wrap gap-2">
          {properties.length > 0 && (
            <Button variant="outline" size="sm" onClick={handleLogVisit}>
              <ClipboardCheck className="h-3.5 w-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">Log Visit</span>
            </Button>
          )}
          {customer.email && (
            <Button variant="outline" size="sm" onClick={handleNewEmail}>
              <Mail className="h-3.5 w-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">Send Email</span>
            </Button>
          )}
          {perms.canViewInvoices && (
            <Button variant="outline" size="sm" onClick={handleCreateInvoice}>
              <FileText className="h-3.5 w-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">Create Invoice</span>
            </Button>
          )}
        </div>
      </div>

      {/* Jump nav + sections */}
      <div className="flex gap-6">
        <SectionJumpNav sections={navItems} />
        <div className="flex-1 min-w-0 space-y-4">
          {sections.map((section) =>
            section.id === "alerts" ? (
              <div key={section.id} id={section.id} className="scroll-mt-20">
                {section.component}
              </div>
            ) : (
              <CollapsibleSectionWrapper
                key={section.id}
                id={section.id}
                label={section.label}
                icon={section.icon}
                defaultOpen={section.defaultOpen}
              >
                {section.component}
              </CollapsibleSectionWrapper>
            )
          )}
        </div>
      </div>

      {/* Floating Action Button — tech mobile only */}
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
