"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import Link from "next/link";
import { PageLayout } from "@/components/layout/page-layout";

interface WaterFeatureSummary {
  id: string;
  name: string | null;
  water_type: string;
  pool_type: string | null;
  pool_gallons: number | null;
  pool_sqft: number | null;
  estimated_service_minutes: number;
  monthly_rate: number | null;
}

interface Property {
  id: string;
  customer_id: string;
  name: string | null;
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
  water_features: WaterFeatureSummary[];
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
    <PageLayout
      title="Properties"
      subtitle={`${total} service locations`}
    >
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Address</TableHead>
              <TableHead>Pool</TableHead>
              <TableHead>Gallons</TableHead>
              <TableHead>Water Features</TableHead>
              <TableHead>Service Time</TableHead>
              <TableHead>Status</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : properties.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-center py-8 text-muted-foreground"
                >
                  No properties. Add them from a client&apos;s detail page.
                </TableCell>
              </TableRow>
            ) : (
              properties.map((p, i) => (
                <TableRow key={p.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{p.name || p.address}</div>
                        <div className="text-xs text-muted-foreground">
                          {p.name ? p.address + ", " : ""}{p.city}, {p.state} {p.zip_code}
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
                    <div className="flex gap-1 flex-wrap">
                      {(p.water_features?.length > 0) ? (
                        p.water_features.map((wf) => (
                          <Badge key={wf.id} variant="outline" className="capitalize text-xs">
                            {wf.name || wf.water_type.replace("_", " ")}
                          </Badge>
                        ))
                      ) : (
                        <>
                          {p.has_spa && <Badge variant="outline">Spa</Badge>}
                          {p.has_water_feature && <Badge variant="outline">Water Feature</Badge>}
                        </>
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
    </PageLayout>
  );
}
