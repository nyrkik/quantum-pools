"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { toast } from "sonner";
import { Plus } from "lucide-react";
import type { CustomerListItem } from "./client-section";

interface CreateClientDialogProps {
  refreshKey: number;
  onCreated: () => void;
}

export function CreateClientDialog({ refreshKey, onCreated }: CreateClientDialogProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newType, setNewType] = useState("residential");
  const [newCompany, setNewCompany] = useState("");
  const [newCompanyCustom, setNewCompanyCustom] = useState("");
  const [existingCompanies, setExistingCompanies] = useState<string[]>([]);

  useEffect(() => {
    api.get<{ items: CustomerListItem[] }>("/v1/customers?limit=200&sort_by=name")
      .then(data => {
        const names = new Set<string>();
        data.items.forEach(c => { if (c.company_name) names.add(c.company_name); });
        setExistingCompanies([...names].sort());
      }).catch(() => {});
  }, [refreshKey]);

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
      onCreated();
    } catch {
      toast.error("Failed to create client");
    }
  };

  return (
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
  );
}
