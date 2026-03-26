"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Loader2 } from "lucide-react";
import { VisitHeader } from "@/components/visits/visit-header";
import { VisitChecklist } from "@/components/visits/visit-checklist";
import { VisitReadings } from "@/components/visits/visit-readings";
import { VisitPhotos } from "@/components/visits/visit-photos";
import { VisitCharges } from "@/components/visits/visit-charges";
import { VisitNotes } from "@/components/visits/visit-notes";
import { VisitFooter } from "@/components/visits/visit-footer";
import type {
  VisitContext,
  VisitChecklistItem,
  VisitReading,
  VisitPhoto,
} from "@/types/visit";

export default function VisitPage() {
  const params = useParams();
  const router = useRouter();
  const visitId = params.id as string;

  const [context, setContext] = useState<VisitContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  const fetchContext = useCallback(async () => {
    try {
      const data = await api.get<VisitContext>(`/v1/visits/${visitId}/context`);
      setContext(data);
      setNotes(data.visit.notes || "");
      setError(null);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? (err as { message: string }).message
          : "Visit not found";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [visitId]);

  useEffect(() => {
    fetchContext();
  }, [fetchContext]);

  const handleChecklistUpdate = useCallback(
    (items: VisitChecklistItem[]) => {
      if (!context) return;
      setContext({ ...context, checklist: items });
    },
    [context]
  );

  const handleReadingsUpdate = useCallback(
    (readings: VisitReading[]) => {
      if (!context) return;
      setContext({ ...context, readings });
    },
    [context]
  );

  const handlePhotosUpdate = useCallback(
    (photos: VisitPhoto[]) => {
      if (!context) return;
      setContext({ ...context, photos });
    },
    [context]
  );

  const handleChargesChanged = useCallback(() => {
    fetchContext();
  }, [fetchContext]);

  const handleNotesChange = useCallback(
    (text: string) => {
      setNotes(text);
      // Notes are saved on visit complete, not individually
    },
    []
  );

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !context) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm text-muted-foreground">{error || "Visit not found"}</p>
        <button onClick={() => router.back()} className="text-sm text-primary hover:underline">
          Go back
        </button>
      </div>
    );
  }

  if (context.visit.status === "completed") {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm text-muted-foreground">This visit has been completed.</p>
        <button onClick={() => router.back()} className="text-sm text-primary hover:underline">
          Go back
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-3 pb-24">
      <Card className="shadow-sm p-4">
        <VisitHeader
          customer={context.customer}
          property={context.property}
          waterFeatures={context.water_features}
          startedAt={context.visit.started_at}
          onBack={() => router.back()}
        />
      </Card>

      <VisitChecklist
        visitId={visitId}
        items={context.checklist}
        onUpdate={handleChecklistUpdate}
      />

      <VisitReadings
        visitId={visitId}
        waterFeatures={context.water_features}
        readings={context.readings}
        lastReadings={context.last_readings}
        onUpdate={handleReadingsUpdate}
      />

      <VisitPhotos
        visitId={visitId}
        photos={context.photos}
        onUpdate={handlePhotosUpdate}
      />

      <VisitCharges
        visitId={visitId}
        propertyId={context.visit.property_id}
        customerId={context.visit.customer_id}
        charges={context.charges}
        onUpdate={handleChargesChanged}
      />

      <VisitNotes
        notes={notes}
        onChange={handleNotesChange}
      />

      <VisitFooter
        context={context}
        notes={notes}
        onChargesChanged={handleChargesChanged}
      />
    </div>
  );
}
