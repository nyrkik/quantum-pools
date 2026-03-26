"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function NewVisitPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const propertyId = searchParams.get("property");
    const routeStopId = searchParams.get("route_stop");

    if (!propertyId) {
      setError("Missing property ID");
      return;
    }

    const startVisit = async () => {
      try {
        const body: Record<string, string | null> = {
          property_id: propertyId,
          route_stop_id: routeStopId || null,
        };

        const result = await api.post<{ visit: { id: string } }>("/v1/visits/start", body);
        router.replace(`/visits/${result.visit.id}`);
      } catch (err: unknown) {
        const msg =
          err && typeof err === "object" && "message" in err
            ? (err as { message: string }).message
            : "Failed to start visit";
        toast.error(msg);
        setError(msg);
      }
    };

    startVisit();
  }, [router, searchParams]);

  if (error) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm text-muted-foreground">{error}</p>
        <button onClick={() => router.back()} className="text-sm text-primary hover:underline">
          Go back
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <p className="text-sm text-muted-foreground">Starting visit...</p>
    </div>
  );
}
