"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, MapPin, Play, AlertTriangle } from "lucide-react";
import { BackButton } from "@/components/ui/back-button";

interface ActiveVisitData {
  visit: { id: string; status: string; started_at: string | null };
  property: { id: string; name: string | null; address: string };
  customer: { name: string; company: string | null } | null;
}

function NewVisitContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [starting, setStarting] = useState(false);
  const [propertyInfo, setPropertyInfo] = useState<{
    address: string; city: string; customer_name: string; gate_code: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeVisit, setActiveVisit] = useState<ActiveVisitData | null>(null);
  const [completingOld, setCompletingOld] = useState(false);

  const propertyId = searchParams.get("property");
  const routeStopId = searchParams.get("route_stop");

  useEffect(() => {
    if (!propertyId) { setLoading(false); return; }

    const init = async () => {
      try {
        // Fetch property info and check for active visit in parallel
        const [prop, active] = await Promise.all([
          api.get<{ address: string; city: string; customer_id: string; gate_code: string | null }>(
            `/v1/properties/${propertyId}`
          ),
          api.get<ActiveVisitData | null>("/v1/visits/active"),
        ]);

        // If active visit is for the SAME property, redirect to it
        if (active && active.visit.status === "in_progress" && active.property.id === propertyId) {
          router.replace(`/visits/${active.visit.id}`);
          return;
        }

        // If active visit for a DIFFERENT property, show conflict prompt
        if (active && active.visit.status === "in_progress") {
          setActiveVisit(active);
        }

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
      } catch {} finally {
        setLoading(false);
      }
    };

    init();
  }, [propertyId, router]);

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

  const handleCompleteAndStart = async () => {
    if (!activeVisit) return;
    setCompletingOld(true);
    try {
      await api.post(`/v1/visits/${activeVisit.visit.id}/finish`, {});
      toast.success("Previous visit completed");
      setActiveVisit(null);
      // Now start the new visit
      await handleStart();
    } catch {
      toast.error("Failed to complete previous visit");
      setCompletingOld(false);
    }
  };

  if (!propertyId) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm text-muted-foreground">Missing property ID</p>
        <BackButton fallback="/visits" label="Go back" />
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

  // Conflict: active visit at another property
  if (activeVisit) {
    const activeLabel =
      activeVisit.property.name ||
      activeVisit.customer?.company ||
      activeVisit.customer?.name ||
      activeVisit.property.address;

    return (
      <div className="max-w-md mx-auto py-8 px-4">
        <BackButton fallback="/visits" className="mb-4" />

        <Card className="shadow-sm border-amber-300">
          <CardContent className="pt-6 space-y-4">
            <div className="text-center space-y-2">
              <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto" />
              <h2 className="text-lg font-semibold">Visit Already in Progress</h2>
              <p className="text-sm text-muted-foreground">
                You have a visit in progress at{" "}
                <span className="font-medium text-foreground">{activeLabel}</span>.
              </p>
              <p className="text-sm text-muted-foreground">
                Complete it first, or resume the existing visit.
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <Button
                className="w-full"
                onClick={handleCompleteAndStart}
                disabled={completingOld}
              >
                {completingOld ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Complete &amp; Start New
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => router.push(`/visits/${activeVisit.visit.id}`)}
              >
                Resume Existing
              </Button>
              <Button
                variant="ghost"
                className="w-full"
                onClick={() => router.back()}
              >
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Normal: no active visit — show start confirmation
  return (
    <div className="max-w-md mx-auto py-8 px-4">
      <BackButton fallback="/visits" className="mb-4" />

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
