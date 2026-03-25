"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { ArrowLeft, Loader2 } from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import type { PropertyPhoto } from "@/types/photo";
import type { Customer, WaterFeature, Property, Invoice, RateSplitData } from "@/components/customers/customer-types";
import { CustomerSidebar, type ViewTab } from "@/components/customers/customer-sidebar";
import { CustomerServiceTab } from "@/components/customers/customer-service-tab";
import { CustomerOverviewTab } from "@/components/customers/customer-overview-tab";
import { CustomerWfsTab } from "@/components/customers/customer-wfs-tab";
import { CustomerInvoicesTab } from "@/components/customers/customer-invoices-tab";

export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const perms = usePermissions();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [heroImages, setHeroImages] = useState<Record<string, PropertyPhoto>>({});
  const [fullWfs, setFullBows] = useState<WaterFeature[]>([]);
  const [techAssignments, setTechAssignments] = useState<Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>>({});
  const isTech = perms.role === "technician";
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const validTabs = ["overview", "service", "details", "wfs", "invoices"] as const;
  const resolvedTab = tabParam === "details" && !isTech ? "overview" : tabParam;
  const initialTab = validTabs.includes(resolvedTab as typeof validTabs[number]) ? (resolvedTab as typeof validTabs[number]) : isTech ? "service" : "overview";
  const [viewTab, setViewTab] = useState<ViewTab>(initialTab);
  const [selectedWfId, setSelectedBowId] = useState<string | null>(null);
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null);
  const [scrollToPropId, setScrollToPropId] = useState<string | null>(null);
  const [editingDetails, setEditingDetails] = useState(false);
  const [showDiscardDialog, setShowDiscardDialog] = useState(false);
  const [discardTarget, setDiscardTarget] = useState<"details" | null>(null);
  const [wfProfitability, setBowProfitability] = useState<Record<string, { margin_pct: number; suggested_rate: number }>>({});
  const [showRateSplit, setShowRateSplit] = useState(false);
  const [rateSplitData, setRateSplitData] = useState<RateSplitData | null>(null);
  const [rateSplitEdits, setRateSplitEdits] = useState<Record<string, number>>({});
  const [rateSplitSaving, setRateSplitSaving] = useState(false);
  const [propRates, setPropRates] = useState<Record<string, number>>({});
  const [propRatesDirty, setPropRatesDirty] = useState(false);
  const [companies, setCompanies] = useState<string[]>([]);
  const [newCompanyCustom, setNewCompanyCustom] = useState("");

  // Customer edit form state
  const [custForm, setCustForm] = useState<Customer | null>(null);
  const [custSaving, setCustSaving] = useState(false);
  const [custDirty, setCustDirty] = useState(false);

  // Single-property inline edit state
  const singleProp = properties.length <= 1 ? properties[0] ?? null : null;
  const [propForm, setPropForm] = useState<Property | null>(null);
  const [propDirty, setPropDirty] = useState(false);

  useEffect(() => {
    if (singleProp) setPropForm(singleProp);
  }, [singleProp?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const rates: Record<string, number> = {};
    properties.forEach(p => { rates[p.id] = p.monthly_rate ?? 0; });
    setPropRates(rates);
    setPropRatesDirty(false);
  }, [properties]);

  const setPropField = (field: string, value: unknown) => {
    setPropForm((f) => f ? { ...f, [field]: value } : f);
    setPropDirty(true);
  };

  const load = useCallback(async () => {
    try {
      const [c, p, inv, heroes, companyList] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
        api.get<{ items: Invoice[] }>(`/v1/invoices?customer_id=${id}`),
        api.get<Record<string, PropertyPhoto>>("/v1/photos/heroes").catch(() => ({})),
        api.get<string[]>("/v1/customers/companies").catch(() => []),
      ]);
      setCustomer(c);
      setCustForm(c);
      setProperties(p.items);
      setInvoices(inv.items);
      setHeroImages(heroes);
      setCompanies(companyList);
    } catch {
      toast.error("Failed to load client");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Auto-select first property for multi-property clients
  useEffect(() => {
    if (properties.length > 1 && !selectedPropertyId) {
      setSelectedPropertyId(properties[0].id);
    } else if (properties.length === 1) {
      setSelectedPropertyId(null);
    }
  }, [properties, selectedPropertyId]);

  const activeProperty = properties.length > 1
    ? properties.find(p => p.id === selectedPropertyId) || properties[0]
    : null;

  // Fetch full WF data + tech assignments for all properties
  useEffect(() => {
    if (properties.length === 0) return;
    Promise.all(
      properties.map((p) => api.get<WaterFeature[]>(`/v1/water-features/property/${p.id}`).catch(() => []))
    ).then((results) => setFullBows(results.flat()));
    api.get<Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>>("/v1/routes/tech-assignments")
      .then(setTechAssignments)
      .catch(() => setTechAssignments({}));
    // Fetch per-WF profitability
    api.get<Array<{ wf_id: string; margin_pct: number; suggested_rate: number; customer_id: string }>>("/v1/profitability/gaps")
      .then((gaps) => {
        const map: Record<string, { margin_pct: number; suggested_rate: number }> = {};
        for (const g of gaps) {
          if (g.customer_id === id) {
            map[g.wf_id] = { margin_pct: g.margin_pct, suggested_rate: g.suggested_rate };
          }
        }
        setBowProfitability(map);
      })
      .catch(() => setBowProfitability({}));
  }, [properties, id]);

  const setCustField = (field: string, value: unknown) => {
    setCustForm((f) => f ? { ...f, [field]: value } : f);
    setCustDirty(true);
  };

  const handleSaveCustomer = async () => {
    if (!custForm) return;
    setCustSaving(true);
    try {
      const promises: Promise<unknown>[] = [
        api.put(`/v1/customers/${id}`, {
          first_name: custForm.first_name, last_name: custForm.last_name,
          company_name: (custForm.company_name === "__new__" ? newCompanyCustom : custForm.company_name) || null, customer_type: custForm.customer_type,
          email: custForm.email || null, phone: custForm.phone || null,
          billing_address: custForm.billing_address || null, billing_city: custForm.billing_city || null,
          billing_state: custForm.billing_state || null, billing_zip: custForm.billing_zip || null,
          service_frequency: custForm.service_frequency || null, preferred_day: custForm.preferred_day || null,
          billing_frequency: custForm.billing_frequency,
          payment_method: custForm.payment_method || null, payment_terms_days: custForm.payment_terms_days,
          difficulty_rating: custForm.difficulty_rating, notes: custForm.notes || null,
          status: custForm.status,
          is_active: custForm.status === "active",
        }),
      ];
      if (propForm && propDirty && singleProp) {
        promises.push(api.put(`/v1/properties/${singleProp.id}`, {
          address: propForm.address, city: propForm.city, state: propForm.state, zip_code: propForm.zip_code,
          gate_code: propForm.gate_code || null, access_instructions: propForm.access_instructions || null,
          dog_on_property: propForm.dog_on_property, is_locked_to_day: propForm.is_locked_to_day,
          service_day_pattern: propForm.service_day_pattern || null, notes: propForm.notes || null,
        }));
      }
      await Promise.all(promises);
      if (propRatesDirty) {
        for (const [propId, rate] of Object.entries(propRates)) {
          const orig = properties.find(p => p.id === propId);
          if (orig && (orig.monthly_rate ?? 0) !== rate) {
            await api.put(`/v1/properties/${propId}`, { monthly_rate: rate });
          }
        }
      }
      toast.success("Client updated");
      setCustDirty(false);
      setPropDirty(false);
      setPropRatesDirty(false);
      setNewCompanyCustom("");
      setEditingDetails(false);
      load();
    } catch {
      toast.error("Failed to update client");
    } finally {
      setCustSaving(false);
    }
  };

  const openRateSplit = async () => {
    try {
      const data = await api.get<RateSplitData>(`/v1/profitability/allocate-rates/${id}`);
      setRateSplitData(data);
      const edits: Record<string, number> = {};
      for (const a of data?.allocations || []) {
        edits[a.wf_id] = a.proposed_rate;
      }
      setRateSplitEdits(edits);
      setShowRateSplit(true);
    } catch {
      toast.error("Failed to load rate allocation");
    }
  };

  const applyRateSplit = async () => {
    setRateSplitSaving(true);
    try {
      await api.post(`/v1/profitability/apply-rates/${id}`, { rates: rateSplitEdits });
      toast.success("Rates applied");
      setShowRateSplit(false);
      load();
    } catch {
      toast.error("Failed to apply rates");
    } finally {
      setRateSplitSaving(false);
    }
  };

  const wfsNeedRateSplit = fullWfs.length > 1 && fullWfs.some(b => b.monthly_rate == null) && (customer?.monthly_rate ?? 0) > 0;

  if (!customer || !custForm) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const handleCancelCustomer = () => {
    setCustForm(customer);
    setCustDirty(false);
  };

  const handleCancelProperty = () => {
    if (singleProp) setPropForm(singleProp);
    setPropDirty(false);
    const rates: Record<string, number> = {};
    properties.forEach(p => { rates[p.id] = p.monthly_rate ?? 0; });
    setPropRates(rates);
    setPropRatesDirty(false);
  };

  const handleExitDetails = () => {
    if (custDirty || propDirty || propRatesDirty) {
      setDiscardTarget("details");
      setShowDiscardDialog(true);
    } else {
      setEditingDetails(false);
    }
  };

  const handleDiscardAndExit = () => {
    if (discardTarget === "details") {
      setCustDirty(false);
      setPropDirty(false);
      setCustForm(customer);
      if (singleProp) setPropForm(singleProp);
      setEditingDetails(false);
    }
    setShowDiscardDialog(false);
    setDiscardTarget(null);
    load();
  };

  return (
    <div className="pb-20 sm:pb-0">
      {/* Unsaved changes guard */}
      <AlertDialog open={showDiscardDialog} onOpenChange={setShowDiscardDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unsaved changes</AlertDialogTitle>
            <AlertDialogDescription>You have unsaved changes. Discard them?</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction onClick={handleDiscardAndExit} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Discard</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Back button */}
      <div className="mb-4">
        <Button variant="ghost" size="sm" className="shrink-0" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
      </div>

      {/* Two-column layout: sidebar + main */}
      <div className="flex flex-col lg:flex-row gap-6">
        <CustomerSidebar
          customer={customer}
          properties={properties}
          invoices={invoices}
          perms={perms}
          isTech={isTech}
          viewTab={viewTab}
          selectedPropertyId={selectedPropertyId}
          activeProperty={activeProperty}
          onTabChange={setViewTab}
          onPropertySelect={setSelectedPropertyId}
        />

        {/* Main content */}
        <div className="flex-1 min-w-0 space-y-4">
          {viewTab === "service" && (
            <CustomerServiceTab customer={customer} properties={properties} />
          )}

          {viewTab === "overview" && (
            <CustomerOverviewTab
              customer={customer}
              properties={properties}
              invoices={invoices}
              heroImages={heroImages}
              perms={perms}
              activeProperty={activeProperty}
              editingDetails={editingDetails}
              custForm={custForm}
              custDirty={custDirty}
              custSaving={custSaving}
              propForm={propForm}
              propDirty={propDirty}
              propRates={propRates}
              propRatesDirty={propRatesDirty}
              companies={companies}
              newCompanyCustom={newCompanyCustom}
              singleProp={singleProp}
              onTabChange={setViewTab}
              onWfSelect={setSelectedBowId}
              onScrollToProp={setScrollToPropId}
              onEditDetails={() => setEditingDetails(true)}
              onExitDetails={handleExitDetails}
              onSaveCustomer={handleSaveCustomer}
              onCancelCustomer={handleCancelCustomer}
              onCancelProperty={handleCancelProperty}
              setCustField={setCustField}
              setPropField={setPropField}
              setPropRates={setPropRates}
              setPropRatesDirty={setPropRatesDirty}
              setNewCompanyCustom={setNewCompanyCustom}
            />
          )}

          {viewTab === "wfs" && (
            <CustomerWfsTab
              customer={customer}
              customerId={id}
              properties={properties}
              fullWfs={fullWfs}
              heroImages={heroImages}
              techAssignments={techAssignments}
              wfProfitability={wfProfitability}
              perms={perms}
              activeProperty={activeProperty}
              selectedWfId={selectedWfId}
              scrollToPropId={scrollToPropId}
              wfsNeedRateSplit={wfsNeedRateSplit}
              showRateSplit={showRateSplit}
              rateSplitData={rateSplitData}
              rateSplitEdits={rateSplitEdits}
              rateSplitSaving={rateSplitSaving}
              onTabChange={setViewTab}
              onWfSelect={setSelectedBowId}
              onScrollToPropClear={() => setScrollToPropId(null)}
              onOpenRateSplit={openRateSplit}
              onCloseRateSplit={() => setShowRateSplit(false)}
              onApplyRateSplit={applyRateSplit}
              onRateSplitEditChange={(wfId, value) => setRateSplitEdits(prev => ({ ...prev, [wfId]: value }))}
              onLoad={load}
            />
          )}

          {viewTab === "invoices" && perms.canViewInvoices && (
            <CustomerInvoicesTab invoices={invoices} />
          )}
        </div>
      </div>
    </div>
  );
}
