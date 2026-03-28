"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, MapPin, Play, ArrowLeft } from "lucide-react";

function NewVisitContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [starting, setStarting] = useState(false);
  const [propertyInfo, setPropertyInfo] = useState<{
    address: string; city: string; customer_name: string; gate_code: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const propertyId = searchParams.get("property");
  const routeStopId = searchParams.get("route_stop");

  useEffect(() => {
    if (!propertyId) { setLoading(false); return; }
    api.get<{ address: string; city: string; customer_id: string; gate_code: string | null }>(
      `/v1/properties/${propertyId}`
    ).then(async (prop) => {
      let customerName = "";
      try {
        const cust = await api.get<{ first_name: string; last_name: string; company_name: string | null }>(
          `/v1/customers/${prop.customer_id}`
        );
        customerName = cust.company_name || `${cust.first_name} ${cust.last_name}`;
      } catch {}
      setPropertyInfo({
        address: prop.address,
        city: prop.city,
        customer_name: customerName,
        gate_code: prop.gate_code,
      });
    }).catch(() => {}).finally(() => setLoading(false));
  }, [propertyId]);

  const handleStart = async () => {
    if (!propertyId) return;
    setStarting(true);
    try {
      const body: Record<string, string | null> = {
        property_id: propertyId,
        route_stop_id: routeStopId || null,
      };
      const result = await api.post<{ visit: { id: string } }>("/v1/visits/start", body);
      router.replace(`/visits/${result.visit.id}`);
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err
        ? (err as { message: string }).message : "Failed to start visit";
      toast.error(msg);
      setStarting(false);
    }
  };

  if (!propertyId) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm text-muted-foreground">Missing property ID</p>
        <Button variant="ghost" size="sm" onClick={() => router.back()}>Go back</Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto py-8 px-4">
      <Button variant="ghost" size="sm" className="mb-4" onClick={() => router.back()}>
        <ArrowLeft className="h-4 w-4 mr-1" /> Back
      </Button>

      <Card className="shadow-sm">
        <CardContent className="pt-6 space-y-4">
          <div className="text-center space-y-2">
            <MapPin className="h-8 w-8 text-primary mx-auto" />
            <h2 className="text-lg font-semibold">Start Visit</h2>
            {propertyInfo && (
              <>
                <p className="text-sm font-medium">{propertyInfo.customer_name}</p>
                <p className="text-sm text-muted-foreground">{propertyInfo.address}, {propertyInfo.city}</p>
                {propertyInfo.gate_code && (
                  <p className="text-sm">Gate: <span className="font-bold">{propertyInfo.gate_code}</span></p>
                )}
              </>
            )}
          </div>

          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => router.back()}>
              Cancel
            </Button>
            <Button className="flex-1" onClick={handleStart} disabled={starting}>
              {starting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Start Visit
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function NewVisitPage() {
  return (
    <Suspense fallback={<div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div>}>
      <NewVisitContent />
    </Suspense>
  );
}
