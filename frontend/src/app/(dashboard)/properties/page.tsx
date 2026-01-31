"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { MapPin } from "lucide-react";

interface Property {
  id: string;
  customer_id: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  pool_type: string | null;
  pool_gallons: number | null;
  has_spa: boolean;
  has_water_feature: boolean;
  estimated_service_minutes: number;
  is_active: boolean;
}

export default function PropertiesPage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<{ items: Property[]; total: number }>(
          "/v1/properties"
        );
        setProperties(data.items);
        setTotal(data.total);
      } catch {
        toast.error("Failed to load properties");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Properties</h1>
        <p className="text-muted-foreground">{total} service locations</p>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Address</TableHead>
              <TableHead>Pool</TableHead>
              <TableHead>Gallons</TableHead>
              <TableHead>Features</TableHead>
              <TableHead>Service Time</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : properties.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="text-center py-8 text-muted-foreground"
                >
                  No properties. Add them from a customer&apos;s detail page.
                </TableCell>
              </TableRow>
            ) : (
              properties.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{p.address}</div>
                        <div className="text-xs text-muted-foreground">
                          {p.city}, {p.state} {p.zip_code}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{p.pool_type || "—"}</TableCell>
                  <TableCell>
                    {p.pool_gallons
                      ? p.pool_gallons.toLocaleString()
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {p.has_spa && <Badge variant="outline">Spa</Badge>}
                      {p.has_water_feature && (
                        <Badge variant="outline">Water Feature</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{p.estimated_service_minutes} min</TableCell>
                  <TableCell>
                    <Badge variant={p.is_active ? "default" : "secondary"}>
                      {p.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
