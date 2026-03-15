"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Ruler, CheckCircle } from "lucide-react";
import { resizeImage } from "@/components/measurement/photo-capture";
import { PhotoCapture, type PhotoFile } from "@/components/measurement/photo-capture";
import {
  MeasurementResults,
  type MeasurementData,
} from "@/components/measurement/measurement-results";

interface BodyOfWater {
  id: string;
  name: string | null;
  water_type: string;
  pool_type: string | null;
  pool_sqft: number | null;
  pool_gallons: number | null;
  pool_volume_method: string | null;
}

interface Property {
  id: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  pool_type: string | null;
  pool_sqft: number | null;
  pool_gallons: number | null;
  pool_volume_method: string | null;
  bodies_of_water?: BodyOfWater[];
}

type Step = "capture" | "analyze" | "apply";

export default function MeasurePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const propertyId = params.id as string;
  const bowId = searchParams.get("bow");

  const [property, setProperty] = useState<Property | null>(null);
  const [bow, setBow] = useState<BodyOfWater | null>(null);
  const [step, setStep] = useState<Step>("capture");
  const [overviewPhotos, setOverviewPhotos] = useState<PhotoFile[]>([]);
  const [depthPhotos, setDepthPhotos] = useState<PhotoFile[]>([]);
  const [scaleRef, setScaleRef] = useState("depth_marker_tile");
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [measurement, setMeasurement] = useState<MeasurementData | null>(null);
  const [pastMeasurements, setPastMeasurements] = useState<MeasurementData[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const [prop, measurements] = await Promise.all([
          api.get<Property>(`/v1/properties/${propertyId}`),
          api.get<MeasurementData[]>(`/v1/measurements/properties/${propertyId}`),
        ]);
        setProperty(prop);
        setPastMeasurements(measurements);
        // Find the targeted BOW if specified
        let targetBow: BodyOfWater | undefined;
        if (bowId && prop.bodies_of_water) {
          targetBow = prop.bodies_of_water.find((b: BodyOfWater) => b.id === bowId);
          if (targetBow) setBow(targetBow);
        }
        // Commercial pools almost always have depth marker tiles — default to tile
        // Residential pools less likely, default to yardstick
        const poolType = targetBow?.pool_type ?? prop.pool_type;
        if (poolType === "residential") {
          setScaleRef("yardstick");
        }
      } catch {
        toast.error("Failed to load property");
      }
    })();
  }, [propertyId]);

  const handleUploadAndAnalyze = async () => {
    if (overviewPhotos.length === 0) {
      toast.error("Take at least one overview photo with scale reference");
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("scale_reference", scaleRef);
      if (bowId) formData.append("body_of_water_id", bowId);
      for (const p of overviewPhotos) {
        const resized = await resizeImage(p.file);
        formData.append("overview_photos", resized);
      }
      for (const p of depthPhotos) {
        const resized = await resizeImage(p.file);
        formData.append("depth_photos", resized);
      }

      const uploaded = await api.upload<MeasurementData>(
        `/v1/measurements/properties/${propertyId}/upload`,
        formData
      );

      setStep("analyze");
      setAnalyzing(true);

      const analyzed = await api.postDirect<MeasurementData>(
        `/v1/measurements/${uploaded.id}/analyze`
      );

      setMeasurement(analyzed);

      if (analyzed.status === "failed") {
        toast.error(analyzed.error_message || "Analysis failed");
      } else {
        toast.success("Analysis complete");
      }
    } catch (e: unknown) {
      console.error("Measure upload/analyze error:", e);
      const msg =
        typeof e === "object" && e && "message" in e
          ? (e as { message: string }).message
          : typeof e === "string" ? e : "Upload failed";
      toast.error(msg);
    } finally {
      setUploading(false);
      setAnalyzing(false);
    }
  };

  const handleApply = async () => {
    if (!measurement) return;
    setApplying(true);
    try {
      await api.post(`/v1/measurements/${measurement.id}/apply`);
      toast.success(bow ? "Body of water updated with measured dimensions" : "Property updated with measured dimensions");
      setStep("apply");
      const prop = await api.get<Property>(`/v1/properties/${propertyId}`);
      setProperty(prop);
    } catch (e: unknown) {
      const msg =
        typeof e === "object" && e && "message" in e
          ? (e as { message: string }).message
          : "Failed to apply";
      toast.error(msg);
    } finally {
      setApplying(false);
    }
  };

  if (!property) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4 sm:space-y-6 pb-24 sm:pb-6">
      {/* Header */}
      <div className="flex items-start gap-2 sm:gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="shrink-0 mt-0.5"
          onClick={() => router.back()}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight flex items-center gap-2">
            <Ruler className="h-5 w-5 shrink-0" />
            Pool Measurement
          </h1>
          <p className="text-sm text-muted-foreground truncate">
            {bow ? `${bow.name || bow.water_type} — ` : ""}{property.address}, {property.city}
          </p>
        </div>
      </div>

      {/* Step indicators */}
      <div className="flex gap-1.5 sm:gap-2">
        {(["capture", "analyze", "apply"] as Step[]).map((s, i) => (
          <Badge
            key={s}
            variant={step === s ? "default" : "outline"}
            className="capitalize text-xs"
          >
            {i + 1}. {s}
          </Badge>
        ))}
      </div>

      {/* Step 1: Capture */}
      {step === "capture" && (
        <div className="space-y-4 sm:space-y-6">
          <Card>
            <CardHeader className="pb-2 sm:pb-3">
              <CardTitle className="text-base sm:text-lg">Instructions</CardTitle>
              <CardDescription>
                Take photos with your phone camera to measure the pool
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(bow?.pool_type ?? property.pool_type) === "commercial" || scaleRef === "depth_marker_tile" ? (
                <>
                  <p>
                    <strong>Overview photo:</strong> Stand back to get the full
                    pool in frame. Make sure at least one depth marker tile is
                    visible at the pool edge — the standard 6&quot;×6&quot; tiles
                    are used as the scale reference. No need to place anything extra.
                  </p>
                  <p>
                    <strong>Depth markers:</strong> Photograph each depth marker
                    tile with enough surrounding pool edge visible so the position
                    along the perimeter is clear. Multiple marker photos from
                    different positions help determine the slope profile and volume.
                  </p>
                </>
              ) : (
                <>
                  <p>
                    <strong>Overview photo:</strong> Stand back to get the full pool
                    in frame. Place a yardstick, pool pole, or other known-size
                    object next to the pool edge.
                  </p>
                  <p>
                    <strong>Depth markers:</strong> Photograph each depth marker
                    with enough surrounding pool edge visible so the position along
                    the perimeter is clear. Don&apos;t zoom in too tight — the marker
                    needs to be readable but seeing where it sits relative to the
                    pool helps calculate the slope profile.
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <div>
            <label className="text-sm font-medium mb-2 block">
              Scale Reference Object
            </label>
            <Select value={scaleRef} onValueChange={setScaleRef}>
              <SelectTrigger className="h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="depth_marker_tile">Depth Marker Tile (6&quot;×6&quot;)</SelectItem>
                <SelectItem value="yardstick">Yardstick (36&quot;)</SelectItem>
                <SelectItem value="pool_pole_8ft">Pool Pole (8 ft)</SelectItem>
                <SelectItem value="pool_pole_16ft">Pool Pole (16 ft)</SelectItem>
                <SelectItem value="shoe">Shoe (~12&quot;)</SelectItem>
                <SelectItem value="other">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <PhotoCapture
            label="Overview Photos (with scale reference)"
            photoType="overview"
            photos={overviewPhotos}
            onAdd={(p) => setOverviewPhotos((prev) => [...prev, p])}
            onRemove={(i) =>
              setOverviewPhotos((prev) => prev.filter((_, idx) => idx !== i))
            }
          />

          <PhotoCapture
            label="Depth Marker Photos"
            photoType="depth"
            photos={depthPhotos}
            onAdd={(p) => setDepthPhotos((prev) => [...prev, p])}
            onRemove={(i) =>
              setDepthPhotos((prev) => prev.filter((_, idx) => idx !== i))
            }
          />

          {/* Sticky bottom action button on mobile */}
          <div className="fixed bottom-0 left-0 right-0 p-4 bg-background border-t sm:static sm:p-0 sm:border-0 sm:bg-transparent z-30">
            <Button
              onClick={handleUploadAndAnalyze}
              disabled={overviewPhotos.length === 0 || uploading}
              className="w-full h-12 sm:h-11 text-base sm:text-sm"
              size="lg"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>Upload & Analyze</>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: Analyze */}
      {step === "analyze" && (
        <div className="space-y-4 sm:space-y-6">
          {analyzing ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin mb-4" />
                <p className="text-sm text-muted-foreground">
                  Claude is analyzing your photos...
                </p>
              </CardContent>
            </Card>
          ) : measurement ? (
            <>
              <MeasurementResults
                measurement={measurement}
                currentValues={{
                  pool_sqft: bow?.pool_sqft ?? property.pool_sqft,
                  pool_gallons: bow?.pool_gallons ?? property.pool_gallons,
                  pool_volume_method: bow?.pool_volume_method ?? property.pool_volume_method,
                }}
              />

              {measurement.status === "completed" && (
                <div className="fixed bottom-0 left-0 right-0 p-4 bg-background border-t sm:static sm:p-0 sm:border-0 sm:bg-transparent z-30">
                  <div className="flex gap-3">
                    <Button
                      variant="outline"
                      onClick={() => {
                        setStep("capture");
                        setMeasurement(null);
                        setOverviewPhotos([]);
                        setDepthPhotos([]);
                      }}
                      className="flex-1 h-12 sm:h-10"
                    >
                      Retake
                    </Button>
                    <Button
                      onClick={handleApply}
                      disabled={applying}
                      className="flex-1 h-12 sm:h-10"
                    >
                      {applying ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        bow ? "Apply to Body of Water" : "Apply to Property"
                      )}
                    </Button>
                  </div>
                </div>
              )}

              {measurement.status === "failed" && (
                <Button
                  variant="outline"
                  onClick={() => {
                    setStep("capture");
                    setMeasurement(null);
                  }}
                  className="w-full h-12 sm:h-10"
                >
                  Try Again
                </Button>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* Step 3: Applied */}
      {step === "apply" && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-10 sm:py-12">
            <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
            <h2 className="text-lg font-semibold mb-1">
              Measurements Applied
            </h2>
            <p className="text-sm text-muted-foreground mb-6 text-center px-4">
              {bow ? "Body of water" : "Property"} record updated with ground-truth dimensions
            </p>
            <div className="grid grid-cols-2 gap-4 text-center text-sm mb-6 w-full max-w-xs">
              <div>
                <span className="text-muted-foreground">Surface Area</span>
                <p className="font-medium text-lg">
                  {(bow?.pool_sqft ?? property.pool_sqft)
                    ? `${(bow?.pool_sqft ?? property.pool_sqft)!.toLocaleString()} sqft`
                    : "—"}
                </p>
              </div>
              <div>
                <span className="text-muted-foreground">Volume</span>
                <p className="font-medium text-lg">
                  {(bow?.pool_gallons ?? property.pool_gallons)
                    ? `${(bow?.pool_gallons ?? property.pool_gallons)!.toLocaleString()} gal`
                    : "—"}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              className="h-12 sm:h-10"
              onClick={() => router.back()}
            >
              Back to Properties
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Past measurements */}
      {pastMeasurements.length > 0 && step === "capture" && (
        <Card>
          <CardHeader className="pb-2 sm:pb-3">
            <CardTitle className="text-sm">Previous Measurements</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pastMeasurements.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between text-sm border-b last:border-0 pb-2 last:pb-0"
                >
                  <div>
                    <span className="font-medium">
                      {m.calculated_gallons
                        ? `${m.calculated_gallons.toLocaleString()} gal`
                        : "—"}
                    </span>
                    <span className="text-muted-foreground ml-2">
                      {m.pool_shape ?? ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge
                      variant={
                        m.status === "completed"
                          ? "default"
                          : m.status === "failed"
                            ? "destructive"
                            : "secondary"
                      }
                      className="text-xs"
                    >
                      {m.status}
                    </Badge>
                    {m.applied_to_property && (
                      <Badge variant="outline" className="text-xs">Applied</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
