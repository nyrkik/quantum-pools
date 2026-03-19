"use client";

import type { ReactNode } from "react";
import { usePermissions, type FeatureSlug } from "@/lib/permissions";
import { UpgradePrompt } from "./upgrade-prompt";

interface FeatureGateProps {
  feature: FeatureSlug;
  children: ReactNode;
  fallback?: ReactNode;
}

export function FeatureGate({ feature, children, fallback }: FeatureGateProps) {
  const { hasFeature } = usePermissions();

  if (hasFeature(feature)) {
    return <>{children}</>;
  }

  return <>{fallback ?? <UpgradePrompt feature={feature} />}</>;
}
