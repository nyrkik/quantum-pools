"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { toast } from "sonner";
import { Plus, Search, Building2, Home, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { usePermissions } from "@/lib/permissions";
import { Overlay, OverlayContent, OverlayBody } from "@/components/ui/overlay";
import { CustomerDetailContent } from "@/components/customers/customer-detail-content";

interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  display_name: string | null;
  company_name: string | null;
  customer_type: string;
  email: string | null;
  phone: string | null;
  monthly_rate: number;
  balance: number;
  status: string;
  is_active: boolean;
  property_count: number;
  first_property_address: string | null;
  first_property_pool_type: string | null;
  wf_summary: string | null;
  first_property_id: string | null;
}

type SortKey = "name" | "property" | "company" | "pool" | "rate" | "balance" | "status";
type SortDir = "asc" | "desc";

function customerDisplayName(c: Customer) {
  return c.display_name || c.first_name;
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3.5 w-3.5 ml-1 text-muted-foreground/40" />;
  return dir === "asc"
    ? <ArrowUp className="h-3.5 w-3.5 ml-1" />
    : <ArrowDown className="h-3.5 w-3.5 ml-1" />;
}

function ClientTable({
  title,
  icon: Icon,
  items,
  perms,
  sortKey,
  sortDir,
  toggleSort,
  thClass,
  techAssignments,
  onSelectCustomer,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  items: Customer[];
  perms: ReturnType<typeof usePermissions>;
  sortKey: SortKey;
  sortDir: SortDir;
  toggleSort: (key: SortKey) => void;
  thClass: string;
  techAssignments: Record<string, Array<{ tech_name: string; color: string }>>;
  onSelectCustomer: (id: string) => void;
}) {
  const colSpan = 6 + (perms.canViewRates ? 1 : 0) + (perms.canViewBalance ? 1 : 0);
  return (
    <div className="rounded-lg border shadow-sm overflow-hidden">
      {/* Section header */}
      <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2.5">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{title}</h2>
        <span className="text-[11px] text-muted-foreground/50">({items.length})</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="bg-slate-100 dark:bg-slate-800">
            <TableHead className={`text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("name")}>
              <div className="flex items-center">Name<SortIcon active={sortKey === "name"} dir={sortDir} /></div>
            </TableHead>
            <TableHead className={`hidden md:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("property")}>
              <div className="flex items-center">Property<SortIcon active={sortKey === "property"} dir={sortDir} /></div>
            </TableHead>
            <TableHead className={`hidden lg:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("company")}>
              <div className="flex items-center">Mgmt Company<SortIcon active={sortKey === "company"} dir={sortDir} /></div>
            </TableHead>
            <TableHead className={`hidden sm:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("pool")}>
              <div className="flex items-center">Pool Type<SortIcon active={sortKey === "pool"} dir={sortDir} /></div>
            </TableHead>
            <TableHead className={`hidden lg:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`}>
              Tech
            </TableHead>
            {perms.canViewRates && (
              <TableHead className={`text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("rate")}>
                <div className="flex items-center">Rate<SortIcon active={sortKey === "rate"} dir={sortDir} /></div>
              </TableHead>
            )}
            {perms.canViewBalance && (
              <TableHead className={`hidden sm:table-cell text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("balance")}>
                <div className="flex items-center">Balance<SortIcon active={sortKey === "balance"} dir={sortDir} /></div>
              </TableHead>
            )}
            <TableHead className={`text-xs font-medium uppercase tracking-wide ${thClass}`} onClick={() => toggleSort("status")}>
              <div className="flex items-center">Status<SortIcon active={sortKey === "status"} dir={sortDir} /></div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={colSpan} className="text-center py-6 text-muted-foreground text-sm">
                No {title.toLowerCase()} clients
              </TableCell>
            </TableRow>
          ) : (
            items.map((c, i) => (
              <TableRow key={c.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                <TableCell>
                  <button onClick={() => onSelectCustomer(c.id)} className="font-medium hover:underline text-left">
                    {customerDisplayName(c)}
                  </button>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground hidden md:table-cell">
                  {c.first_property_address || "\u2014"}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground hidden lg:table-cell">
                  {c.company_name || "\u2014"}
                </TableCell>
                <TableCell className="hidden sm:table-cell text-sm text-muted-foreground capitalize">
                  {c.wf_summary || c.first_property_pool_type || "\u2014"}
                </TableCell>
                <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                  {(() => {
                    const tech = c.first_property_id ? techAssignments[c.first_property_id]?.[0] : null;
                    return tech ? (
                      <div className="flex items-center gap-1.5">
                        <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: tech.color }} />
                        <span className="truncate">{tech.tech_name.split(" ")[0]}</span>
                      </div>
                    ) : "\u2014";
                  })()}
                </TableCell>
                {perms.canViewRates && (
                  <TableCell>${c.monthly_rate.toFixed(2)}</TableCell>
                )}
                {perms.canViewBalance && (
                  <TableCell className={`hidden sm:table-cell ${c.balance > 0 ? "text-red-600 font-medium" : ""}`}>
                    ${c.balance.toFixed(2)}
                  </TableCell>
                )}
                <TableCell>
                  <Badge variant={c.status === "active" ? "default" : c.status === "service_call" ? "outline" : c.status === "lead" || c.status === "pending" ? "outline" : "secondary"}
                    className={c.status === "service_call" ? "border-blue-400 text-blue-600" : c.status === "lead" || c.status === "pending" ? "border-amber-400 text-amber-600" : c.status === "one_time" ? "border-blue-400 text-blue-600" : ""}>
                    {c.status === "service_call" ? "Service Call" : c.status === "one_time" ? "One-time" : c.status.charAt(0).toUpperCase() + c.status.slice(1)}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}

export default function CustomersPage() {
  const perms = usePermissions();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newType, setNewType] = useState("residential");
  const [newCompany, setNewCompany] = useState("");
  const [newCompanyCustom, setNewCompanyCustom] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set(["active"]));
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [techAssignments, setTechAssignments] = useState<Record<string, Array<{ tech_name: string; color: string }>>>({});
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const fetchCustomers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      statusFilter.forEach(s => params.append("status", s));
      const data = await api.get<{ items: Customer[]; total: number }>(
        `/v1/customers?${params}`
      );
      setCustomers(data.items);
      setTotal(data.total);
    } catch {
      toast.error("Failed to load clients");
    } finally {
      setLoading(false);
    }
  }, [search, [...statusFilter].sort().join(",")]);

  useEffect(() => {
    api.get<Record<string, Array<{ tech_name: string; color: string }>>>("/v1/routes/tech-assignments")
      .then(setTechAssignments).catch(() => {});
  }, []);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  useEffect(() => {
    const handleFocus = () => fetchCustomers();
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [fetchCustomers]);

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const isCommercial = newType === "commercial";
    const body = {
      first_name: isCommercial
        ? (form.get("property_name") as string)
        : (form.get("first_name") as string),
      last_name: isCommercial ? "" : (form.get("last_name") as string),
      company_name: isCommercial
        ? (newCompany === "__new__" ? newCompanyCustom : newCompany) || undefined
        : undefined,
      customer_type: newType,
      email: (form.get("email") as string) || undefined,
      phone: (form.get("phone") as string) || undefined,
      monthly_rate: parseFloat(form.get("monthly_rate") as string) || 0,
      address: form.get("address") as string,
      city: form.get("city") as string,
      state: form.get("state") as string,
      zip_code: form.get("zip_code") as string,
      water_type: "pool",
      pool_type: isCommercial ? "commercial" : "residential",
    };
    try {
      await api.post("/v1/customers/with-property", body);
      toast.success("Client created");
      setDialogOpen(false);
      setNewType("residential");
      setNewCompany("");
      setNewCompanyCustom("");
      fetchCustomers();
    } catch {
      toast.error("Failed to create client");
    }
  };

  const sortFn = useCallback((a: Customer, b: Customer) => {
    const dir = sortDir === "asc" ? 1 : -1;
    switch (sortKey) {
      case "name":
        return dir * customerDisplayName(a).localeCompare(customerDisplayName(b));
      case "property":
        return dir * (a.first_property_address ?? "").localeCompare(b.first_property_address ?? "");
      case "company":
        return dir * (a.company_name ?? "").localeCompare(b.company_name ?? "");
      case "pool":
        return dir * (a.wf_summary ?? a.first_property_pool_type ?? "").localeCompare(b.wf_summary ?? b.first_property_pool_type ?? "");
      case "rate":
        return dir * (a.monthly_rate - b.monthly_rate);
      case "balance":
        return dir * (a.balance - b.balance);
      case "status":
        return dir * (a.status ?? "").localeCompare(b.status ?? "");
      default:
        return 0;
    }
  }, [sortKey, sortDir]);

  const commercialList = useMemo(() =>
    customers.filter(c => c.customer_type === "commercial").sort(sortFn),
    [customers, sortFn]
  );
  const residentialList = useMemo(() =>
    customers.filter(c => c.customer_type === "residential").sort(sortFn),
    [customers, sortFn]
  );

  const existingCompanies = useMemo(() => {
    const names = new Set<string>();
    customers.forEach(c => { if (c.company_name) names.add(c.company_name); });
    return [...names].sort((a, b) => a.localeCompare(b));
  }, [customers]);

  const thClass = "cursor-pointer select-none";

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Clients</h1>
          <p className="text-muted-foreground text-sm">{total} total</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          {perms.canCreateCustomers && (
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                <span className="hidden sm:inline">Add Client</span>
                <span className="sm:hidden">Add</span>
              </Button>
            </DialogTrigger>
          )}
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New Client</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-2">
                <Label>Type</Label>
                <Select value={newType} onValueChange={setNewType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="residential">Residential</SelectItem>
                    <SelectItem value="commercial">Commercial</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {newType === "commercial" ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="property_name">Property Name</Label>
                    <Input
                      id="property_name"
                      name="property_name"
                      placeholder="e.g. Parkwood Square"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Mgmt Company</Label>
                    {existingCompanies.length > 0 ? (
                      <>
                        <Select value={newCompany} onValueChange={setNewCompany}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select or add new..." />
                          </SelectTrigger>
                          <SelectContent>
                            {existingCompanies.map(name => (
                              <SelectItem key={name} value={name}>{name}</SelectItem>
                            ))}
                            <SelectItem value="__new__">+ New company...</SelectItem>
                          </SelectContent>
                        </Select>
                        {newCompany === "__new__" && (
                          <Input
                            placeholder="New company name..."
                            value={newCompanyCustom}
                            onChange={(e) => setNewCompanyCustom(e.target.value)}
                          />
                        )}
                      </>
                    ) : (
                      <Input
                        placeholder="e.g. Bright PM"
                        value={newCompany}
                        onChange={(e) => setNewCompany(e.target.value)}
                      />
                    )}
                  </div>
                </>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="first_name">First Name</Label>
                    <Input id="first_name" name="first_name" required />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="last_name">Last Name</Label>
                    <Input id="last_name" name="last_name" required />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" name="email" type="email" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone</Label>
                  <Input id="phone" name="phone" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="address">Service Address</Label>
                <Input id="address" name="address" placeholder="123 Main St" required />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-2">
                  <Label htmlFor="city">City</Label>
                  <Input id="city" name="city" required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="state">State</Label>
                  <Input id="state" name="state" defaultValue="CA" required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="zip_code">Zip</Label>
                  <Input id="zip_code" name="zip_code" required />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="monthly_rate">Monthly Rate</Label>
                <Input
                  id="monthly_rate"
                  name="monthly_rate"
                  type="number"
                  step="0.01"
                  defaultValue="0"
                />
              </div>
              <Button type="submit" className="w-full">
                Create Client
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search clients..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5">
          {[
            { value: "commercial", label: "Commercial", icon: Building2 },
            { value: "residential", label: "Residential", icon: Home },
          ].map((t) => (
            <Button
              key={t.value}
              variant={typeFilter === t.value ? "default" : "outline"}
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={() => setTypeFilter(prev => prev === t.value ? null : t.value)}
            >
              <t.icon className="h-3.5 w-3.5 mr-1" />{t.label}
            </Button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1.5">
          {[
            { value: "active", label: "Active" },
            { value: "service_call", label: "Service Call" },
            { value: "lead", label: "Lead" },
            { value: "inactive", label: "Inactive" },
          ].map((s) => (
            <Button
              key={s.value}
              variant={statusFilter.has(s.value) ? "default" : "outline"}
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={() => setStatusFilter(prev => {
                const next = new Set(prev);
                if (next.has(s.value)) next.delete(s.value);
                else next.add(s.value);
                return next;
              })}
            >
              {s.label}
            </Button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-8 text-muted-foreground">Loading...</div>
      ) : (
        <TooltipProvider>
          <div className="space-y-6">
            {(typeFilter === null || typeFilter === "commercial") && (
              <ClientTable
                title="Commercial"
                icon={Building2}
                items={commercialList}
                perms={perms}
                sortKey={sortKey}
                sortDir={sortDir}
                toggleSort={toggleSort}
                thClass={thClass}
                techAssignments={techAssignments}
                onSelectCustomer={setSelectedCustomerId}
              />
            )}
            {(typeFilter === null || typeFilter === "residential") && (
              <ClientTable
                title="Residential"
                icon={Home}
                items={residentialList}
                perms={perms}
                sortKey={sortKey}
                sortDir={sortDir}
                toggleSort={toggleSort}
                thClass={thClass}
                techAssignments={techAssignments}
                onSelectCustomer={setSelectedCustomerId}
              />
            )}
          </div>
        </TooltipProvider>
      )}

      {/* Customer detail overlay */}
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
    </div>
  );
}
