"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, Play, Camera, Beaker, CheckSquare, Clock } from "lucide-react";
import type { Customer, Property } from "../customer-types";

interface VisitHistoryItem {
  id: string;
  scheduled_date: string | null;
  status: string;
  duration_minutes: number | null;
  tech_name: string | null;
  notes: string | null;
  photo_count: number;
  reading_count: number;
  checklist_total: number;
  checklist_completed: number;
}

interface ServiceSummarySectionProps {
  customerId: string;
  customer: Customer;
  properties: Property[];
}

export function ServiceSummarySection({ customerId, customer, properties }: ServiceSummarySectionProps) {
  const router = useRouter();
  const [history, setHistory] = useState<VisitHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedPropertyId, setSelectedPropertyId] = useState<string>(
    properties.length === 1 ? properties[0].id : ""
  );

  useEffect(() => {
    if (!selectedPropertyId) return;
    setHistoryLoading(true);
    api
      .get<VisitHistoryItem[]>(`/v1/visits/history/${selectedPropertyId}?limit=5`)
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [selectedPropertyId]);

  const handleLogVisit = () => {
    const propId = selectedPropertyId || properties[0]?.id;
    if (propId) router.push(`/visits/new?property=${propId}`);
  };

  return (
    <div className="space-y-4">
      {/* Service schedule + log visit */}
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm space-y-1 flex-1">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <div>
              <span className="text-muted-foreground">Frequency: </span>
              <span className="capitalize">{customer.service_frequency || "weekly"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Days: </span>
              {customer.preferred_day
                ? customer.preferred_day.split(",").map(d => d.trim().charAt(0).toUpperCase() + d.trim().slice(1, 3)).join(", ")
                : "Any"}
            </div>
          </div>
        </div>
        <Button size="sm" onClick={handleLogVisit} disabled={properties.length === 0}>
          <Play className="h-3.5 w-3.5 mr-1.5" />
          Log Visit
        </Button>
      </div>

      {/* Property selector for multi-property */}
      {properties.length > 1 && (
        <Select value={selectedPropertyId} onValueChange={setSelectedPropertyId}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select property..." />
          </SelectTrigger>
          <SelectContent>
            {properties.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name || p.address}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* Visit History */}
      <div>
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Recent Visits</p>
        {!selectedPropertyId && properties.length > 1 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Select a property to see visit history
          </p>
        ) : historyLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : history.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No visits recorded yet
          </p>
        ) : (
          <div className="space-y-1">
            {history.map((v) => (
              <Link
                key={v.id}
                href={`/visits/${v.id}`}
                className="flex items-center gap-3 p-2 rounded-md hover:bg-muted/50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {v.scheduled_date
                        ? new Date(v.scheduled_date + "T00:00:00").toLocaleDateString()
                        : "No date"}
                    </span>
                    <Badge
                      variant={v.status === "completed" ? "default" : "outline"}
                      className="text-[10px] px-1.5"
                    >
                      {v.status}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                    {v.tech_name && <span>{v.tech_name}</span>}
                    {v.duration_minutes != null && (
                      <span className="flex items-center gap-0.5">
                        <Clock className="h-3 w-3" />{v.duration_minutes}m
                      </span>
                    )}
                    {v.checklist_total > 0 && (
                      <span className="flex items-center gap-0.5">
                        <CheckSquare className="h-3 w-3" />{v.checklist_completed}/{v.checklist_total}
                      </span>
                    )}
                    {v.reading_count > 0 && (
                      <span className="flex items-center gap-0.5">
                        <Beaker className="h-3 w-3" />{v.reading_count}
                      </span>
                    )}
                    {v.photo_count > 0 && (
                      <span className="flex items-center gap-0.5">
                        <Camera className="h-3 w-3" />{v.photo_count}
                      </span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
