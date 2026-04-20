"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { events } from "@/lib/events";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { ScheduleInlineInitial, StepComponentProps } from "./types";

function toLocalDatetimeInputValue(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return (
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  } catch {
    return "";
  }
}

export function ScheduleInlineStep({
  initial,
  onDone,
}: StepComponentProps<ScheduleInlineInitial>) {
  const [userId, setUserId] = useState<string>(initial.default_assignee_id ?? "");
  const [dateLocal, setDateLocal] = useState<string>(
    toLocalDatetimeInputValue(initial.default_date),
  );
  const [saving, setSaving] = useState(false);

  const pickedOption = initial.assignee_options.find((o) => o.id === userId);
  const canSave = !!pickedOption && !!dateLocal;

  const handleSave = async () => {
    if (!pickedOption || !dateLocal) {
      toast.error("Pick a date and a person");
      return;
    }
    // <input type="datetime-local"> yields "YYYY-MM-DDTHH:MM" in local
    // time with no zone. Convert to a real Date (which interprets it
    // as local) and send as ISO UTC so the backend stores an instant,
    // not a wall-clock string.
    const dueIso = new Date(dateLocal).toISOString();
    setSaving(true);
    try {
      await api.put(`/v1/admin/agent-actions/${initial.entity_id}`, {
        assigned_to: pickedOption.first_name,
        due_date: dueIso,
      });
      events.emit("handler.applied", {
        level: "user_action",
        entity_refs: {
          entity_id: initial.entity_id,
          entity_type: initial.entity_type,
          assignee_user_id: pickedOption.id,
        },
        payload: { handler: "schedule_inline", input: { due_date: dueIso } },
      });
      toast.success(`Scheduled for ${pickedOption.first_name}`);
      onDone();
    } catch {
      toast.error("Failed to schedule");
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
      payload: { handler: "schedule_inline", reason: "skip" },
    });
    onDone();
  };

  return (
    <div className="border rounded-md bg-muted/40 p-3 space-y-2">
      <div className="text-xs font-medium text-muted-foreground">
        Schedule this job
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input
          type="datetime-local"
          value={dateLocal}
          onChange={(e) => setDateLocal(e.target.value)}
          className="h-9"
        />
        <Select value={userId} onValueChange={setUserId}>
          <SelectTrigger className="h-9">
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
      </div>
      <div className="flex items-center gap-2 justify-end">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={handleSkip}
          disabled={saving}
        >
          Skip
        </Button>
        <Button type="button" size="sm" onClick={handleSave} disabled={!canSave || saving}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
        </Button>
      </div>
    </div>
  );
}
