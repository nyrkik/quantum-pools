"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { FeatureSettingsSheet } from "@/components/ui/feature-settings-sheet";
import { InboxRoutingSection } from "@/components/settings/inbox-routing-section";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

interface InboxSettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InboxSettingsSheet({ open, onOpenChange }: InboxSettingsSheetProps) {
  const [learningMode, setLearningMode] = useState(true);
  const [loadingLearning, setLoadingLearning] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get<{ email_contact_learning: boolean }>("/v1/admin/contact-learning")
      .then((d) => setLearningMode(d.email_contact_learning))
      .catch(() => {});
  }, [open]);

  const toggleLearning = async (enabled: boolean) => {
    setLoadingLearning(true);
    try {
      await api.put("/v1/admin/contact-learning", { enabled });
      setLearningMode(enabled);
      toast.success(enabled ? "Contact learning enabled" : "Contact learning disabled");
    } catch {
      toast.error("Failed to update setting");
    } finally {
      setLoadingLearning(false);
    }
  };

  return (
    <FeatureSettingsSheet
      title="Inbox Settings"
      description="Route emails to team members or block automated senders."
      open={open}
      onOpenChange={onOpenChange}
    >
      {/* Contact Learning Toggle */}
      <div className="flex items-center justify-between py-3 border-b mb-4">
        <div className="space-y-0.5">
          <Label className="text-sm font-medium">Contact Learning Mode</Label>
          <p className="text-xs text-muted-foreground">
            {learningMode
              ? "Modal appears when viewing emails from unknown senders"
              : "Subtle banner shown instead — click to add contacts"}
          </p>
        </div>
        <Switch
          checked={learningMode}
          onCheckedChange={toggleLearning}
          disabled={loadingLearning}
        />
      </div>

      <InboxRoutingSection editMode={true} />
    </FeatureSettingsSheet>
  );
}
