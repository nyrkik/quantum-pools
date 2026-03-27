"use client";

import { FeatureSettingsSheet } from "@/components/ui/feature-settings-sheet";
import { InboxRoutingSection } from "@/components/settings/inbox-routing-section";

interface InboxSettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InboxSettingsSheet({ open, onOpenChange }: InboxSettingsSheetProps) {
  return (
    <FeatureSettingsSheet
      title="Inbox Settings"
      description="Route emails to team members or block automated senders."
      open={open}
      onOpenChange={onOpenChange}
    >
      <InboxRoutingSection editMode={true} />
    </FeatureSettingsSheet>
  );
}
