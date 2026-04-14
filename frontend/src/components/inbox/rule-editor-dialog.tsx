"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Trash2 } from "lucide-react";

export type ConditionField =
  | "sender_email"
  | "sender_domain"
  | "recipient_email"
  | "subject"
  | "category"
  | "customer_id"
  | "body";
export type ConditionOperator =
  | "equals"
  | "contains"
  | "starts_with"
  | "ends_with"
  | "matches";
export type ActionType =
  | "assign_folder"
  | "assign_tag"
  | "assign_category"
  | "set_visibility"
  | "suppress_contact_prompt"
  | "route_to_spam"
  | "mark_as_read";

export interface RuleCondition {
  field: ConditionField;
  operator: ConditionOperator;
  value: string;
}

export interface RuleAction {
  type: ActionType;
  params?: Record<string, string>;
}

export interface RuleDraft {
  id?: string;
  name: string;
  priority: number;
  conditions: RuleCondition[];
  actions: RuleAction[];
  is_active: boolean;
}

interface InboxFolder {
  id: string;
  name: string;
}

interface RuleEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialDraft: RuleDraft;
  folders: InboxFolder[];
  onSave: (draft: RuleDraft) => Promise<void>;
}

const FIELD_OPTIONS: { value: ConditionField; label: string }[] = [
  { value: "sender_email", label: "Sender email" },
  { value: "sender_domain", label: "Sender domain" },
  { value: "recipient_email", label: "Recipient email" },
  { value: "subject", label: "Subject" },
  { value: "body", label: "Body" },
  { value: "category", label: "AI category" },
  { value: "customer_id", label: "Matched customer" },
];

const OPERATOR_OPTIONS: { value: ConditionOperator; label: string }[] = [
  { value: "equals", label: "equals" },
  { value: "contains", label: "contains" },
  { value: "starts_with", label: "starts with" },
  { value: "ends_with", label: "ends with" },
  { value: "matches", label: "matches (glob *)" },
];

const ACTION_OPTIONS: { value: ActionType; label: string; needs: string[] }[] = [
  { value: "assign_folder", label: "Move to folder", needs: ["folder_id"] },
  { value: "assign_tag", label: "Tag sender", needs: ["tag"] },
  { value: "assign_category", label: "Set category", needs: ["category"] },
  { value: "set_visibility", label: "Restrict visibility", needs: ["permission_slug"] },
  { value: "route_to_spam", label: "Route to Spam folder", needs: [] },
  { value: "mark_as_read", label: "Mark as read (don't inflate unread count)", needs: [] },
  { value: "suppress_contact_prompt", label: "Suppress Add-Contact prompt", needs: [] },
];

const TAG_OPTIONS = [
  "billing",
  "vendor",
  "notification",
  "personal",
  "automated",
  "other",
];

