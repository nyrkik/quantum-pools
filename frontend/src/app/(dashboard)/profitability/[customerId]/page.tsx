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
import { Loader2, ArrowLeft, Save, Pencil, X, Check } from "lucide-react";
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

import { formatCurrency } from "@/lib/format";

interface WfCost {
  wf_id: string;
  wf_name: string | null;
  water_type: string;
  gallons: number;
  service_minutes: number;
  monthly_rate: number;
  chemical_cost: number;
  labor_cost: number;
  travel_cost: number;
  overhead_cost: number;
  total_cost: number;
  profit: number;
  margin_pct: number;
  suggested_rate: number;
  rate_gap: number;
}

interface WfDifficulty {
  access_difficulty: number;
  chemical_demand: number;
  equipment_effectiveness: number;
  pool_design: number;
  shade_exposure: number;
  tree_debris: number;
}

function WfCostCard({ bc, onSaved }: { bc: WfCost; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [gallons, setGallons] = useState(bc.gallons);
  const [minutes, setMinutes] = useState(bc.service_minutes);
  const [rate, setRate] = useState(bc.monthly_rate);
  const [diff, setDiff] = useState<WfDifficulty | null>(null);

  useEffect(() => {
    if (editing && !diff) {
      api.get<WfDifficulty>(`/v1/water-features/${bc.wf_id}`)
        .then((wf) => setDiff({
          access_difficulty: wf.access_difficulty ?? 1,
          chemical_demand: wf.chemical_demand ?? 1,
          equipment_effectiveness: wf.equipment_effectiveness ?? 3,
          pool_design: wf.pool_design ?? 3,
          shade_exposure: wf.shade_exposure ?? 1,
          tree_debris: wf.tree_debris ?? 1,
        }))
        .catch(() => setDiff({ access_difficulty: 1, chemical_demand: 1, equipment_effectiveness: 3, pool_design: 3, shade_exposure: 1, tree_debris: 1 }));
    }
  }, [editing, diff, bc.wf_id]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/v1/water-features/${bc.wf_id}`, {
        pool_gallons: gallons,
        estimated_service_minutes: minutes,
        monthly_rate: rate,
        ...(diff || {}),
      });
      toast.success("Updated");
      setEditing(false);
      onSaved();
    } catch {
      toast.error("Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setGallons(bc.gallons);
    setMinutes(bc.service_minutes);
    setRate(bc.monthly_rate);
    setEditing(false);
  };

  return (
    <div className={`rounded-lg border px-4 py-3 transition-colors ${editing ? "border-l-4 border-l-primary bg-muted/30" : "hover:bg-muted/30 cursor-pointer"}`}
      onClick={!editing ? () => setEditing(true) : undefined}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold capitalize">{bc.wf_name || bc.water_type}</span>
          {!editing && (
            <span className="text-xs text-muted-foreground">{bc.gallons.toLocaleString()} gal · {bc.service_minutes} min</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!editing ? (
            <span className="text-sm text-muted-foreground">{formatCurrency(bc.monthly_rate)}/mo</span>
          ) : (
            <>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-green-600" onClick={(e) => { e.stopPropagation(); handleSave(); }}>
                  <Check className="h-4 w-4" />
                </Button>
              )}
              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={(e) => { e.stopPropagation(); handleCancel(); }}>
                <X className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>

      {editing && (
        <div className="space-y-3 mb-2" onClick={(e) => e.stopPropagation()}>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Gallons</Label>
              <Input type="number" value={gallons} onChange={(e) => setGallons(parseInt(e.target.value) || 0)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Service Minutes</Label>
              <Input type="number" value={minutes} onChange={(e) => setMinutes(parseInt(e.target.value) || 0)} className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Monthly Rate</Label>
              <Input type="number" step="0.01" value={rate} onChange={(e) => setRate(parseFloat(e.target.value) || 0)} className="h-8 text-sm" />
            </div>
          </div>
          {diff && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {([
                { key: "access_difficulty" as const, label: "Access", desc: "1=easy, 5=difficult" },
                { key: "chemical_demand" as const, label: "Chem Demand", desc: "1=stable, 5=chronic issues" },
                { key: "equipment_effectiveness" as const, label: "Equipment", desc: "1=poor, 5=excellent" },
                { key: "pool_design" as const, label: "Design/Flow", desc: "1=poor, 5=great" },
                { key: "shade_exposure" as const, label: "Shade", desc: "1=full sun, 5=full shade" },
                { key: "tree_debris" as const, label: "Tree Debris", desc: "1=none, 5=heavy" },
              ]).map((f) => (
                <div key={f.key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">{f.label}</Label>
                    <span className="text-xs font-medium">{diff[f.key].toFixed(1)}</span>
                  </div>
                  <Slider min={1} max={5} step={0.5} value={[diff[f.key]]} onValueChange={([v]) => setDiff({ ...diff, [f.key]: v })} />
                  <p className="text-[10px] text-muted-foreground">{f.desc}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-4 gap-2 text-xs">
        {[
          { label: "Chemical", value: bc.chemical_cost },
          { label: "Labor", value: bc.labor_cost },
          { label: "Travel", value: bc.travel_cost },
          { label: "Overhead", value: bc.overhead_cost },
        ].map((item) => (
          <div key={item.label} className="text-center">
            <p className="text-muted-foreground">{item.label}</p>
            <p className="font-medium">{formatCurrency(item.value)}</p>
          </div>
        ))}
      </div>
    </div>
  );
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
          customer_demands_score: diff.customer_demands_score,
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
    { key: "customer_demands_score", label: "Client Demands", description: "Frequent calls, complaints, callbacks, special requests" },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/profitability">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{account.customer_name}</h1>
          <p className="text-muted-foreground">{account.property_address}</p>
        </div>
        <Link href={`/customers/${account.customer_id}?tab=wfs`}>
          <Button variant="outline" size="sm">Water Features</Button>
        </Link>
      </div>

      {/* Rate comparison */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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

        {/* Property Factors + Difficulty Index */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Property Factors</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Difficulty index */}
            <div className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg">
              <div>
                <p className="text-xs text-muted-foreground">Difficulty Index</p>
                <p className="text-3xl font-bold">{account.difficulty_score.toFixed(1)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Multiplier</p>
                <p className="text-lg font-semibold">{account.difficulty_multiplier.toFixed(2)}x</p>
              </div>
            </div>

            {/* Per-WF difficulty summary */}
            {account.wf_costs && account.wf_costs.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Water Feature Difficulty</p>
                {account.wf_costs.map((bc) => {
                  const score = bc.difficulty_score;
                  const pct = ((score - 1) / 4) * 100;
                  return (
                    <div key={bc.wf_id} className="flex items-center gap-2 text-xs">
                      <span className="w-28 truncate capitalize font-medium">{bc.wf_name || bc.water_type}</span>
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${score >= 3.5 ? "bg-red-400" : score >= 2.5 ? "bg-amber-400" : "bg-green-400"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-7 text-right text-muted-foreground">{score.toFixed(1)}</span>
                    </div>
                  );
                })}
              </div>
            )}

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

            {difficulty && diffForm.customer_demands_score !== difficulty.customer_demands_score && (
              <Button onClick={handleSaveDifficulty} disabled={saving}>
                {saving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Per-WF Breakdown */}
      {account.wf_costs && account.wf_costs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Per Water Feature Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {account.wf_costs.map((bc) => (
                <WfCostCard key={bc.wf_id} bc={bc} onSaved={loadData} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
