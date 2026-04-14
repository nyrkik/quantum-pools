"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plug, Settings2 } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { FeatureSettingsSheet } from "@/components/ui/feature-settings-sheet";
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
      description="Tune how inbound email is routed, tagged, and displayed."
      open={open}
      onOpenChange={onOpenChange}
    >
      <div className="flex items-center justify-between py-3 border-b">
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

      <div className="flex items-center justify-between py-3 border-b">
        <div className="space-y-0.5">
          <Label className="text-sm font-medium">Inbox Rules</Label>
          <p className="text-xs text-muted-foreground">
            Route, tag, and mark-as-read inbound email by sender or recipient.
          </p>
        </div>
        <Button asChild variant="outline" size="sm" onClick={() => onOpenChange(false)}>
          <Link href="/inbox/rules">
            <Settings2 className="h-3.5 w-3.5 mr-1.5" />
            Manage rules
          </Link>
        </Button>
      </div>

      <div className="flex items-center justify-between py-3 border-b">
        <div className="space-y-0.5">
          <Label className="text-sm font-medium">Email Integrations</Label>
          <p className="text-xs text-muted-foreground">
            Connect Gmail or another mailbox so QP can send and receive customer email.
          </p>
        </div>
        <Button asChild variant="outline" size="sm" onClick={() => onOpenChange(false)}>
          <Link href="/inbox/integrations">
            <Plug className="h-3.5 w-3.5 mr-1.5" />
            Manage
          </Link>
        </Button>
      </div>
    </FeatureSettingsSheet>
  );
}
