"use client";

import { Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { FeatureSlug } from "@/lib/permissions";

const FEATURE_NAMES: Record<FeatureSlug, string> = {
  core_operations: "Core Operations",
  route_optimization: "Route Optimization",
  invoicing: "Invoicing & Billing",
  profitability: "Profitability Analysis",
  satellite_analysis: "Satellite Analysis",
  emd_intelligence: "EMD Inspection Intel",
  chemical_costs: "Chemical Cost Engine",
  customer_portal: "Customer Portal",
};

interface UpgradePromptProps {
  feature: FeatureSlug;
}

export function UpgradePrompt({ feature }: UpgradePromptProps) {
  const name = FEATURE_NAMES[feature] ?? feature;

  return (
    <Card className="shadow-sm">
      <CardContent className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-muted p-4 mb-4">
          <Lock className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold mb-2">{name}</h3>
        <p className="text-sm text-muted-foreground max-w-md">
          This feature is not included in your current subscription.
          Contact your account owner to add {name} to your plan.
        </p>
      </CardContent>
    </Card>
  );
}
