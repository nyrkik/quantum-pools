"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Droplets } from "lucide-react";
import type { Customer, Property } from "./customer-types";

interface CustomerServiceTabProps {
  customer: Customer;
  properties: Property[];
}

export function CustomerServiceTab({ customer, properties }: CustomerServiceTabProps) {
  const allWfs = properties.flatMap(p => p.water_features || []);

  return (
    <div className="space-y-4">
      {/* Service schedule */}
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Today&apos;s Service</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
            <div><span className="text-muted-foreground">Frequency: </span><span className="capitalize">{customer.service_frequency || "weekly"}</span></div>
            <div>
              <span className="text-muted-foreground">Days: </span>
              {customer.preferred_day
                ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ")
                : "Any"}
            </div>
          </div>
          {customer.notes && (
            <div className="text-sm pt-1.5 border-t">
              <span className="text-muted-foreground">Notes: </span>{customer.notes}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pool info for each WF — what the tech needs to know */}
      {allWfs.map((wf) => (
        <Card key={wf.id} className="shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Droplets className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-sm capitalize">{wf.name || wf.water_type.replace("_", " ")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-xs text-muted-foreground">Gallons</p>
                <p className="font-medium">{wf.pool_gallons ? wf.pool_gallons.toLocaleString() : "\u2014"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Service Time</p>
                <p className="font-medium">{wf.estimated_service_minutes} min</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Type</p>
                <p className="font-medium capitalize">{wf.pool_type || "\u2014"}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
      {allWfs.length === 0 && (
        <Card className="shadow-sm">
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            No water features
          </CardContent>
        </Card>
      )}

      {/* Chemical reading entry — placeholder */}
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Chemical Reading</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
            Chemical reading entry coming soon
          </div>
        </CardContent>
      </Card>

      {/* Service checklist — placeholder */}
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Service Checklist</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
            Service checklist coming soon
          </div>
        </CardContent>
      </Card>

      {/* Complete visit — placeholder */}
      <Button className="w-full h-12 text-base" disabled>
        Complete Visit
      </Button>
    </div>
  );
}
