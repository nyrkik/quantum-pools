"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export type ConditionField =
  | "sender_email"
  | "sender_domain"
  | "recipient_email"
  | "subject"
  | "category"
  | "customer_id"
  | "customer_matched"
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
  | "mark_as_read"
  | "skip_customer_match";

export interface RuleCondition {
  field: ConditionField;
  operator: ConditionOperator;
  // Scalar string (single value) OR string[] (matches if ANY element
  // satisfies the operator). Lets one rule stand in for N per-value rules.
  value: string | string[];
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

export interface PermissionItem {
  slug: string;
  action: string;
  description: string | null;
}

export interface PermissionCatalog {
  resources: Record<string, PermissionItem[]>;
}

interface RuleEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialDraft: RuleDraft;
  folders: InboxFolder[];
  /** Full permission catalog grouped by resource — renders the visibility
   * action's picker. Null until loaded; falls back to free-text input. */
  permissions?: PermissionCatalog | null;
  onSave: (draft: RuleDraft, options: { applyToExisting: boolean }) => Promise<void>;
  /** Called after the editor creates a new folder via the inline prompt,
   * so the parent list can pick it up without refetching. */
  onFolderCreated?: (folder: InboxFolder) => void;
}

const FIELD_OPTIONS: { value: ConditionField; label: string }[] = [
  { value: "sender_email", label: "Sender email" },
  { value: "sender_domain", label: "Sender domain" },
  { value: "recipient_email", label: "Recipient email" },
  { value: "subject", label: "Subject" },
  { value: "body", label: "Body" },
  { value: "category", label: "AI category" },
  { value: "customer_id", label: "Matched customer (specific)" },
  { value: "customer_matched", label: "Sender is a matched customer" },
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
  {
    value: "skip_customer_match",
    label: "Don't auto-match to a past customer (shared/regional sender)",
    needs: [],
  },
];

/**
 * ChipValueInput — scalar-or-list text input for rule condition values.
 *
 * Type + Enter/comma to add a chip. Backspace on empty input removes the
 * last chip. Blur commits any in-progress text. On change, a single value
 * is emitted as a scalar string; multiple values emit as an array (matches
 * when the operator is satisfied by ANY element).
 *
 * Must live at module scope (NOT inline in RuleEditorDialog) — an inline
 * component definition remounts on every parent render, which ate Enter-
 * key commits before shipping this fix.
 */
function ChipValueInput({
  value,
  onChange,
  placeholder,
}: {
  value: string | string[];
  onChange: (next: string | string[]) => void;
  placeholder?: string;
}) {
  const chips = Array.isArray(value) ? value : value ? [value] : [];
  const [draft, setDraft] = useState("");

  const commit = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    const next = [...chips, trimmed];
    onChange(next.length === 1 ? next[0] : next);
    setDraft("");
  };

  const removeChip = (idx: number) => {
    const next = chips.filter((_, i) => i !== idx);
    onChange(next.length === 0 ? "" : next.length === 1 ? next[0] : next);
  };

  return (
    <div className="rounded-md border bg-background w-full min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-1.5 p-2">
        {chips.map((chip, i) => (
          <Badge
            key={i}
            variant="secondary"
            className="gap-1 max-w-full whitespace-normal break-all"
          >
            <span className="min-w-0 break-all">{chip}</span>
            <button
              type="button"
              onClick={() => removeChip(i)}
              className="rounded-sm hover:bg-muted-foreground/20 shrink-0"
              aria-label={`Remove ${chip}`}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <input
          className="flex-1 min-w-[140px] bg-transparent outline-none text-sm py-0.5"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              e.stopPropagation();
              commit();
            } else if (e.key === "Backspace" && !draft && chips.length > 0) {
              e.preventDefault();
              removeChip(chips.length - 1);
            }
          }}
          onBlur={commit}
          placeholder={chips.length === 0 ? placeholder : "Enter or , to add another"}
        />
      </div>
      <div className="border-t bg-muted/30 px-2 py-1 text-[10px] text-muted-foreground">
        {chips.length === 0
          ? "Type a value, then press Enter or comma to add it. Add more for any-of matching."
          : chips.length === 1
            ? "One value — press Enter or comma to add another."
            : `${chips.length} values — matches when the operator is satisfied by any of them.`}
      </div>
    </div>
  );
}

const TAG_OPTIONS = [
  "billing",
  "vendor",
  "notification",
  "personal",
  "automated",
  "other",
];

const NEW_FOLDER_SENTINEL = "__new_folder__";

/**
 * FolderPickerOrCreate — folder <Select> with an inline "+ New folder" option.
 * When the user picks the sentinel, the control flips into an inline naming
 * input; Enter calls POST /v1/inbox-folders, appends to the parent list via
 * `onCreated`, and auto-selects the new folder.
 */
function FolderPickerOrCreate({
  value,
  folders,
  onSelect,
  onCreated,
}: {
  value: string;
  folders: InboxFolder[];
  onSelect: (id: string) => void;
  onCreated: (folder: InboxFolder) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      const created = await api.post<InboxFolder>("/v1/inbox-folders", {
        name: trimmed,
      });
      onCreated(created);
      onSelect(created.id);
      setCreating(false);
      setName("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't create folder");
    } finally {
      setSaving(false);
    }
  };

  if (creating) {
    return (
      <div className="flex flex-1 items-center gap-1 min-w-0">
        <Input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleCreate();
            } else if (e.key === "Escape") {
              setCreating(false);
              setName("");
            }
          }}
          placeholder="New folder name…"
          className="flex-1 min-w-0"
          disabled={saving}
        />
        <Button
          size="sm"
          onClick={handleCreate}
          disabled={saving || !name.trim()}
        >
          Create
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setCreating(false);
            setName("");
          }}
          disabled={saving}
        >
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <Select
      value={value || ""}
      onValueChange={(v) => {
        if (v === NEW_FOLDER_SENTINEL) {
          setCreating(true);
        } else {
          onSelect(v);
        }
      }}
    >
      <SelectTrigger className="flex-1 min-w-0">
        <SelectValue placeholder="Pick folder..." />
      </SelectTrigger>
      <SelectContent>
        {folders.map((f) => (
          <SelectItem key={f.id} value={f.id}>
            {f.name}
          </SelectItem>
        ))}
        <SelectItem value={NEW_FOLDER_SENTINEL}>
          + New folder…
        </SelectItem>
      </SelectContent>
    </Select>
  );
}

