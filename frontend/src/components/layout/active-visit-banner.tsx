"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Check, ExternalLink, Loader2, ClipboardList } from "lucide-react";

interface ActiveVisit {
  visit: {
    id: string;
    status: string;
    started_at: string | null;
  };
  property: {
    id: string;
    name: string | null;
    address: string;
  };
  customer: {
    name: string;
    company: string | null;
  } | null;
}

export function ActiveVisitBanner() {
  const router = useRouter();
  const [visit, setVisit] = useState<ActiveVisit | null>(null);
  const [completing, setCompleting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchActive = useCallback(async () => {
    try {
      const result = await api.get<ActiveVisit | null>("/v1/visits/active");
      setVisit(result);
    } catch {
      // Silently fail — banner just doesn't show
      setVisit(null);
    }
  }, []);

  // Poll for active visit every 60s
  useEffect(() => {
    fetchActive();
    const poll = setInterval(fetchActive, 60_000);
    return () => clearInterval(poll);
  }, [fetchActive]);

  // Live elapsed timer (updates every 30s to avoid excessive re-renders)
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);

    if (visit?.visit.started_at) {
      const updateElapsed = () => {
        const start = new Date(visit.visit.started_at!).getTime();
        setElapsed(Math.floor((Date.now() - start) / 1000));
      };
      updateElapsed();
      intervalRef.current = setInterval(updateElapsed, 30_000);
    } else {
      setElapsed(0);
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [visit?.visit.started_at]);

  const handleComplete = async () => {
    if (!visit) return;
    setCompleting(true);
    try {
      await api.post(`/v1/visits/${visit.visit.id}/finish`, {});
      toast.success("Visit completed");
      setVisit(null);
    } catch {
      toast.error("Failed to complete visit");
    } finally {
      setCompleting(false);
    }
  };

  if (!visit || visit.visit.status !== "in_progress") return null;

  const minutes = Math.floor(elapsed / 60);
  const label =
    visit.property.name ||
    visit.customer?.company ||
    visit.customer?.name ||
    visit.property.address;

  return (
    <div className="flex items-center justify-between gap-3 bg-blue-50 dark:bg-blue-950/40 border-b border-blue-200 dark:border-blue-800 px-4 py-2 text-sm shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        <ClipboardList className="h-4 w-4 text-blue-600 dark:text-blue-400 shrink-0" />
        <span className="text-blue-800 dark:text-blue-200 truncate">
          <span className="font-medium">Visit in progress:</span>{" "}
          <span className="truncate">{label}</span>
          <span className="text-blue-600 dark:text-blue-400 ml-2">
            {minutes} min
          </span>
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900"
          onClick={() => router.push(`/visits/${visit.visit.id}`)}
        >
          <ExternalLink className="h-3 w-3 mr-1" />
          Resume
        </Button>
        <Button
          size="sm"
          className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white"
          onClick={handleComplete}
          disabled={completing}
        >
          {completing ? (
            <Loader2 className="h-3 w-3 animate-spin mr-1" />
          ) : (
            <Check className="h-3 w-3 mr-1" />
          )}
          Complete
        </Button>
      </div>
    </div>
  );
}
