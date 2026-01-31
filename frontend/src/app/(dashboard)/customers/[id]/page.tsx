"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { ArrowLeft, Plus, MapPin } from "lucide-react";

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
  billing_address: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_zip: string | null;
  notes: string | null;
  is_active: boolean;
  property_count: number;
  created_at: string;
}

interface Property {
  id: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  pool_type: string | null;
  pool_gallons: number | null;
  has_spa: boolean;
  is_active: boolean;
}

export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [addPropOpen, setAddPropOpen] = useState(false);

  const fetch = useCallback(async () => {
    try {
      const [c, p] = await Promise.all([
        api.get<Customer>(`/v1/customers/${id}`),
        api.get<{ items: Property[] }>(`/v1/properties?customer_id=${id}`),
      ]);
      setCustomer(c);
      setProperties(p.items);
    } catch {
      toast.error("Failed to load customer");
    }
  }, [id]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const handleAddProperty = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/v1/properties", {
        customer_id: id,
        address: form.get("address"),
        city: form.get("city"),
        state: form.get("state"),
        zip_code: form.get("zip_code"),
        pool_type: form.get("pool_type") || undefined,
        pool_gallons: parseInt(form.get("pool_gallons") as string) || undefined,
        has_spa: form.get("has_spa") === "on",
      });
      toast.success("Property added");
      setAddPropOpen(false);
      fetch();
    } catch {
      toast.error("Failed to add property");
    }
  };

  if (!customer) {
    return (
      <div className="flex items-center justify-center py-20">Loading...</div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {customer.first_name} {customer.last_name}
          </h1>
          {customer.company_name && (
            <p className="text-muted-foreground">{customer.company_name}</p>
          )}
        </div>
        <Badge variant={customer.is_active ? "default" : "secondary"}>
          {customer.is_active ? "Active" : "Inactive"}
        </Badge>
      </div>

      <Tabs defaultValue="info">
        <TabsList>
          <TabsTrigger value="info">Info</TabsTrigger>
          <TabsTrigger value="properties">
            Properties ({properties.length})
          </TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
        </TabsList>

        <TabsContent value="info" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Contact</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Email: </span>
                  {customer.email || "—"}
                </div>
                <div>
                  <span className="text-muted-foreground">Phone: </span>
                  {customer.phone || "—"}
                </div>
                <div>
                  <span className="text-muted-foreground">Type: </span>
                  {customer.customer_type}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Billing</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Monthly Rate: </span>$
                  {customer.monthly_rate.toFixed(2)}
                </div>
                <div>
                  <span className="text-muted-foreground">Balance: </span>
                  <span
                    className={
                      customer.balance > 0 ? "text-red-600 font-medium" : ""
                    }
                  >
                    ${customer.balance.toFixed(2)}
                  </span>
                </div>
                {customer.billing_address && (
                  <div>
                    <span className="text-muted-foreground">Address: </span>
                    {customer.billing_address}, {customer.billing_city},{" "}
                    {customer.billing_state} {customer.billing_zip}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
          {customer.notes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Notes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap">{customer.notes}</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="properties" className="space-y-4">
          <div className="flex justify-end">
            <Dialog open={addPropOpen} onOpenChange={setAddPropOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="mr-2 h-4 w-4" />
                  Add Property
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Add Property</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleAddProperty} className="space-y-4">
                  <div className="space-y-2">
                    <Label>Address</Label>
                    <Input name="address" required />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="space-y-2">
                      <Label>City</Label>
                      <Input name="city" required />
                    </div>
                    <div className="space-y-2">
                      <Label>State</Label>
                      <Input name="state" required />
                    </div>
                    <div className="space-y-2">
                      <Label>Zip</Label>
                      <Input name="zip_code" required />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>Pool type</Label>
                      <Input name="pool_type" placeholder="gunite, vinyl..." />
                    </div>
                    <div className="space-y-2">
                      <Label>Gallons</Label>
                      <Input
                        name="pool_gallons"
                        type="number"
                        placeholder="15000"
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="checkbox" name="has_spa" id="has_spa" />
                    <Label htmlFor="has_spa">Has spa</Label>
                  </div>
                  <Button type="submit" className="w-full">
                    Add Property
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
          {properties.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No properties yet
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {properties.map((p) => (
                <Card key={p.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <MapPin className="h-4 w-4" />
                      {p.address}
                    </CardTitle>
                    <CardDescription>
                      {p.city}, {p.state} {p.zip_code}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="text-sm space-y-1">
                    {p.pool_type && <div>Pool: {p.pool_type}</div>}
                    {p.pool_gallons && (
                      <div>{p.pool_gallons.toLocaleString()} gallons</div>
                    )}
                    {p.has_spa && <Badge variant="outline">Spa</Badge>}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="invoices">
          <p className="text-center text-muted-foreground py-8">
            Invoicing available in Phase 3
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
