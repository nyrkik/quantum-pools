"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Loader2, Save } from "lucide-react";
import type { WfCost, PropertyDifficulty, PropertyDifficultyUpdate } from "@/types/profitability";

interface PropertyFactorsCardProps {
  difficultyScore: number;
  difficultyMultiplier: number;
  wfCosts: WfCost[];
  difficulty: PropertyDifficulty | null;
  diffForm: PropertyDifficultyUpdate;
  onDiffFormChange: (form: PropertyDifficultyUpdate) => void;
  onSave: () => void;
  saving: boolean;
}

export function PropertyFactorsCard({
  difficultyScore,
  difficultyMultiplier,
  wfCosts,
  difficulty,
  diffForm,
  onDiffFormChange,
  onSave,
  saving,
}: PropertyFactorsCardProps) {
  const scoreFields = [
    { key: "customer_demands_score" as const, label: "Client Demands", description: "Frequent calls, complaints, callbacks, special requests" },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Property Factors</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg">
          <div>
            <p className="text-xs text-muted-foreground">Difficulty Index</p>
            <p className="text-3xl font-bold">{difficultyScore.toFixed(1)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Multiplier</p>
            <p className="text-lg font-semibold">{difficultyMultiplier.toFixed(2)}x</p>
          </div>
        </div>

        {wfCosts.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Water Feature Difficulty</p>
            {wfCosts.map((bc) => {
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
                onDiffFormChange({ ...diffForm, [field.key]: v })
              }
            />
            <p className="text-xs text-muted-foreground">{field.description}</p>
          </div>
        ))}

        {difficulty && diffForm.customer_demands_score !== difficulty.customer_demands_score && (
          <Button onClick={onSave} disabled={saving}>
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
  );
}
