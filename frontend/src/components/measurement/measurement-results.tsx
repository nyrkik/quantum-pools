"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface MeasurementData {
  id: string;
  length_ft: number | null;
  width_ft: number | null;
  depth_shallow_ft: number | null;
  depth_deep_ft: number | null;
  depth_avg_ft: number | null;
  calculated_sqft: number | null;
  calculated_gallons: number | null;
  pool_shape: string | null;
  confidence: number | null;
  status: string;
  error_message: string | null;
  raw_analysis: Record<string, unknown> | null;
  applied_to_property: boolean;
}

interface MeasurementResultsProps {
  measurement: MeasurementData;
  currentValues?: {
    pool_sqft: number | null;
    pool_gallons: number | null;
    pool_volume_method: string | null;
  };
}

function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function MeasurementResults({
  measurement,
  currentValues,
}: MeasurementResultsProps) {
  const m = measurement;
  const notes = m.raw_analysis?.notes as string | undefined;
  const depthMarkers = m.raw_analysis?.depth_markers as
    | { value: string; location: string }[]
    | undefined;
  const depthProfile = m.raw_analysis?.depth_profile as string | undefined;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Dimensions</CardTitle>
            {m.confidence != null && (
              <Badge variant={m.confidence >= 0.7 ? "default" : "secondary"}>
                {Math.round(m.confidence * 100)}% confidence
              </Badge>
            )}
          </div>
          {m.pool_shape && (
            <CardDescription className="capitalize">
              {m.pool_shape} pool
            </CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Length</span>
              <p className="font-medium">{fmt(m.length_ft)} ft</p>
            </div>
            <div>
              <span className="text-muted-foreground">Width</span>
              <p className="font-medium">{fmt(m.width_ft)} ft</p>
            </div>
            <div>
              <span className="text-muted-foreground">Surface Area</span>
              <p className="font-medium">{fmt(m.calculated_sqft)} sqft</p>
            </div>
            <div>
              <span className="text-muted-foreground">Volume</span>
              <p className="font-medium text-lg">
                {m.calculated_gallons
                  ? m.calculated_gallons.toLocaleString()
                  : "—"}{" "}
                gal
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Depths</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Shallow</span>
              <p className="font-medium">{fmt(m.depth_shallow_ft)} ft</p>
            </div>
            <div>
              <span className="text-muted-foreground">Deep</span>
              <p className="font-medium">{fmt(m.depth_deep_ft)} ft</p>
            </div>
            <div>
              <span className="text-muted-foreground">Average</span>
              <p className="font-medium">{fmt(m.depth_avg_ft)} ft</p>
            </div>
          </div>
          {depthProfile && (
            <div className="mt-3 pt-3 border-t">
              <span className="text-xs text-muted-foreground">Profile: </span>
              <span className="text-xs capitalize">
                {depthProfile.replace("_", " ")}
              </span>
            </div>
          )}
          {depthMarkers && depthMarkers.length > 0 && (
            <div className="mt-2 space-y-1">
              <span className="text-xs text-muted-foreground">Markers:</span>
              {depthMarkers.map((dm, i) => (
                <div key={i} className="text-xs flex justify-between">
                  <span className="font-medium">{dm.value}</span>
                  <span className="text-muted-foreground">{dm.location}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {currentValues && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Before / After</CardTitle>
            <CardDescription>
              Current property values vs. new measurement
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Surface Area</span>
                <span>
                  {fmt(currentValues.pool_sqft)} → {fmt(m.calculated_sqft)} sqft
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Volume</span>
                <span>
                  {currentValues.pool_gallons?.toLocaleString() ?? "—"} →{" "}
                  {m.calculated_gallons?.toLocaleString() ?? "—"} gal
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Method</span>
                <span>
                  {currentValues.pool_volume_method ?? "none"} → measured
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {notes && (
        <div className="text-sm text-muted-foreground bg-muted p-3 rounded-md">
          {notes}
        </div>
      )}
    </div>
  );
}

export type { MeasurementData };
