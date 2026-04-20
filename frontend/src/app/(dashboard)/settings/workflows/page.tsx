"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Lock } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface WorkflowConfig {
  post_creation_handlers: Record<string, string>;
  default_assignee_strategy: {
    strategy: string;
    fallback_user_id?: string | null;
  };
}

type JobHandler = "schedule_inline" | "assign_inline" | "unassigned_pool";
type StrategyKind = "always_ask" | "last_used_in_org" | "fixed";

const JOB_HANDLER_OPTIONS: Array<{
  value: JobHandler;
  title: string;
  blurb: string;
}> = [
  {
    value: "schedule_inline",
    title: "Schedule right away",
    blurb:
      "Best for coordinator-driven teams. Pick a date and assignee before the job enters the schedule.",
  },
  {
    value: "assign_inline",
    title: "Create and assign",
    blurb:
      "Best for flexible schedules. The job lands immediately; you just pick who takes it.",
  },
  {
    value: "unassigned_pool",
    title: "Send to unassigned pool",
    blurb:
      "Best for dispatch-style teams. The job waits in a queue your dispatcher picks from.",
  },
];

const STRATEGY_OPTIONS: Array<{
  value: StrategyKind;
  title: string;
  blurb: string;
}> = [
  {
    value: "always_ask",
    title: "Always ask (no default)",
    blurb: "The picker opens empty every time.",
  },
  {
    value: "last_used_in_org",
    title: "Remember who we last assigned",
    blurb:
      "Pre-selects whoever took the most recent job in your org. Change it each time if you need to.",
  },
  {
    value: "fixed",
    title: "Default to a specific person",
    blurb: "Always pre-select the same person. You can still change it before saving.",
  },
];

function equalConfig(a: WorkflowConfig, b: WorkflowConfig): boolean {
  if (a.post_creation_handlers.job !== b.post_creation_handlers.job) return false;
  if (a.default_assignee_strategy.strategy !== b.default_assignee_strategy.strategy)
    return false;
  const af = a.default_assignee_strategy.fallback_user_id ?? null;
  const bf = b.default_assignee_strategy.fallback_user_id ?? null;
  return af === bf;
}

export default function WorkflowSettingsPage() {
  const { can } = usePermissions();
  const canEdit = can("workflow.manage_config");
  const team = useTeamMembersFull();

  const [original, setOriginal] = useState<WorkflowConfig | null>(null);
  const [form, setForm] = useState<WorkflowConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<WorkflowConfig>("/v1/workflow/config");
      const normalized: WorkflowConfig = {
        post_creation_handlers: { job: "assign_inline", ...data.post_creation_handlers },
        default_assignee_strategy: {
          strategy: data.default_assignee_strategy?.strategy ?? "last_used_in_org",
          fallback_user_id: data.default_assignee_strategy?.fallback_user_id ?? null,
        },
      };
      setOriginal(normalized);
      setForm(normalized);
    } catch {
      toast.error("Failed to load workflow settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const isDirty = useMemo(() => {
    if (!form || !original) return false;
    return !equalConfig(form, original);
  }, [form, original]);

  const handleSave = async () => {
    if (!form) return;
    // If "fixed" is selected but no user picked yet, block save.
    if (
      form.default_assignee_strategy.strategy === "fixed" &&
      !form.default_assignee_strategy.fallback_user_id
    ) {
      toast.error("Pick a person for the default");
      return;
    }
    setSaving(true);
    try {
      await api.put<WorkflowConfig>("/v1/workflow/config", {
        post_creation_handlers: form.post_creation_handlers,
        default_assignee_strategy: form.default_assignee_strategy,
      });
      toast.success("Workflow settings saved");
      await load();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (original) setForm(original);
  };

  const selectedHandler = (form?.post_creation_handlers.job ?? "assign_inline") as JobHandler;
  const selectedStrategy = (form?.default_assignee_strategy.strategy ??
    "last_used_in_org") as StrategyKind;

  return (
    <PageLayout
      title="Workflows"
      subtitle="How new jobs get handled after they're created"
    >
      {loading || !form ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-6 max-w-3xl">
          {!canEdit && (
            <Card className="shadow-sm bg-muted/50">
              <CardContent className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
                <Lock className="h-3.5 w-3.5" />
                You can view these settings but not change them. Ask an owner or admin.
              </CardContent>
            </Card>
          )}

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">How new jobs get handled</h2>
            <div className="space-y-2">
              {JOB_HANDLER_OPTIONS.map((opt) => {
                const selected = selectedHandler === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    disabled={!canEdit}
                    onClick={() =>
                      setForm({
                        ...form,
                        post_creation_handlers: {
                          ...form.post_creation_handlers,
                          job: opt.value,
                        },
                      })
                    }
                    className={
                      "w-full text-left rounded-lg border p-4 transition-colors " +
                      (selected
                        ? "border-primary bg-primary/5 ring-1 ring-primary"
                        : "hover:border-muted-foreground/40") +
                      (canEdit ? " cursor-pointer" : " cursor-not-allowed opacity-80")
                    }
                  >
                    <div className="flex items-start gap-3">
                      <span
                        className={
                          "mt-1 h-3.5 w-3.5 rounded-full border shrink-0 " +
                          (selected
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/50")
                        }
                      />
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{opt.title}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {opt.blurb}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Default assignee</h2>
            <div className="space-y-2">
              {STRATEGY_OPTIONS.map((opt) => {
                const selected = selectedStrategy === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    disabled={!canEdit}
                    onClick={() =>
                      setForm({
                        ...form,
                        default_assignee_strategy: {
                          strategy: opt.value,
                          fallback_user_id:
                            opt.value === "fixed"
                              ? form.default_assignee_strategy.fallback_user_id ?? null
                              : null,
                        },
                      })
                    }
                    className={
                      "w-full text-left rounded-lg border p-4 transition-colors " +
                      (selected
                        ? "border-primary bg-primary/5 ring-1 ring-primary"
                        : "hover:border-muted-foreground/40") +
                      (canEdit ? " cursor-pointer" : " cursor-not-allowed opacity-80")
                    }
                  >
                    <div className="flex items-start gap-3">
                      <span
                        className={
                          "mt-1 h-3.5 w-3.5 rounded-full border shrink-0 " +
                          (selected
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/50")
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium">{opt.title}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {opt.blurb}
                        </div>
                        {opt.value === "fixed" && selected && (
                          <div
                            className="mt-3"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Select
                              disabled={!canEdit}
                              value={
                                form.default_assignee_strategy.fallback_user_id ?? ""
                              }
                              onValueChange={(v) =>
                                setForm({
                                  ...form,
                                  default_assignee_strategy: {
                                    strategy: "fixed",
                                    fallback_user_id: v || null,
                                  },
                                })
                              }
                            >
                              <SelectTrigger className="h-9 max-w-xs">
                                <SelectValue placeholder="Choose a person" />
                              </SelectTrigger>
                              <SelectContent>
                                {team.map((m) => (
                                  <SelectItem key={m.user_id} value={m.user_id}>
                                    {[m.first_name, m.last_name]
                                      .filter(Boolean)
                                      .join(" ") || m.first_name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          {canEdit && isDirty && (
            <div className="flex gap-2">
              <Button onClick={handleSave} disabled={saving} size="sm">
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
                Save
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCancel}
                disabled={saving}
              >
                Cancel
              </Button>
            </div>
          )}
        </div>
      )}
    </PageLayout>
  );
}
