"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Pencil,
  X,
  Loader2,
  Droplets,
  Receipt,
  DollarSign,
  Clock,
  Calendar,
} from "lucide-react";
import type { Permissions } from "@/lib/permissions";
import type { Customer, Property, Invoice, PropertyPhoto } from "./customer-types";
import type { ViewTab } from "./customer-sidebar";
import { getBackendOrigin } from "@/lib/api";

const API_BASE = typeof window !== "undefined" ? getBackendOrigin() : "http://localhost:7061";

interface CustomerOverviewTabProps {
  customer: Customer;
  properties: Property[];
  invoices: Invoice[];
  heroImages: Record<string, PropertyPhoto>;
  perms: Permissions;
  activeProperty: Property | null;
  // Edit mode state
  editingDetails: boolean;
  custForm: Customer;
  custDirty: boolean;
  custSaving: boolean;
  propForm: Property | null;
  propDirty: boolean;
  propRates: Record<string, number>;
  propRatesDirty: boolean;
  companies: string[];
  newCompanyCustom: string;
  singleProp: Property | null;
  // Callbacks
  onTabChange: (tab: ViewTab) => void;
  onWfSelect: (id: string) => void;
  onScrollToProp: (id: string) => void;
  onEditDetails: () => void;
  onExitDetails: () => void;
  onSaveCustomer: () => void;
  onCancelCustomer: () => void;
  onCancelProperty: () => void;
  setCustField: (field: string, value: unknown) => void;
  setPropField: (field: string, value: unknown) => void;
  setPropRates: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  setPropRatesDirty: (dirty: boolean) => void;
  setNewCompanyCustom: (value: string) => void;
}

