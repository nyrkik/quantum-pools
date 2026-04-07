"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { toast } from "sonner";
import { Loader2, ArrowLeft } from "lucide-react";
import type {
  ProfitabilityAccount,
  PropertyDifficulty,
  PropertyDifficultyUpdate,
} from "@/types/profitability";

import { formatCurrency } from "@/lib/format";
import { CostWaterfallChart } from "@/components/profitability/cost-waterfall-chart";
import { PropertyFactorsCard } from "@/components/profitability/property-factors-card";
import { WfCostCard } from "@/components/profitability/wf-cost-card";

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
            <div className={`text-2xl font-bold ${account.cost_breakdown.rate_gap > 0 ? "text-yellow-600" : "text-green-600"}`}>
              {formatCurrency(account.cost_breakdown.suggested_rate)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Margin</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${account.cost_breakdown.margin_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
              {account.cost_breakdown.margin_pct.toFixed(1)}%
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CostWaterfallChart costBreakdown={account.cost_breakdown} />

        <PropertyFactorsCard
          difficultyScore={account.difficulty_score}
          difficultyMultiplier={account.difficulty_multiplier}
          wfCosts={account.wf_costs || []}
          difficulty={difficulty}
          diffForm={diffForm}
          onDiffFormChange={setDiffForm}
          onSave={handleSaveDifficulty}
          saving={saving}
        />
      </div>

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
