"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { toast } from "sonner";
import { Loader2, X, Check } from "lucide-react";
import { formatCurrency } from "@/lib/format";
import type { WfCost } from "@/types/profitability";

interface WfDifficulty {
  access_difficulty: number;
  chemical_demand: number;
  equipment_effectiveness: number;
  pool_design: number;
  shade_exposure: number;
  tree_debris: number;
}

interface WfCostCardProps {
  bc: WfCost;
  onSaved: () => void;
}

export function WfCostCard({ bc, onSaved }: WfCostCardProps) {
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

  const difficultyFields = [
    { key: "access_difficulty" as const, label: "Access", desc: "1=easy, 5=difficult" },
    { key: "chemical_demand" as const, label: "Chem Demand", desc: "1=stable, 5=chronic issues" },
    { key: "equipment_effectiveness" as const, label: "Equipment", desc: "1=poor, 5=excellent" },
    { key: "pool_design" as const, label: "Design/Flow", desc: "1=poor, 5=great" },
    { key: "shade_exposure" as const, label: "Shade", desc: "1=full sun, 5=full shade" },
    { key: "tree_debris" as const, label: "Tree Debris", desc: "1=none, 5=heavy" },
  ];

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
              {difficultyFields.map((f) => (
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
