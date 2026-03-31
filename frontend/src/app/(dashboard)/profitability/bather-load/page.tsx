"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
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
import { Loader2, Calculator, Users, AlertCircle } from "lucide-react";
import type {
  Jurisdiction,
  BatherLoadRequest,
  BatherLoadResult,
} from "@/types/profitability";

export default function BatherLoadPage() {
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([]);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [result, setResult] = useState<BatherLoadResult | null>(null);
  const [form, setForm] = useState<BatherLoadRequest>({
    pool_sqft: null,
    pool_gallons: null,
    shallow_sqft: null,
    deep_sqft: null,
    has_deep_end: false,
    spa_sqft: null,
    diving_board_count: 0,
    pump_flow_gpm: null,
    is_indoor: false,
    jurisdiction_id: null,
  });

  useEffect(() => {
    loadJurisdictions();
  }, []);

  async function loadJurisdictions() {
    try {
      const data = await api.get<Jurisdiction[]>("/v1/profitability/jurisdictions");
      setJurisdictions(data);
      const ca = data.find((j) => j.method_key === "california");
      if (ca) {
        setForm((f) => ({ ...f, jurisdiction_id: ca.id }));
      }
    } catch {
      toast.error("Failed to load jurisdictions");
    } finally {
      setLoading(false);
    }
  }

  async function handleCalculate() {
    setCalculating(true);
    try {
      const data = await api.post<BatherLoadResult>(
        "/v1/profitability/bather-load/calculate",
        form
      );
      setResult(data);
    } catch {
      toast.error("Failed to calculate bather load");
    } finally {
      setCalculating(false);
    }
  }

  function numVal(v: string): number | null {
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  function intVal(v: string): number | null {
    const n = parseInt(v);
    return isNaN(n) ? null : n;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const selectedJurisdiction = jurisdictions.find((j) => j.id === form.jurisdiction_id);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Bather Load Calculator</h1>
        <p className="text-muted-foreground">
          Calculate maximum bather load by jurisdiction
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Input Form */}
        <Card>
          <CardHeader>
            <CardTitle>Pool Characteristics</CardTitle>
            <CardDescription>
              Enter what you know — unknown values will be estimated
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Jurisdiction</Label>
              <Select
                value={form.jurisdiction_id ?? ""}
                onValueChange={(v) => setForm({ ...form, jurisdiction_id: v })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select jurisdiction..." />
                </SelectTrigger>
                <SelectContent>
                  {jurisdictions.map((j) => (
                    <SelectItem key={j.id} value={j.id}>
                      {j.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedJurisdiction?.notes && (
                <p className="text-xs text-muted-foreground">{selectedJurisdiction.notes}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Pool Area (sqft)</Label>
                <Input
                  type="number"
                  placeholder="e.g. 800"
                  value={form.pool_sqft ?? ""}
                  onChange={(e) => setForm({ ...form, pool_sqft: numVal(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label>Pool Volume (gallons)</Label>
                <Input
                  type="number"
                  placeholder="e.g. 20000"
                  value={form.pool_gallons ?? ""}
                  onChange={(e) => setForm({ ...form, pool_gallons: intVal(e.target.value) as number | null })}
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="has_deep_end"
                checked={form.has_deep_end}
                onCheckedChange={(v) => setForm({ ...form, has_deep_end: !!v })}
              />
              <Label htmlFor="has_deep_end">Has deep end (5ft+)</Label>
            </div>

            {form.has_deep_end && selectedJurisdiction?.depth_based && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Shallow Area (sqft)</Label>
                  <Input
                    type="number"
                    placeholder="Auto-estimated"
                    value={form.shallow_sqft ?? ""}
                    onChange={(e) => setForm({ ...form, shallow_sqft: numVal(e.target.value) })}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Deep Area (sqft)</Label>
                  <Input
                    type="number"
                    placeholder="Auto-estimated"
                    value={form.deep_sqft ?? ""}
                    onChange={(e) => setForm({ ...form, deep_sqft: numVal(e.target.value) })}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Spa Area (sqft)</Label>
                <Input
                  type="number"
                  placeholder="0 if none"
                  value={form.spa_sqft ?? ""}
                  onChange={(e) => setForm({ ...form, spa_sqft: numVal(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label>Diving Boards</Label>
                <Input
                  type="number"
                  min={0}
                  value={form.diving_board_count ?? 0}
                  onChange={(e) => setForm({ ...form, diving_board_count: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Pump Flow Rate (GPM)</Label>
              <Input
                type="number"
                placeholder="Auto-estimated from volume"
                value={form.pump_flow_gpm ?? ""}
                onChange={(e) => setForm({ ...form, pump_flow_gpm: numVal(e.target.value) })}
              />
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="is_indoor"
                checked={form.is_indoor}
                onCheckedChange={(v) => setForm({ ...form, is_indoor: !!v })}
              />
              <Label htmlFor="is_indoor">Indoor pool</Label>
            </div>

            <Button onClick={handleCalculate} disabled={calculating} className="w-full">
              {calculating ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Calculator className="mr-2 h-4 w-4" />
              )}
              Calculate Bather Load
            </Button>
          </CardContent>
        </Card>

        {/* Results */}
        <Card>
          <CardHeader>
            <CardTitle>Results</CardTitle>
          </CardHeader>
          <CardContent>
            {result ? (
              <div className="space-y-6">
                <div className="flex items-center gap-4">
                  <Users className="h-12 w-12 text-primary" />
                  <div>
                    <div className="text-4xl font-bold">{result.max_bathers}</div>
                    <p className="text-sm text-muted-foreground">
                      Maximum bathers — {result.jurisdiction_name}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Pool bathers:</span>
                    <span className="ml-2 font-medium">{result.pool_bathers}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Spa bathers:</span>
                    <span className="ml-2 font-medium">{result.spa_bathers}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Diving bathers:</span>
                    <span className="ml-2 font-medium">{result.diving_bathers}</span>
                  </div>
                  {result.flow_rate_bathers !== null && (
                    <div>
                      <span className="text-muted-foreground">Flow rate limit:</span>
                      <span className="ml-2 font-medium">{result.flow_rate_bathers}</span>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Total sqft:</span>
                    <span className="ml-2 font-medium">{result.pool_sqft_used.toFixed(0)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Shallow:</span>
                    <span className="ml-2 font-medium">{result.shallow_sqft_used.toFixed(0)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Deep:</span>
                    <span className="ml-2 font-medium">{result.deep_sqft_used.toFixed(0)}</span>
                  </div>
                </div>

                {result.estimated_fields.length > 0 && (
                  <div className="flex items-start gap-2 rounded-md border border-yellow-200 bg-yellow-50 p-3">
                    <AlertCircle className="h-4 w-4 text-yellow-600 mt-0.5" />
                    <div className="text-sm">
                      <p className="font-medium text-yellow-800">Estimated values used:</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {result.estimated_fields.map((f) => (
                          <Badge key={f} variant="outline" className="text-yellow-700">
                            {f.replace(/_/g, " ")}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Calculator className="h-12 w-12 mb-4" />
                <p>Enter pool characteristics and click Calculate</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