export function CustomerOverviewTab({
  customer,
  properties,
  invoices,
  heroImages,
  perms,
  activeProperty,
  editingDetails,
  custForm,
  custDirty,
  custSaving,
  propForm,
  propDirty,
  propRates,
  propRatesDirty,
  companies,
  newCompanyCustom,
  singleProp,
  onTabChange,
  onWfSelect,
  onScrollToProp,
  onEditDetails,
  onExitDetails,
  onSaveCustomer,
  onCancelCustomer,
  onCancelProperty,
  setCustField,
  setPropField,
  setPropRates,
  setPropRatesDirty,
  setNewCompanyCustom,
}: CustomerOverviewTabProps) {
  const unpaidInvoices = invoices.filter(inv => inv.balance > 0);
  const outstandingTotal = unpaidInvoices.reduce((sum, inv) => sum + inv.balance, 0);
  const paidInvoices = invoices.filter(inv => inv.status === "paid");
  const ytdRevenue = paidInvoices.reduce((sum, inv) => sum + inv.total, 0);
  const allWfs = properties.flatMap(p => p.water_features || []);
  // Suppress unused variable warning
  void ytdRevenue;

  return (
    <div className="space-y-4">
      {/* Metric cards */}
      <div className={`grid grid-cols-2 ${perms.canViewRates ? "lg:grid-cols-4" : "lg:grid-cols-2"} gap-3`}>
        {perms.canViewRates && (
          <Link href={`/profitability/${customer.id}`}>
            <Card className="shadow-sm hover:bg-muted/50 transition-colors cursor-pointer">
              <CardContent className="pt-3 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <DollarSign className="h-4 w-4 text-muted-foreground" />
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Monthly Rate</p>
                </div>
                <p className="text-2xl font-bold">${customer.monthly_rate.toFixed(2)}</p>
              </CardContent>
            </Card>
          </Link>
        )}
        {perms.canViewBalance && (
          <Card className={`shadow-sm hover:bg-muted/50 transition-colors cursor-pointer ${outstandingTotal > 0 ? "border-red-200" : ""}`} onClick={() => onTabChange("invoices")}>
            <CardContent className="pt-3 pb-3">
              <div className="flex items-center gap-2 mb-1">
                <Receipt className="h-4 w-4 text-muted-foreground" />
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Balance</p>
              </div>
              <p className={`text-2xl font-bold ${outstandingTotal > 0 ? "text-red-600" : ""}`}>
                ${customer.balance.toFixed(2)}
              </p>
            </CardContent>
          </Card>
        )}
        <Card className="shadow-sm">
          <CardContent className="pt-3 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Last Service</p>
            </div>
            <p className="text-2xl font-bold text-muted-foreground">&mdash;</p>
            <p className="text-xs text-muted-foreground">No visits recorded</p>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardContent className="pt-3 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Next Service</p>
            </div>
            <p className="text-2xl font-bold text-muted-foreground">&mdash;</p>
            <p className="text-xs text-muted-foreground">No schedule set</p>
          </CardContent>
        </Card>
      </div>

      {/* Two-column: outstanding invoices + pools */}
      <div className={`grid grid-cols-1 ${perms.canViewInvoices ? "lg:grid-cols-2" : ""} gap-4`}>
        {/* Outstanding invoices */}
        {perms.canViewInvoices && (
          <Card className="shadow-sm py-4 gap-3 h-full max-h-64 lg:max-h-none hover:bg-muted/50 transition-colors cursor-pointer" onClick={() => onTabChange("invoices")}>
            <CardHeader className="pb-0">
              <CardTitle className="text-sm">Invoices</CardTitle>
            </CardHeader>
            <CardContent className="overflow-y-auto">
              {invoices.length === 0 ? (
                <p className="text-sm text-muted-foreground py-3">No invoices</p>
              ) : (
                <div className="space-y-1.5">
                  {invoices.map((inv) => (
                    <div key={inv.id} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2 min-w-0">
                        <Link href={`/invoices/${inv.id}`} className="font-medium hover:underline shrink-0">{inv.invoice_number}</Link>
                        <span className="text-muted-foreground text-xs">{inv.issue_date}</span>
                      </div>
                      <span className={`shrink-0 ml-2 ${inv.balance > 0 ? "text-red-600 font-medium" : "text-muted-foreground"}`}>
                        ${inv.total.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Water Features summary */}
        <Card className="shadow-sm py-4 gap-3 h-full">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Water Features</CardTitle>
          </CardHeader>
          <CardContent>
            {(() => {
              const visibleProps = activeProperty ? [activeProperty] : properties;
              return (
              <div className="space-y-3">
                {visibleProps.map((prop) => {
                  const wfs = prop.water_features || [];
                  const hero = heroImages[prop.id];
                  return (
                    <div key={prop.id}>
                      {hero && (
                        <img
                          src={`${API_BASE}${hero.url}`}
                          alt="Property photo"
                          className="w-full h-28 object-cover rounded-md border mb-2"
                        />
                      )}
                      {/* Property-level service info */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground mb-2 px-1">
                        <span><span className="font-medium">Freq:</span> <span className="capitalize">{customer.service_frequency || "weekly"}</span></span>
                        <span><span className="font-medium">Days:</span> {customer.preferred_day
                          ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ")
                          : "Any"}</span>
                        {prop.gate_code && <span><span className="font-medium">Gate:</span> {prop.gate_code}</span>}
                        {prop.dog_on_property && <span className="text-amber-600 font-medium">Dog on property</span>}
                      </div>
                      <div className="space-y-2">
                        {wfs.length === 0 && (
                          <div className="bg-muted/50 rounded-md p-2.5 cursor-pointer hover:bg-muted/80 transition-colors" onClick={() => { onScrollToProp(prop.id); onTabChange("wfs"); }}>
                            <p className="text-xs text-muted-foreground">No water features — <span className="text-primary">add one</span></p>
                          </div>
                        )}
                        {wfs.map((wf) => (
                          <div key={wf.id} className="bg-muted/50 rounded-md p-2.5 cursor-pointer hover:bg-muted/80 transition-colors" onClick={() => { onWfSelect(wf.id); onTabChange("wfs"); }}>
                            <div className="flex items-center gap-2 mb-1.5">
                              <Droplets className="h-3.5 w-3.5 text-blue-500" />
                              <span className="font-medium text-sm capitalize">{wf.name || wf.water_type.replace("_", " ")}</span>
                              {wf.pool_type && (
                                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 capitalize ml-auto">{wf.pool_type}</Badge>
                              )}
                            </div>
                            <div className="grid grid-cols-3 gap-x-3 text-xs">
                              <div>
                                <span className="text-muted-foreground">Gallons</span>
                                <p className="font-medium">{wf.pool_gallons ? wf.pool_gallons.toLocaleString() : "\u2014"}</p>
                              </div>
                              <div>
                                <span className="text-muted-foreground">Service</span>
                                <p className="font-medium">{wf.estimated_service_minutes} min</p>
                              </div>
                              {wf.monthly_rate != null ? (
                                <div>
                                  <span className="text-muted-foreground">Rate</span>
                                  <p className="font-medium">${wf.monthly_rate.toFixed(2)}</p>
                                </div>
                              ) : wf.pool_sqft ? (
                                <div>
                                  <span className="text-muted-foreground">Size</span>
                                  <p className="font-medium">{wf.pool_sqft.toLocaleString()} ft²</p>
                                </div>
                              ) : (
                                <div />
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              );
            })()}
          </CardContent>
        </Card>
      </div>

      {/* ===== DETAILS (inline in overview) ===== */}
      <Card className={`shadow-sm py-4 gap-3 ${editingDetails ? `bg-muted/50 ${custDirty || propDirty || propRatesDirty ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-primary"}` : ""}`}>
        <CardHeader className="pb-0">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Details</CardTitle>
            {!editingDetails && perms.canEditCustomers && (
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onEditDetails}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
            {editingDetails && (
              <div className="flex gap-1.5">
                {(custDirty || propDirty || propRatesDirty) && (
                  <>
                    <Button variant="default" size="sm" className="h-8 px-3 text-xs" onClick={onSaveCustomer} disabled={custSaving}>
                      {custSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                    </Button>
                    <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs" onClick={() => { onCancelCustomer(); onCancelProperty(); }}>
                      Cancel
                    </Button>
                  </>
                )}
                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={onExitDetails}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {!editingDetails ? (
            /* --- Details View --- */
            <DetailsViewMode customer={customer} perms={perms} />
          ) : (
            /* --- Details Edit --- */
            <DetailsEditMode
              custForm={custForm}
              propForm={propForm}
              singleProp={singleProp}
              properties={properties}
              propRates={propRates}
              companies={companies}
              newCompanyCustom={newCompanyCustom}
              perms={perms}
              setCustField={setCustField}
              setPropField={setPropField}
              setPropRates={setPropRates}
              setPropRatesDirty={setPropRatesDirty}
              setNewCompanyCustom={setNewCompanyCustom}
              onTabChange={onTabChange}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function DetailsViewMode({ customer, perms }: { customer: Customer; perms: Permissions }) {
  return (
    <div className="space-y-4">
      {/* Billing — only for roles that can see rates */}
      {perms.canViewRates && (
        <Card className="shadow-sm py-4 gap-3">
          <CardHeader className="pb-0">
            <CardTitle className="text-sm">Billing</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              <div><span className="text-muted-foreground">Rate: </span>${customer.monthly_rate.toFixed(2)}/mo</div>
              <div><span className="text-muted-foreground">Terms: </span>{customer.payment_terms_days} days</div>
              <div><span className="text-muted-foreground">Frequency: </span><span className="capitalize">{customer.billing_frequency}</span></div>
              <div><span className="text-muted-foreground">Payment: </span>{customer.payment_method || "\u2014"}</div>
            </div>
            <div className="pt-1.5 border-t">
              <p className="text-xs text-muted-foreground mb-1">Billing Address</p>
              <p>{customer.billing_address ? `${customer.billing_address}, ${customer.billing_city}, ${customer.billing_state} ${customer.billing_zip}` : "Same as service address"}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Notes — always present */}
      <Card className="shadow-sm py-4 gap-3">
        <CardHeader className="pb-0">
          <CardTitle className="text-sm">Notes</CardTitle>
        </CardHeader>
        <CardContent>
          {customer.notes ? (
            <p className="text-sm whitespace-pre-wrap">{customer.notes}</p>
          ) : (
            <p className="text-sm text-muted-foreground">No notes</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface DetailsEditModeProps {
  custForm: Customer;
  propForm: Property | null;
  singleProp: Property | null;
  properties: Property[];
  propRates: Record<string, number>;
  companies: string[];
  newCompanyCustom: string;
  perms: Permissions;
  setCustField: (field: string, value: unknown) => void;
  setPropField: (field: string, value: unknown) => void;
  setPropRates: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  setPropRatesDirty: (dirty: boolean) => void;
  setNewCompanyCustom: (value: string) => void;
  onTabChange: (tab: ViewTab) => void;
}

function DetailsEditMode({
  custForm,
  propForm,
  singleProp,
  properties,
  propRates,
  companies,
  newCompanyCustom,
  perms,
  setCustField,
  setPropField,
  setPropRates,
  setPropRatesDirty,
  setNewCompanyCustom,
  onTabChange,
}: DetailsEditModeProps) {
  return (
    <div className="space-y-4">
      {/* Client tile — identity + address */}
      <Card className="bg-background">
        <CardContent className="pt-3 pb-3 space-y-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Client</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Type</Label>
              <Select value={custForm.customer_type} onValueChange={(v) => setCustField("customer_type", v)}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="residential">Residential</SelectItem>
                  <SelectItem value="commercial">Commercial</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Status</Label>
              <Select value={custForm.status ?? "active"} onValueChange={(v) => setCustField("status", v)}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="one_time">One-time</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">{custForm.customer_type === "commercial" ? "Name" : "First Name"}</Label>
              <Input value={custForm.first_name} onChange={(e) => setCustField("first_name", e.target.value)} className="h-9" />
            </div>
            {custForm.customer_type !== "commercial" ? (
              <div className="space-y-1.5">
                <Label className="text-xs">Last Name</Label>
                <Input value={custForm.last_name} onChange={(e) => setCustField("last_name", e.target.value)} className="h-9" />
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label className="text-xs">Company</Label>
                {companies.length > 0 ? (
                  <>
                    <Select
                      value={custForm.company_name === "__new__" ? "__new__" : (custForm.company_name || "__none__")}
                      onValueChange={(v) => {
                        if (v === "__none__") { setCustField("company_name", ""); setNewCompanyCustom(""); }
                        else if (v === "__new__") { setCustField("company_name", "__new__"); }
                        else { setCustField("company_name", v); setNewCompanyCustom(""); }
                      }}
                    >
                      <SelectTrigger className="h-9"><SelectValue placeholder="Select company..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">None</SelectItem>
                        {companies.map(name => (
                          <SelectItem key={name} value={name}>{name}</SelectItem>
                        ))}
                        <SelectItem value="__new__">+ New company...</SelectItem>
                      </SelectContent>
                    </Select>
                    {custForm.company_name === "__new__" && (
                      <Input
                        placeholder="New company name..."
                        value={newCompanyCustom}
                        onChange={(e) => setNewCompanyCustom(e.target.value)}
                        className="h-9"
                      />
                    )}
                  </>
                ) : (
                  <Input value={custForm.company_name ?? ""} onChange={(e) => setCustField("company_name", e.target.value)} className="h-9" />
                )}
              </div>
            )}
          </div>
          {/* Service address inline */}
          {singleProp && propForm ? (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs">Address</Label>
                <Input value={propForm.address} onChange={(e) => setPropField("address", e.target.value)} className="h-9" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">City</Label>
                  <Input value={propForm.city} onChange={(e) => setPropField("city", e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">State</Label>
                  <Input value={propForm.state} onChange={(e) => setPropField("state", e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Zip</Label>
                  <Input value={propForm.zip_code} onChange={(e) => setPropField("zip_code", e.target.value)} className="h-9" />
                </div>
              </div>
            </>
          ) : !singleProp && (
            <p className="text-xs text-muted-foreground">
              {properties.length} properties — <button type="button" className="text-primary hover:underline" onClick={() => onTabChange("wfs")}>edit on Water Features tab</button>
            </p>
          )}
        </CardContent>
      </Card>

      {/* Contact tile */}
      <Card className="bg-background">
        <CardContent className="pt-3 pb-3 space-y-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Contact</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Email</Label>
              <Input type="email" value={custForm.email ?? ""} onChange={(e) => setCustField("email", e.target.value)} className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Phone</Label>
              <Input value={custForm.phone ?? ""} onChange={(e) => setCustField("phone", e.target.value)} className="h-9" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Billing tile — only for roles that can see rates */}
      {perms.canViewRates && <Card className="bg-background">
        <CardContent className="pt-3 pb-3 space-y-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Billing</p>
          {properties.length <= 1 ? (
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Monthly Rate</Label>
                <Input type="number" step="0.01" value={propRates[properties[0]?.id] ?? ""} onChange={(e) => { setPropRates(prev => ({ ...prev, [properties[0]?.id]: parseFloat(e.target.value) || 0 })); setPropRatesDirty(true); }} className="h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Payment Terms (days)</Label>
                <Input type="number" value={custForm.payment_terms_days} onChange={(e) => setCustField("payment_terms_days", parseInt(e.target.value) || 30)} className="h-9" />
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Total Rate</Label>
                  <p className="h-9 flex items-center text-sm font-medium">${Object.values(propRates).reduce((s, r) => s + r, 0).toFixed(2)}/mo</p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Payment Terms (days)</Label>
                  <Input type="number" value={custForm.payment_terms_days} onChange={(e) => setCustField("payment_terms_days", parseInt(e.target.value) || 30)} className="h-9" />
                </div>
              </div>
              {properties.map(prop => (
                <div key={prop.id} className="flex items-center gap-2">
                  <Label className="text-xs flex-1 min-w-0 truncate">{prop.name || prop.address}</Label>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">$</span>
                    <Input type="number" step="0.01" value={propRates[prop.id] ?? ""} onChange={(e) => { setPropRates(prev => ({ ...prev, [prop.id]: parseFloat(e.target.value) || 0 })); setPropRatesDirty(true); }} className="h-8 w-28 text-sm text-right" />
                    <span className="text-xs text-muted-foreground">/mo</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Billing Frequency</Label>
              <Select value={custForm.billing_frequency} onValueChange={(v) => setCustField("billing_frequency", v)}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Monthly</SelectItem>
                  <SelectItem value="quarterly">Quarterly</SelectItem>
                  <SelectItem value="annually">Annually</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Payment Method</Label>
              <Input value={custForm.payment_method ?? ""} onChange={(e) => setCustField("payment_method", e.target.value)} placeholder="check, cc, ach..." className="h-9" />
            </div>
          </div>
          {/* Billing address with "same as" toggle */}
          {singleProp && propForm && (() => {
            const sameAddr = custForm.billing_address === propForm.address
              && custForm.billing_city === propForm.city
              && custForm.billing_state === propForm.state
              && custForm.billing_zip === propForm.zip_code;
            const isSame = !custForm.billing_address || sameAddr;
            return (
              <>
                <div className="flex items-center gap-2 pt-1">
                  <Switch checked={isSame} onCheckedChange={(v) => {
                    if (v) {
                      setCustField("billing_address", propForm.address);
                      setCustField("billing_city", propForm.city);
                      setCustField("billing_state", propForm.state);
                      setCustField("billing_zip", propForm.zip_code);
                    }
                  }} />
                  <Label className="text-xs">Same as service address</Label>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Billing Address</Label>
                  <Input value={isSame ? propForm.address : (custForm.billing_address ?? "")} onChange={(e) => setCustField("billing_address", e.target.value)} className="h-9" disabled={isSame} />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs">City</Label>
                    <Input value={isSame ? propForm.city : (custForm.billing_city ?? "")} onChange={(e) => setCustField("billing_city", e.target.value)} className="h-9" disabled={isSame} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">State</Label>
                    <Input value={isSame ? propForm.state : (custForm.billing_state ?? "")} onChange={(e) => setCustField("billing_state", e.target.value)} className="h-9" disabled={isSame} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Zip</Label>
                    <Input value={isSame ? propForm.zip_code : (custForm.billing_zip ?? "")} onChange={(e) => setCustField("billing_zip", e.target.value)} className="h-9" disabled={isSame} />
                  </div>
                </div>
              </>
            );
          })()}
          {/* Fallback: no property, show billing address fields directly */}
          {!singleProp && (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs">Billing Address</Label>
                <Input value={custForm.billing_address ?? ""} onChange={(e) => setCustField("billing_address", e.target.value)} className="h-9" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">City</Label>
                  <Input value={custForm.billing_city ?? ""} onChange={(e) => setCustField("billing_city", e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">State</Label>
                  <Input value={custForm.billing_state ?? ""} onChange={(e) => setCustField("billing_state", e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Zip</Label>
                  <Input value={custForm.billing_zip ?? ""} onChange={(e) => setCustField("billing_zip", e.target.value)} className="h-9" />
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>}

      {/* Service tile — schedule + access details */}
      <Card className="bg-background">
        <CardContent className="pt-3 pb-3 space-y-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Service</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Frequency</Label>
              <Select value={custForm.service_frequency ?? "weekly"} onValueChange={(v) => setCustField("service_frequency", v)}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="biweekly">Biweekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                  <SelectItem value="on_call">On Call</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Service Days</Label>
              <div className="flex flex-wrap gap-1">
                {["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"].map((day) => {
                  const days = (custForm.preferred_day ?? "").split(",").filter(Boolean);
                  const active = days.includes(day);
                  return (
                    <Button key={day} type="button" variant={active ? "default" : "outline"} size="sm" className="h-7 px-2 text-xs"
                      onClick={() => { const next = active ? days.filter(d => d !== day) : [...days, day]; setCustField("preferred_day", next.length ? next.join(",") : null); }}>
                      {day.slice(0, 3).charAt(0).toUpperCase() + day.slice(1, 3)}
                    </Button>
                  );
                })}
              </div>
            </div>
          </div>
          {/* Access details from property */}
          {singleProp && propForm ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Gate Code</Label>
                  <Input value={propForm.gate_code ?? ""} onChange={(e) => setPropField("gate_code", e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Access Instructions</Label>
                  <Input value={propForm.access_instructions ?? ""} onChange={(e) => setPropField("access_instructions", e.target.value)} className="h-9" />
                </div>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                <div className="flex items-center gap-2">
                  <Switch checked={propForm.dog_on_property} onCheckedChange={(v) => setPropField("dog_on_property", v)} />
                  <Label className="text-xs">Dog on Property</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={propForm.is_locked_to_day} onCheckedChange={(v) => setPropField("is_locked_to_day", v)} />
                  <Label className="text-xs">Locked to Day</Label>
                </div>
              </div>
            </>
          ) : !singleProp && (
            <p className="text-xs text-muted-foreground">
              Site access — <button type="button" className="text-primary hover:underline" onClick={() => onTabChange("wfs")}>edit per-property on Water Features tab</button>
            </p>
          )}
          <div className="space-y-1.5">
            <Label className="text-xs">Notes</Label>
            <Textarea value={custForm.notes ?? ""} onChange={(e) => setCustField("notes", e.target.value)} rows={2} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
