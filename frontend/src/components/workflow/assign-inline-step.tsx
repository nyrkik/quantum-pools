"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { events } from "@/lib/events";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { AssignInlineInitial, StepComponentProps } from "./types";

export function AssignInlineStep({
  initial,
  onDone,
}: StepComponentProps<AssignInlineInitial>) {
  const [userId, setUserId] = useState<string>(initial.default_assignee_id ?? "");
  const [saving, setSaving] = useState(false);

  const pickedOption = initial.assignee_options.find((o) => o.id === userId);

  const handleSave = async () => {
    if (!pickedOption) {
      toast.error("Pick who takes this job");
      return;
    }
    setSaving(true);
    try {
      await api.put(`/v1/admin/agent-actions/${initial.entity_id}`, {
        assigned_to: pickedOption.first_name,
      });
      events.emit("handler.applied", {
        level: "user_action",
        entity_refs: {
          entity_id: initial.entity_id,
          entity_type: initial.entity_type,
          assignee_user_id: pickedOption.id,
        },
        payload: { handler: "assign_inline" },
      });
      toast.success(`Assigned to ${pickedOption.first_name}`);
      onDone();
    } catch {
      toast.error("Failed to assign");
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = () => {
    events.emit("handler.abandoned", {
      level: "user_action",
      entity_refs: {
        entity_id: initial.entity_id,
        entity_type: initial.entity_type,
      },
      payload: { handler: "assign_inline", reason: "skip" },
    });
    onDone();
  };

  return (
    <div className="border rounded-md bg-muted/40 p-3 space-y-2">
      <div className="text-xs font-medium text-muted-foreground">
        Who takes this job?
      </div>
      <div className="flex items-center gap-2">
        <Select value={userId} onValueChange={setUserId}>
          <SelectTrigger className="h-9 flex-1">
            <SelectValue placeholder="Pick a person" />
          </SelectTrigger>
          <SelectContent>
            {initial.assignee_options.map((o) => (
              <SelectItem key={o.id} value={o.id}>
                {o.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          size="sm"
          onClick={handleSave}
          disabled={!pickedOption || saving}
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={handleSkip}
          disabled={saving}
        >
          Skip
        </Button>
      </div>
    </div>
  );
}