export function RuleEditorDialog({
  open,
  onOpenChange,
  initialDraft,
  folders,
  onSave,
}: RuleEditorDialogProps) {
  const [draft, setDraft] = useState<RuleDraft>(initialDraft);
  const [saving, setSaving] = useState(false);
  const wasOpen = useRef(false);

  // Only snapshot initialDraft on the closed→open transition. While the
  // dialog is open we preserve user edits even if the parent re-renders
  // and passes a fresh initialDraft reference.
  useEffect(() => {
    if (open && !wasOpen.current) {
      setDraft(initialDraft);
    }
    wasOpen.current = open;
  }, [open, initialDraft]);

  const updateCondition = (idx: number, patch: Partial<RuleCondition>) => {
    setDraft((d) => ({
      ...d,
      conditions: d.conditions.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    }));
  };

  const updateAction = (idx: number, patch: Partial<RuleAction>) => {
    setDraft((d) => ({
      ...d,
      actions: d.actions.map((a, i) => (i === idx ? { ...a, ...patch } : a)),
    }));
  };

  const handleSave = async () => {
    if (draft.actions.length === 0) return;
    setSaving(true);
    try {
      await onSave(draft);
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  const isEditing = Boolean(initialDraft.id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Edit rule" : "New inbox rule"}</DialogTitle>
          <DialogDescription>
            Every condition must match for the rule to fire. Reorder rules
            later by dragging them in the list.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div>
            <Label htmlFor="rule-name">Name</Label>
            <Input
              id="rule-name"
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
              placeholder="e.g. Stripe billing → Billing folder"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Conditions (ALL must match)</Label>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setDraft((d) => ({
                    ...d,
                    conditions: [
                      ...d.conditions,
                      { field: "sender_email", operator: "equals", value: "" },
                    ],
                  }))
                }
              >
                + Add condition
              </Button>
            </div>
            {draft.conditions.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No conditions — rule will match every message.
              </p>
            )}
            {draft.conditions.map((c, idx) => (
              <div
                key={idx}
                className="rounded-md border bg-muted/30 p-2 space-y-2"
              >
                <div className="flex items-center gap-2">
                  <Select
                    value={c.field}
                    onValueChange={(v) =>
                      updateCondition(idx, { field: v as ConditionField })
                    }
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FIELD_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={c.operator}
                    onValueChange={(v) =>
                      updateCondition(idx, { operator: v as ConditionOperator })
                    }
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {OPERATOR_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() =>
                      setDraft((d) => ({
                        ...d,
                        conditions: d.conditions.filter((_, i) => i !== idx),
                      }))
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <Input
                  value={c.value}
                  onChange={(e) =>
                    updateCondition(idx, { value: e.target.value })
                  }
                  placeholder="value (e.g. billing@acme.com or *@acme.com)"
                />
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Actions (applied in order)</Label>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setDraft((d) => ({
                    ...d,
                    actions: [...d.actions, { type: "assign_folder", params: {} }],
                  }))
                }
              >
                + Add action
              </Button>
            </div>
            {draft.actions.length === 0 && (
              <p className="text-xs text-destructive">
                A rule needs at least one action.
              </p>
            )}
            {draft.actions.map((a, idx) => {
              const opt = ACTION_OPTIONS.find((o) => o.value === a.type);
              return (
                <div key={idx} className="flex items-center gap-2">
                  <Select
                    value={a.type}
                    onValueChange={(v) =>
                      updateAction(idx, { type: v as ActionType, params: {} })
                    }
                  >
                    <SelectTrigger className="w-52">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ACTION_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {opt?.needs.includes("folder_id") && (
                    <Select
                      value={a.params?.folder_id || ""}
                      onValueChange={(v) =>
                        updateAction(idx, { params: { ...a.params, folder_id: v } })
                      }
                    >
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder="Pick folder..." />
                      </SelectTrigger>
                      <SelectContent>
                        {folders.map((f) => (
                          <SelectItem key={f.id} value={f.id}>
                            {f.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}

                  {opt?.needs.includes("tag") && (
                    <Select
                      value={a.params?.tag || ""}
                      onValueChange={(v) =>
                        updateAction(idx, { params: { ...a.params, tag: v } })
                      }
                    >
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder="Pick tag..." />
                      </SelectTrigger>
                      <SelectContent>
                        {TAG_OPTIONS.map((t) => (
                          <SelectItem key={t} value={t}>
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}

                  {opt?.needs.includes("category") && (
                    <Input
                      value={a.params?.category || ""}
                      onChange={(e) =>
                        updateAction(idx, {
                          params: { ...a.params, category: e.target.value },
                        })
                      }
                      placeholder="category (e.g. billing)"
                      className="flex-1"
                    />
                  )}

                  {opt?.needs.includes("permission_slug") && (
                    <Input
                      value={a.params?.permission_slug || ""}
                      onChange={(e) =>
                        updateAction(idx, {
                          params: { ...a.params, permission_slug: e.target.value },
                        })
                      }
                      placeholder="permission slug"
                      className="flex-1"
                    />
                  )}

                  {opt && opt.needs.length === 0 && <div className="flex-1" />}

                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() =>
                      setDraft((d) => ({
                        ...d,
                        actions: d.actions.filter((_, i) => i !== idx),
                      }))
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              );
            })}
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || draft.actions.length === 0}
          >
            {saving ? "Saving…" : isEditing ? "Save" : "Create rule"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
