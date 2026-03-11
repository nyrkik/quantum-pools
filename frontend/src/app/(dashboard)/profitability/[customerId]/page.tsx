"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Loader2, ArrowLeft, Save } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type {
  ProfitabilityAccount,
  PropertyDifficulty,
  PropertyDifficultyUpdate,
} from "@/types/profitability";

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

export default function AccountDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const [accounts, setAccounts] = useState<ProfitabilityAccount[]>([]);
  const [difficulty, setDifficulty] = useState<PropertyDifficulty | null>(null);
  const [diffForm, setDiffForm] = useState<PropertyDifficultyUpdate>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadData();
  }, [customerId]);

  async function loadData() {
    try {
      const accts = await api.get<ProfitabilityAccount[]>(
        `/v1/profitability/account/${customerId}`
      );
      setAccounts(accts);

      if (accts.length > 0) {
        const diff = await api.get<PropertyDifficulty>(
          `/v1/profitability/properties/${accts[0].property_id}/difficulty`
        );
        setDifficulty(diff);
        setDiffForm({
          access_difficulty_score: diff.access_difficulty_score,
          customer_demands_score: diff.customer_demands_score,
          chemical_demand_score: diff.chemical_demand_score,
          callback_frequency_score: diff.callback_frequency_score,
          equipment_age_years: diff.equipment_age_years,
          shade_exposure: diff.shade_exposure,
          tree_debris_level: diff.tree_debris_level,
          enclosure_type: diff.enclosure_type,
        });
      }
    } catch {
      toast.error("Failed to load account data");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveDifficulty() {
    if (!accounts.length || !difficulty) return;
    setSaving(true);
    try {
      const updated = await api.put<PropertyDifficulty>(
        `/v1/profitability/properties/${accounts[0].property_id}/difficulty`,
        diffForm
      );
      setDifficulty(updated);
      toast.success("Difficulty saved — reload to see updated profitability");
    } catch {
      toast.error("Failed to save difficulty");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!accounts.length) {
    return <p className="text-muted-foreground">No account data found.</p>;
  }

  const account = accounts[0];
  const cb = account.cost_breakdown;

  const waterfallData = [
    { name: "Revenue", value: cb.revenue, fill: "#3b82f6" },
    { name: "Labor", value: -cb.labor_cost, fill: "#ef4444" },
    { name: "Chemical", value: -cb.chemical_cost, fill: "#f97316" },
    { name: "Travel", value: -cb.travel_cost, fill: "#eab308" },
    { name: "Overhead", value: -cb.overhead_cost, fill: "#8b5cf6" },
    { name: "Profit", value: cb.profit, fill: cb.profit >= 0 ? "#22c55e" : "#ef4444" },
  ];

  const scoreFields = [
    { key: "access_difficulty_score", label: "Access Difficulty", description: "Locked gates, stairs, narrow paths" },
    { key: "customer_demands_score", label: "Customer Demands", description: "Frequent calls, complaints, special requests" },
    { key: "chemical_demand_score", label: "Chemical Demand", description: "Chronic algae, unstable chemistry" },
    { key: "callback_frequency_score", label: "Callback Frequency", description: "Rework rate" },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/profitability">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">{account.customer_name}</h1>
          <p className="text-muted-foreground">{account.property_address}</p>
        </div>
      </div>

      {/* Rate comparison */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Current Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(account.monthly_rate)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Suggested Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${cb.rate_gap > 0 ? "text-yellow-600" : "text-green-600"}`}>
              {formatCurrency(cb.suggested_rate)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Margin</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${cb.margin_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
              {cb.margin_pct.toFixed(1)}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Difficulty</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{account.difficulty_score.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">{account.difficulty_multiplier.toFixed(2)}x multiplier</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Cost Waterfall */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cost Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={waterfallData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={(value) => [formatCurrency(Math.abs(value as number)), ""]} />
                <Bar dataKey="value">
                  {waterfallData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Difficulty Scores */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Difficulty Scoring</CardTitle>
            {difficulty && (
              <Badge variant="outline">
                Composite: {difficulty.composite_score.toFixed(1)}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="space-y-6">
            {scoreFields.map((field) => (
              <div key={field.key} className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-sm">{field.label}</Label>
                  <span className="text-sm font-medium">
                    {(diffForm[field.key] as number)?.toFixed(1) ?? "1.0"}
                  </span>
                </div>
                <Slider
                  min={1}
                  max={5}
                  step={0.5}
                  value={[diffForm[field.key] as number ?? 1]}
                  onValueChange={([v]) =>
                    setDiffForm({ ...diffForm, [field.key]: v })
                  }
                />
                <p className="text-xs text-muted-foreground">{field.description}</p>
              </div>
            ))}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-sm">Shade Exposure</Label>
                <Select
                  value={diffForm.shade_exposure ?? ""}
                  onValueChange={(v) => setDiffForm({ ...diffForm, shade_exposure: v || null })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full_sun">Full Sun</SelectItem>
                    <SelectItem value="partial_shade">Partial Shade</SelectItem>
                    <SelectItem value="full_shade">Full Shade</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm">Tree Debris</Label>
                <Select
                  value={diffForm.tree_debris_level ?? ""}
                  onValueChange={(v) => setDiffForm({ ...diffForm, tree_debris_level: v || null })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="moderate">Moderate</SelectItem>
                    <SelectItem value="heavy">Heavy</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-sm">Equipment Age (years)</Label>
              <Input
                type="number"
                className="max-w-[120px]"
                value={diffForm.equipment_age_years ?? ""}
                onChange={(e) =>
                  setDiffForm({
                    ...diffForm,
                    equipment_age_years: e.target.value ? parseInt(e.target.value) : null,
                  })
                }
              />
            </div>

            <Button onClick={handleSaveDifficulty} disabled={saving}>
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Save Difficulty
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
