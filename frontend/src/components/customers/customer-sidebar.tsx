"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Building2,
  Home,
  MapPin,
  ClipboardCheck,
  LayoutDashboard,
  Droplets,
  Receipt,
  History,
} from "lucide-react";
import type { Permissions } from "@/lib/permissions";
import type { Customer, Property, Invoice } from "./customer-types";

function SiteDetails({ property, className }: { property: Property; className?: string }) {
  const items: string[] = [];
  if (property.gate_code) items.push(`Gate: ${property.gate_code}`);
  if (property.dog_on_property) items.push("Dog on property");
  if (property.access_instructions) items.push(property.access_instructions);
  if (items.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground ${className || ""}`}>
      {items.map((item, i) => (
        <span key={i} className={item === "Dog on property" ? "text-amber-600 font-medium" : ""}>{item}</span>
      ))}
    </div>
  );
}

const validTabs = ["overview", "service", "details", "wfs", "invoices"] as const;
export type ViewTab = typeof validTabs[number];

interface CustomerSidebarProps {
  customer: Customer;
  properties: Property[];
  invoices: Invoice[];
  perms: Permissions;
  isTech: boolean;
  viewTab: ViewTab;
  selectedPropertyId: string | null;
  activeProperty: Property | null;
  onTabChange: (tab: ViewTab) => void;
  onPropertySelect: (id: string) => void;
}

export function CustomerSidebar({
  customer,
  properties,
  invoices,
  perms,
  isTech,
  viewTab,
  selectedPropertyId,
  activeProperty,
  onTabChange,
  onPropertySelect,
}: CustomerSidebarProps) {
  const TypeIcon = customer.customer_type === "commercial" ? Building2 : Home;
  const displayName = (customer as { display_name?: string }).display_name || customer.first_name;

  return (
    <div className="lg:w-72 lg:shrink-0 space-y-4">
      {/* Client card — identity + address + contact + billing */}
      <Card className="shadow-sm">
        <CardContent className="pt-4 pb-4 space-y-3">
          {/* Name + badges */}
          <div className="flex items-center gap-3">
            <TypeIcon className="h-6 w-6 text-muted-foreground shrink-0" />
            <h1 className="text-xl font-bold tracking-tight truncate flex-1">
              {displayName}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {customer.company_name && (
              <Badge variant="outline" className="text-xs">{customer.company_name}</Badge>
            )}
            <Badge
              variant={customer.status === "active" ? "default" : customer.status === "service_call" ? "outline" : customer.status === "lead" || customer.status === "pending" ? "outline" : "secondary"}
              className={customer.status === "service_call" ? "border-blue-400 text-blue-600" : customer.status === "lead" || customer.status === "pending" ? "border-amber-400 text-amber-600" : customer.status === "one_time" ? "border-blue-400 text-blue-600" : ""}
            >
              {customer.status === "service_call" ? "Service Call" : customer.status === "one_time" ? "One-time" : (customer.status ?? "active").charAt(0).toUpperCase() + (customer.status ?? "active").slice(1)}
            </Badge>
          </div>

          {/* Property badges — multi-property */}
          {properties.length > 1 && (
            <div className="flex flex-wrap gap-1.5 pt-1 border-t">
              {properties.map((prop) => (
                <button
                  key={prop.id}
                  onClick={() => onPropertySelect(prop.id)}
                  className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                    selectedPropertyId === prop.id
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background text-muted-foreground border-border hover:bg-muted"
                  }`}
                >
                  <MapPin className="h-3 w-3 inline mr-1" />
                  {prop.name || prop.address.split(",")[0]}
                </button>
              ))}
            </div>
          )}

          {/* Address */}
          {properties.length === 1 && (
            <div className="text-sm space-y-0.5 pt-1 border-t">
              <div className="flex items-start gap-1.5 pt-1.5">
                <Link href={`/map?wf=${(properties[0].water_features?.[0]?.id) || ""}`} title="View on map">
                  <MapPin className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground hover:text-primary transition-colors" />
                </Link>
                <span>{properties[0].address}, {properties[0].city}, {properties[0].state} {properties[0].zip_code}</span>
              </div>
              {!isTech && <SiteDetails property={properties[0]} className="ml-5" />}
            </div>
          )}
          {properties.length > 1 && activeProperty && !isTech && (() => {
            const details: string[] = [];
            if (activeProperty.gate_code) details.push(`Gate: ${activeProperty.gate_code}`);
            if (activeProperty.dog_on_property) details.push("Dog on property");
            if (activeProperty.access_instructions) details.push(activeProperty.access_instructions);
            return details.length > 0 ? <SiteDetails property={activeProperty} /> : null;
          })()}

          {/* Site access — prominent for techs */}
          {isTech && properties.length >= 1 && (
            <div className="text-sm space-y-1.5 pt-1 border-t">
              <div className="pt-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
                <div><span className="text-muted-foreground">Gate: </span><span className="font-medium">{properties[0].gate_code || "None"}</span></div>
                <div>{properties[0].dog_on_property ? <span className="text-amber-600 font-medium">Dog on property</span> : <span className="text-muted-foreground">No dog</span>}</div>
              </div>
              {properties[0].access_instructions && (
                <div><span className="text-muted-foreground">Access: </span>{properties[0].access_instructions}</div>
              )}
            </div>
          )}

          {/* Contact */}
          <div className="text-sm space-y-1 pt-1 border-t">
            <div className="pt-1.5"><span className="text-muted-foreground">Email: </span>{customer.email || "\u2014"}</div>
            <div><span className="text-muted-foreground">Phone: </span>{customer.phone || "\u2014"}</div>
          </div>

          {/* Billing summary */}
          {perms.canViewRates && (
            <div className="text-sm space-y-1 pt-1 border-t">
              <div className="pt-1.5"><span className="text-muted-foreground">Rate: </span>${customer.monthly_rate.toFixed(2)}/mo</div>
              <div>
                <span className="text-muted-foreground">Balance: </span>
                <span className={customer.balance > 0 ? "text-red-600 font-medium" : ""}>${customer.balance.toFixed(2)}</span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Nav tiles — desktop: vertical stack, mobile: horizontal scroll */}
      <div className="flex lg:flex-col gap-2 overflow-x-auto lg:overflow-visible pb-1 lg:pb-0">
        {[
          { key: "overview" as const, icon: LayoutDashboard, label: "Overview" },
          { key: "service" as const, icon: ClipboardCheck, label: "Service" },
          { key: "wfs" as const, icon: Droplets, label: "Water Features" },
          ...(perms.canViewInvoices ? [{ key: "invoices" as const, icon: Receipt, label: "Invoices" }] : []),
        ].map((nav) => (
          <button
            key={nav.key}
            onClick={() => onTabChange(nav.key)}
            className={`flex items-center gap-3 rounded-lg border px-4 py-2 text-sm font-medium transition-colors shrink-0 lg:w-full ${
              viewTab === nav.key
                ? "bg-accent border-primary/30 shadow-sm font-semibold"
                : "bg-background hover:bg-muted/50 border-border"
            }`}
          >
            <nav.icon className={`h-5 w-5 ${viewTab === nav.key ? "text-primary" : "text-muted-foreground"}`} />
            {nav.label}
            {nav.key === "invoices" && (() => {
              const outstanding = invoices.reduce((sum, inv) => sum + inv.balance, 0);
              return outstanding > 0
                ? <span className={`ml-auto text-xs ${viewTab === "invoices" ? "opacity-80" : "text-red-600"}`}>${outstanding.toFixed(2)}</span>
                : invoices.length > 0 ? <span className={`ml-auto text-xs ${viewTab === "invoices" ? "opacity-80" : "text-muted-foreground"}`}>({invoices.length})</span> : null;
            })()}
          </button>
        ))}
      </div>
    </div>
  );
}
