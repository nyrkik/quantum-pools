"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { toast } from "sonner";
import { Save, Loader2 } from "lucide-react";
import type { OrgCostSettings, OrgCostSettingsUpdate } from "@/types/profitability";

export default function ProfitabilitySettingsPage() {
  const [settings, setSettings] = useState<OrgCostSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<OrgCostSettingsUpdate>({});

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    try {
      const data = await api.get<OrgCostSettings>("/v1/profitability/settings");
      setSettings(data);
      setForm({
        burdened_labor_rate: data.burdened_labor_rate,
        vehicle_cost_per_mile: data.vehicle_cost_per_mile,
        chemical_cost_per_gallon: data.chemical_cost_per_gallon,
        monthly_overhead: data.monthly_overhead,
        target_margin_pct: data.target_margin_pct,
      });
    } catch {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const data = await api.put<OrgCostSettings>("/v1/profitability/settings", form);
      setSettings(data);
      toast.success("Settings saved");
    } catch {
      toast.error("Failed to save settings");
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

  const fields = [
    {
      key: "burdened_labor_rate" as const,
      label: "Burdened Labor Rate",
      prefix: "$",
      suffix: "/hour",
      description: "Fully loaded cost per hour (wages + taxes + benefits + insurance)",
    },
    {
      key: "vehicle_cost_per_mile" as const,
      label: "Vehicle Cost per Mile",
      prefix: "$",
      suffix: "/mile",
      description: "IRS standard mileage rate or your actual cost",
    },
    {
      key: "chemical_cost_per_gallon" as const,
      label: "Chemical Cost per 10k Gallons",
      prefix: "$",
      suffix: "/visit",
      description: "Average chemical cost per visit per 10,000 gallons of pool water",
    },
    {
      key: "monthly_overhead" as const,
      label: "Monthly Overhead",
      prefix: "$",
      suffix: "/month",
      description: "Office, insurance, software, phone — split across all accounts",
    },
    {
      key: "target_margin_pct" as const,
      label: "Target Profit Margin",
      prefix: "",
      suffix: "%",
      description: "Accounts below this margin will be flagged for price adjustment",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Profitability Settings</h1>
        <p className="text-muted-foreground">
          Configure cost assumptions for profitability analysis
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Cost Configuration</CardTitle>
          <CardDescription>
            These values drive all profitability calculations. Start with
            estimates — refine as you gather real data.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {fields.map((field) => (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={field.key}>{field.label}</Label>
              <div className="flex items-center gap-2">
                {field.prefix && (
                  <span className="text-sm text-muted-foreground">{field.prefix}</span>
                )}
                <Input
                  id={field.key}
                  type="number"
                  step="0.01"
                  className="max-w-[200px]"
                  value={form[field.key] ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, [field.key]: parseFloat(e.target.value) || 0 })
                  }
                />
                {field.suffix && (
                  <span className="text-sm text-muted-foreground">{field.suffix}</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">{field.description}</p>
            </div>
          ))}

          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Save Settings
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
