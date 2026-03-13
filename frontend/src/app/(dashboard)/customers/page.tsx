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

interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  company_name: string | null;
  customer_type: string;
  email: string | null;
  phone: string | null;
  monthly_rate: number;
  balance: number;
  is_active: boolean;
  property_count: number;
  first_property_address: string | null;
  first_property_pool_type: string | null;
  bow_summary: string | null;
}

type SortKey = "name" | "property" | "company" | "pool" | "rate" | "balance" | "status";
type SortDir = "asc" | "desc";

function customerDisplayName(c: Customer) {
  if (c.customer_type === "commercial") return c.first_name;
  return `${c.first_name} ${c.last_name}`.trim();
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3.5 w-3.5 ml-1 text-muted-foreground/40" />;
  return dir === "asc"
    ? <ArrowUp className="h-3.5 w-3.5 ml-1" />
    : <ArrowDown className="h-3.5 w-3.5 ml-1" />;
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newType, setNewType] = useState("residential");
  const [newCompany, setNewCompany] = useState("");
  const [newCompanyCustom, setNewCompanyCustom] = useState("");
  const [typeFilter, setTypeFilter] = useState<"commercial" | "residential" | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

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
  }, [search]);

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
    };
    try {
      await api.post("/v1/customers", body);
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

  const commercialCount = customers.filter(c => c.customer_type === "commercial").length;
  const residentialCount = customers.filter(c => c.customer_type === "residential").length;
  const hasCommercial = commercialCount > 0;
  const hasResidential = residentialCount > 0;

  const sorted = useMemo(() => {
    const filtered = typeFilter ? customers.filter(c => c.customer_type === typeFilter) : customers;
    return [...filtered].sort((a, b) => {
      // Commercial always first, then sort within groups
      const typeOrder = (a.customer_type === "commercial" ? 0 : 1) - (b.customer_type === "commercial" ? 0 : 1);
      if (typeOrder !== 0) return typeOrder;

      const dir = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "name":
          return dir * customerDisplayName(a).localeCompare(customerDisplayName(b));
        case "property":
          return dir * (a.first_property_address ?? "").localeCompare(b.first_property_address ?? "");
        case "company":
          return dir * (a.company_name ?? "").localeCompare(b.company_name ?? "");
        case "pool":
          return dir * (a.bow_summary ?? a.first_property_pool_type ?? "").localeCompare(b.bow_summary ?? b.first_property_pool_type ?? "");
        case "rate":
          return dir * (a.monthly_rate - b.monthly_rate);
        case "balance":
          return dir * (a.balance - b.balance);
        case "status": {
          const av = a.is_active ? 0 : 1;
          const bv = b.is_active ? 0 : 1;
          return dir * (av - bv);
        }
        default:
          return 0;
      }
    });
  }, [customers, typeFilter, sortKey, sortDir]);

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
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              <span className="hidden sm:inline">Add Client</span>
              <span className="sm:hidden">Add</span>
            </Button>
          </DialogTrigger>
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

      {hasCommercial && hasResidential && (
        <div className="flex items-center gap-2">
          <Button
            variant={typeFilter === null ? "default" : "outline"}
            size="sm"
            onClick={() => setTypeFilter(null)}
          >
            All
          </Button>
          <Button
            variant={typeFilter === "commercial" ? "default" : "outline"}
            size="sm"
            onClick={() => setTypeFilter("commercial")}
          >
            <Building2 className="h-3.5 w-3.5 mr-1.5" />
            Commercial ({commercialCount})
          </Button>
          <Button
            variant={typeFilter === "residential" ? "default" : "outline"}
            size="sm"
            onClick={() => setTypeFilter("residential")}
          >
            <Home className="h-3.5 w-3.5 mr-1.5" />
            Residential ({residentialCount})
          </Button>
        </div>
      )}

      <TooltipProvider>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead className={thClass} onClick={() => toggleSort("name")}>
                  <div className="flex items-center">Name<SortIcon active={sortKey === "name"} dir={sortDir} /></div>
                </TableHead>
                <TableHead className={`hidden md:table-cell ${thClass}`} onClick={() => toggleSort("property")}>
                  <div className="flex items-center">Property<SortIcon active={sortKey === "property"} dir={sortDir} /></div>
                </TableHead>
                <TableHead className={`hidden lg:table-cell ${thClass}`} onClick={() => toggleSort("company")}>
                  <div className="flex items-center">Mgmt Company<SortIcon active={sortKey === "company"} dir={sortDir} /></div>
                </TableHead>
                <TableHead className={`hidden sm:table-cell ${thClass}`} onClick={() => toggleSort("pool")}>
                  <div className="flex items-center">Pool Type<SortIcon active={sortKey === "pool"} dir={sortDir} /></div>
                </TableHead>
                <TableHead className={thClass} onClick={() => toggleSort("rate")}>
                  <div className="flex items-center">Rate<SortIcon active={sortKey === "rate"} dir={sortDir} /></div>
                </TableHead>
                <TableHead className={`hidden sm:table-cell ${thClass}`} onClick={() => toggleSort("balance")}>
                  <div className="flex items-center">Balance<SortIcon active={sortKey === "balance"} dir={sortDir} /></div>
                </TableHead>
                <TableHead className={thClass} onClick={() => toggleSort("status")}>
                  <div className="flex items-center">Status<SortIcon active={sortKey === "status"} dir={sortDir} /></div>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8">
                    Loading...
                  </TableCell>
                </TableRow>
              ) : customers.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="text-center py-8 text-muted-foreground"
                  >
                    No clients found
                  </TableCell>
                </TableRow>
              ) : (
                sorted.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="pr-0">
                      <Tooltip>
                        <TooltipTrigger>
                          {c.customer_type === "commercial" ? (
                            <Building2 className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <Home className="h-4 w-4 text-muted-foreground" />
                          )}
                        </TooltipTrigger>
                        <TooltipContent>{c.customer_type}</TooltipContent>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/customers/${c.id}`}
                        className="font-medium hover:underline"
                      >
                        {customerDisplayName(c)}
                      </Link>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground hidden md:table-cell">
                      {c.first_property_address || "\u2014"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground hidden lg:table-cell">
                      {c.company_name || "\u2014"}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-sm text-muted-foreground capitalize">
                      {c.bow_summary || c.first_property_pool_type || "\u2014"}
                    </TableCell>
                    <TableCell>${c.monthly_rate.toFixed(2)}</TableCell>
                    <TableCell
                      className={`hidden sm:table-cell ${c.balance > 0 ? "text-red-600 font-medium" : ""}`}
                    >
                      ${c.balance.toFixed(2)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={c.is_active ? "default" : "secondary"}>
                        {c.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </TooltipProvider>
    </div>
  );
}
