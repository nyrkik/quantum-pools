"use client";

import { useState, useEffect, useCallback } from "react";
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
import { Plus, Search, Building2, Home } from "lucide-react";

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
}

function customerDisplayName(c: Customer) {
  if (c.customer_type === "commercial") return c.first_name;
  return `${c.first_name} ${c.last_name}`.trim();
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newType, setNewType] = useState("residential");

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
      toast.error("Failed to load customers");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    fetchCustomers();
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
        ? (form.get("company_name") as string) || undefined
        : undefined,
      customer_type: newType,
      email: (form.get("email") as string) || undefined,
      phone: (form.get("phone") as string) || undefined,
      monthly_rate: parseFloat(form.get("monthly_rate") as string) || 0,
    };
    try {
      await api.post("/v1/customers", body);
      toast.success("Customer created");
      setDialogOpen(false);
      setNewType("residential");
      fetchCustomers();
    } catch {
      toast.error("Failed to create customer");
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Customers</h1>
          <p className="text-muted-foreground text-sm">{total} total</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              <span className="hidden sm:inline">Add Customer</span>
              <span className="sm:hidden">Add</span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New Customer</DialogTitle>
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
                    <Label htmlFor="company_name">Management Company</Label>
                    <Input
                      id="company_name"
                      name="company_name"
                      placeholder="e.g. Bright PM"
                    />
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
                Create Customer
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search customers..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
      </div>

      <TooltipProvider>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="hidden md:table-cell">Property</TableHead>
                <TableHead className="hidden lg:table-cell">Mgmt Co</TableHead>
                <TableHead className="hidden sm:table-cell">Contact</TableHead>
                <TableHead>Rate</TableHead>
                <TableHead className="hidden sm:table-cell">Balance</TableHead>
                <TableHead>Status</TableHead>
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
                    No customers found
                  </TableCell>
                </TableRow>
              ) : (
                customers.map((c) => (
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
                      {c.first_property_address || "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground hidden lg:table-cell">
                      {c.company_name || "—"}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <div className="text-sm">{c.email}</div>
                      <div className="text-xs text-muted-foreground">
                        {c.phone}
                      </div>
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
