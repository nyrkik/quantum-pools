"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import type { OptimizationRequest, OptimizationSummary } from "@/types/route";

const DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
] as const;

interface OptimizationControlsProps {
  onOptimize: (req: OptimizationRequest) => Promise<void>;
  onSave: () => Promise<void>;
  optimizing: boolean;
  saving: boolean;
  hasResults: boolean;
  summary?: OptimizationSummary | null;
  selectedDay: string;
  onDayChange: (day: string) => void;
}

export default function OptimizationControls({
  onOptimize,
  onSave,
  optimizing,
  saving,
  hasResults,
  summary,
  selectedDay,
  onDayChange,
}: OptimizationControlsProps) {
  const [mode, setMode] = useState<OptimizationRequest["mode"]>("full_per_day");
  const [speed, setSpeed] = useState<OptimizationRequest["speed"]>("quick");

  const handleOptimize = () => {
    onOptimize({
      mode,
      speed,
      service_day: mode !== "cross_day" ? selectedDay : undefined,
    });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Service Day</Label>
        <Select value={selectedDay} onValueChange={onDayChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DAYS.map((d) => (
              <SelectItem key={d} value={d}>
                {d.charAt(0).toUpperCase() + d.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Mode</Label>
        <Select value={mode} onValueChange={(v) => setMode(v as OptimizationRequest["mode"])}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="full_per_day">Full (assign techs)</SelectItem>
            <SelectItem value="refine">Refine (reorder only)</SelectItem>
            <SelectItem value="cross_day">Cross-day balance</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Speed</Label>
        <Select value={speed} onValueChange={(v) => setSpeed(v as OptimizationRequest["speed"])}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="quick">Quick (30s)</SelectItem>
            <SelectItem value="thorough">Thorough (120s)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex gap-2">
        <Button onClick={handleOptimize} disabled={optimizing} className="flex-1">
          {optimizing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {optimizing ? "Optimizing..." : "Optimize"}
        </Button>
        {hasResults && (
          <Button variant="outline" onClick={onSave} disabled={saving} className="flex-1">
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {saving ? "Saving..." : "Save Routes"}
          </Button>
        )}
      </div>

      {summary && (
        <div className="rounded-md border p-3 text-sm space-y-1">
          <p className="font-medium">Results</p>
          <p>Routes: {summary.total_routes}</p>
          <p>Stops: {summary.total_stops}</p>
          <p>Distance: {summary.total_distance_miles} mi</p>
          <p>Duration: {summary.total_duration_minutes} min</p>
        </div>
      )}
    </div>
  );
}
