"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import {
  Loader2,
  Satellite,
  TreePine,
  Droplets,
  RefreshCw,
  Eye,
  AlertCircle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SatelliteAnalysis, BulkAnalysisResponse } from "@/types/satellite";
import type { ProfitabilityOverview } from "@/types/profitability";

interface PropertyRow {
  id: string;
  address: string;
  city: string;
  customer_name: string;
  pool_sqft: number | null;
  lat: number | null;
  lng: number | null;
  analysis: SatelliteAnalysis | null;
}

export default function SatellitePage() {
  const [properties, setProperties] = useState<PropertyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedAnalysis, setSelectedAnalysis] = useState<SatelliteAnalysis | null>(null);
  const [imageDialogOpen, setImageDialogOpen] = useState(false);

  const loadData = useCallback(async () => {
    try {
      // Two API calls: profitability overview (has customer names + property data) and all satellite analyses
      const [overview, analyses] = await Promise.all([
        api.get<ProfitabilityOverview>("/v1/profitability/overview"),
        api.get<SatelliteAnalysis[]>("/v1/satellite/all"),
      ]);

      const analysisMap = new Map(analyses.map((a) => [a.property_id, a]));

      const rows: PropertyRow[] = overview.accounts.map((acct) => ({
        id: acct.property_id,
        address: acct.property_address,
        city: "",
        customer_name: acct.customer_name,
        pool_sqft: acct.pool_sqft,
        lat: 1, // profitability only includes geocoded properties
        lng: 1,
        analysis: analysisMap.get(acct.property_id) || null,
      }));

      setProperties(rows);
    } catch {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const runBulkAnalysis = async (force = false) => {
    setAnalyzing(true);
    try {
      const result = await api.post<BulkAnalysisResponse>("/v1/satellite/bulk-analyze", {
        force_reanalyze: force,
      });
      toast.success(
        `Analyzed ${result.analyzed} properties. ${result.skipped} skipped, ${result.failed} failed.`
      );
      await loadData();
    } catch {
      toast.error("Bulk analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const analyzeOne = async (propertyId: string) => {
    try {
      const result = await api.post<SatelliteAnalysis>(
        `/v1/satellite/properties/${propertyId}/analyze?force=true`
      );
      setProperties((prev) =>
        prev.map((p) => (p.id === propertyId ? { ...p, analysis: result } : p))
      );
      toast.success("Analysis complete");
    } catch {
      toast.error("Analysis failed");
    }
  };

  const viewImage = (analysis: SatelliteAnalysis) => {
    setSelectedAnalysis(analysis);
    setImageDialogOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const analyzedCount = properties.filter((p) => p.analysis).length;
  const totalCount = properties.length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Satellite Analysis</h1>
          <p className="text-muted-foreground">
            {analyzedCount} of {totalCount} properties analyzed
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => runBulkAnalysis(false)}
            disabled={analyzing}
          >
            {analyzing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Satellite className="mr-2 h-4 w-4" />
            )}
            Analyze New
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => runBulkAnalysis(true)}
            disabled={analyzing}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Re-analyze All
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pools Detected</CardTitle>
            <Droplets className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {properties.filter((p) => p.analysis?.pool_detected).length}
            </div>
            <p className="text-xs text-muted-foreground">of {analyzedCount} analyzed</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Vegetation</CardTitle>
            <TreePine className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {analyzedCount > 0
                ? (
                    properties
                      .filter((p) => p.analysis)
                      .reduce((sum, p) => sum + (p.analysis?.vegetation_pct || 0), 0) /
                    analyzedCount
                  ).toFixed(1)
                : "0"}
              %
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">High Canopy</CardTitle>
            <TreePine className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-600">
              {properties.filter((p) => (p.analysis?.canopy_overhang_pct || 0) > 30).length}
            </div>
            <p className="text-xs text-muted-foreground">&gt;30% overhang near pool</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Not Analyzed</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">
              {totalCount - analyzedCount}
            </div>
            <p className="text-xs text-muted-foreground">pending analysis</p>
          </CardContent>
        </Card>
      </div>

      {/* Results Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Property Analysis Results</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Client</TableHead>
                <TableHead>Address</TableHead>
                <TableHead className="text-right">Pool sqft</TableHead>
                <TableHead className="text-right">Vegetation</TableHead>
                <TableHead className="text-right">Canopy</TableHead>
                <TableHead className="text-right">Shadow</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
                <TableHead className="text-center">Status</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {properties.map((prop) => (
                <TableRow key={prop.id}>
                  <TableCell className="font-medium">{prop.customer_name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {prop.address}
                  </TableCell>
                  <TableCell className="text-right">
                    {prop.analysis?.estimated_pool_sqft
                      ? `${prop.analysis.estimated_pool_sqft.toLocaleString()} ft²`
                      : prop.pool_sqft
                      ? `${prop.pool_sqft.toLocaleString()} ft² (manual)`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {prop.analysis ? `${prop.analysis.vegetation_pct}%` : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {prop.analysis ? (
                      <span
                        className={
                          prop.analysis.canopy_overhang_pct > 30
                            ? "text-yellow-600 font-medium"
                            : ""
                        }
                      >
                        {prop.analysis.canopy_overhang_pct}%
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {prop.analysis ? `${prop.analysis.shadow_pct}%` : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {prop.analysis ? (
                      <Badge
                        className={
                          prop.analysis.pool_confidence >= 0.7
                            ? "bg-green-100 text-green-800 hover:bg-green-100"
                            : prop.analysis.pool_confidence >= 0.4
                            ? "bg-yellow-100 text-yellow-800 hover:bg-yellow-100"
                            : "bg-red-100 text-red-800 hover:bg-red-100"
                        }
                      >
                        {(prop.analysis.pool_confidence * 100).toFixed(0)}%
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    {prop.analysis ? (
                      prop.analysis.error_message ? (
                        <Badge variant="destructive">Error</Badge>
                      ) : prop.analysis.pool_detected ? (
                        <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">
                          Pool Found
                        </Badge>
                      ) : (
                        <Badge variant="secondary">No Pool</Badge>
                      )
                    ) : (
                      <Badge variant="outline">Pending</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1 justify-end">
                      {prop.analysis?.image_url && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => viewImage(prop.analysis!)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => analyzeOne(prop.id)}
                      >
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Image Preview Dialog */}
      <Dialog open={imageDialogOpen} onOpenChange={setImageDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Satellite Image</DialogTitle>
          </DialogHeader>
          {selectedAnalysis?.image_url && (
            <div className="space-y-4">
              <img
                src={selectedAnalysis.image_url}
                alt="Satellite view"
                className="w-full rounded-lg border"
              />
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Pool Detected:</span>{" "}
                  <span className="font-medium">
                    {selectedAnalysis.pool_detected ? "Yes" : "No"}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Est. Pool Size:</span>{" "}
                  <span className="font-medium">
                    {selectedAnalysis.estimated_pool_sqft
                      ? `${selectedAnalysis.estimated_pool_sqft.toLocaleString()} ft²`
                      : "N/A"}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Vegetation:</span>{" "}
                  <span className="font-medium">{selectedAnalysis.vegetation_pct}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Canopy Overhang:</span>{" "}
                  <span className="font-medium">{selectedAnalysis.canopy_overhang_pct}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Shadow:</span>{" "}
                  <span className="font-medium">{selectedAnalysis.shadow_pct}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Hardscape:</span>{" "}
                  <span className="font-medium">{selectedAnalysis.hardscape_pct}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Confidence:</span>{" "}
                  <span className="font-medium">
                    {(selectedAnalysis.pool_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
