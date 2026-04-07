"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  TooltipProvider,
} from "@/components/ui/tooltip";
import { Building2, Home } from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import { PageLayout } from "@/components/layout/page-layout";
import { Overlay, OverlayContent, OverlayBody } from "@/components/ui/overlay";
import { CustomerDetailContent } from "@/components/customers/customer-detail-content";
import { ClientSection, type SortKey, type SortDir } from "@/components/customers/client-section";
import { CreateClientDialog } from "@/components/customers/create-client-dialog";
import { CustomerFilterBar } from "@/components/customers/customer-filter-bar";

export default function CustomersPage() {
  const perms = usePermissions();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set(["active"]));
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [techAssignments, setTechAssignments] = useState<Record<string, Array<{ tech_name: string; color: string }>>>({});
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  useEffect(() => {
    api.get<Record<string, Array<{ tech_name: string; color: string }>>>("/v1/routes/tech-assignments")
      .then(setTechAssignments).catch(() => {});
  }, []);

  return (
    <PageLayout
      title="Clients"
      action={
        perms.canCreateCustomers ? (
          <CreateClientDialog
            refreshKey={refreshKey}
            onCreated={() => setRefreshKey(k => k + 1)}
          />
        ) : undefined
      }
    >
      <CustomerFilterBar
        search={search}
        onSearchChange={setSearch}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
      />

      <TooltipProvider>
        <div className="space-y-6">
          {(typeFilter === null || typeFilter === "commercial") && (
            <ClientSection
              key={`commercial-${refreshKey}`}
              customerType="commercial"
              title="Commercial"
              icon={Building2}
              perms={perms}
              search={search}
              statusFilter={statusFilter}
              sortKey={sortKey}
              sortDir={sortDir}
              onToggleSort={toggleSort}
              techAssignments={techAssignments}
              onSelectCustomer={setSelectedCustomerId}
            />
          )}
          {(typeFilter === null || typeFilter === "residential") && (
            <ClientSection
              key={`residential-${refreshKey}`}
              customerType="residential"
              title="Residential"
              icon={Home}
              perms={perms}
              search={search}
              statusFilter={statusFilter}
              sortKey={sortKey}
              sortDir={sortDir}
              onToggleSort={toggleSort}
              techAssignments={techAssignments}
              onSelectCustomer={setSelectedCustomerId}
            />
          )}
        </div>
      </TooltipProvider>

      <Overlay open={!!selectedCustomerId} onOpenChange={(o) => { if (!o) setSelectedCustomerId(null); }}>
        <OverlayContent className="max-w-3xl max-h-[92vh]">
          <OverlayBody className="p-0">
            {selectedCustomerId && (
              <div className="p-4">
                <CustomerDetailContent
                  id={selectedCustomerId}
                  onClose={() => setSelectedCustomerId(null)}
                  compact
                />
              </div>
            )}
          </OverlayBody>
        </OverlayContent>
      </Overlay>
    </PageLayout>
  );
}
