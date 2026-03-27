"use client";

import { FeatureSettingsSheet } from "@/components/ui/feature-settings-sheet";
import { VendorsSection } from "@/components/settings/vendors-section";

interface VendorSettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function VendorSettingsSheet({ open, onOpenChange }: VendorSettingsSheetProps) {
  return (
    <FeatureSettingsSheet
      title="Vendor Settings"
      description="Configure your parts suppliers and search portals."
      open={open}
      onOpenChange={onOpenChange}
    >
      <VendorsSection editMode={true} />
    </FeatureSettingsSheet>
  );
}