export function RuleEditorDialog({
  open,
  onOpenChange,
  initialDraft,
  folders,
  permissions,
  onSave,
  onFolderCreated,
}: RuleEditorDialogProps) {

  const [draft, setDraft] = useState<RuleDraft>(initialDraft);
  const [saving, setSaving] = useState(false);
  // Default ON — most users want a rule they create to also clean up
  // existing matches in their inbox (Gmail's default behavior). Reset on
  // every open so a previous "off" choice doesn't silently persist.
  const [applyToExisting, setApplyToExisting] = useState(true);
  const wasOpen = useRef(false);

  // Only snapshot initialDraft on the closed→open transition. While the
  // dialog is open we preserve user edits even if the parent re-renders
  // and passes a fresh initialDraft reference.
  useEffect(() => {
    if (open && !wasOpen.current) {
      setDraft(initialDraft);
      setApplyToExisting(true);
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
      await onSave(draft, { applyToExisting });
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  const isEditing = Boolean(initialDraft.id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto overflow-x-hidden">
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
                className="rounded-md border bg-muted/30 p-2 space-y-2 min-w-0"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Select
                    value={c.field}
                    onValueChange={(v) =>
                      updateCondition(idx, { field: v as ConditionField })
                    }
                  >
                    <SelectTrigger className="flex-1 min-w-0">
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
                    <SelectTrigger className="flex-1 min-w-0">
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
                {c.field === "customer_matched" ? (
                  <Select
                    value={Array.isArray(c.value) ? c.value[0] || "" : c.value || ""}
                    onValueChange={(v) => updateCondition(idx, { value: v })}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="yes / no" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="yes">yes (sender is a matched customer)</SelectItem>
                      <SelectItem value="no">no (sender is not matched)</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <ChipValueInput
                    value={c.value}
                    onChange={(next) => updateCondition(idx, { value: next })}
                    placeholder="value (Enter or , to add more)"
                  />
                )}
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
                <div key={idx} className="flex items-center gap-2 min-w-0">
                  <Select
                    value={a.type}
                    onValueChange={(v) =>
                      updateAction(idx, { type: v as ActionType, params: {} })
                    }
                  >
                    <SelectTrigger className="w-52 min-w-0 shrink-0">
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
                    <FolderPickerOrCreate
                      value={a.params?.folder_id || ""}
                      folders={folders}
                      onSelect={(id) =>
                        updateAction(idx, { params: { ...a.params, folder_id: id } })
                      }
                      onCreated={(f) => {
                        if (onFolderCreated) onFolderCreated(f);
                      }}
                    />
                  )}

                  {opt?.needs.includes("tag") && (
                    <>
                      <Input
                        list={`tag-options-${idx}`}
                        value={a.params?.tag || ""}
                        onChange={(e) =>
                          updateAction(idx, {
                            params: { ...a.params, tag: e.target.value },
                          })
                        }
                        placeholder="tag (type or pick)"
                        className="flex-1 min-w-0"
                      />
                      <datalist id={`tag-options-${idx}`}>
                        {TAG_OPTIONS.map((t) => (
                          <option key={t} value={t} />
                        ))}
                      </datalist>
                    </>
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
                    permissions && Object.keys(permissions.resources).length > 0 ? (
                      <Select
                        value={a.params?.permission_slug || ""}
                        onValueChange={(v) =>
                          updateAction(idx, {
                            params: { ...a.params, permission_slug: v },
                          })
                        }
                      >
                        <SelectTrigger className="flex-1 min-w-0">
                          <SelectValue placeholder="Pick a permission..." />
                        </SelectTrigger>
                        <SelectContent className="max-h-80">
                          {Object.entries(permissions.resources)
                            .sort(([a], [b]) => a.localeCompare(b))
                            .map(([resource, perms]) => (
                              <SelectGroup key={resource}>
                                <SelectLabel className="capitalize">
                                  {resource.replace(/_/g, " ")}
                                </SelectLabel>
                                {perms.map((p) => (
                                  <SelectItem key={p.slug} value={p.slug}>
                                    <span className="flex flex-col text-left">
                                      <span>{p.slug}</span>
                                      {p.description && (
                                        <span className="text-[10px] text-muted-foreground">
                                          {p.description}
                                        </span>
                                      )}
                                    </span>
                                  </SelectItem>
                                ))}
                              </SelectGroup>
                            ))}
                        </SelectContent>
                      </Select>
                    ) : (
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
                    )
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

        {/* "Apply to existing emails" toggle — back-applies the rule's
            actions to threads already in the inbox after save. Default
            on so users don't have to remember to clean up old matches.
            See InboxRulesService.apply_to_existing_threads for the
            backend semantics (skips folder_override + body conditions). */}
        <div className="flex items-center gap-2 px-1 pt-1">
          <Checkbox
            id="apply-to-existing"
            checked={applyToExisting}
            onCheckedChange={(v) => setApplyToExisting(v === true)}
          />
          <Label htmlFor="apply-to-existing" className="text-sm font-normal cursor-pointer">
            Also apply to matching emails already in my inbox
          </Label>
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
