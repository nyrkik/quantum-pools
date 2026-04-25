"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PageLayout } from "@/components/layout/page-layout";
import {
  RuleEditorDialog,
  type RuleDraft,
} from "@/components/inbox/rule-editor-dialog";
import { api } from "@/lib/api";
import { GripVertical, Pencil, Plus, Trash2, Wand2, X, PlayCircle, Loader2 } from "lucide-react";
import { BackButton } from "@/components/ui/back-button";
import { toast } from "sonner";

interface InboxFolder {
  id: string;
  name: string;
}

interface PermissionItem {
  slug: string;
  action: string;
  description: string | null;
}

interface PermissionCatalog {
  resources: Record<string, PermissionItem[]>;
}

interface RuleRow extends RuleDraft {
  id: string;
  created_by: string | null;
  created_at: string;
}

const EMPTY_DRAFT: RuleDraft = {
  name: "",
  priority: 100,
  conditions: [{ field: "sender_email", operator: "equals", value: "" }],
  actions: [{ type: "assign_folder", params: {} }],
  is_active: true,
};

// Thread context pulled when the rules page opens from a thread's wand
// icon — drives the "Add from thread" banner + per-row Add-sender buttons.
interface ThreadContext {
  id: string;
  subject: string | null;
  contact_email: string;
  category: string | null;
  sender_tag: string | null;
  folder_id: string | null;
}

function draftFromThread(ctx: ThreadContext): RuleDraft {
  const sender = (ctx.contact_email || "").toLowerCase();
  const actions: RuleDraft["actions"] = [];
  if (ctx.folder_id) {
    actions.push({ type: "assign_folder", params: { folder_id: ctx.folder_id } });
  }
  if (ctx.sender_tag) {
    actions.push({ type: "assign_tag", params: { tag: ctx.sender_tag } });
  }
  if (ctx.category && ctx.category !== "general") {
    actions.push({ type: "assign_category", params: { category: ctx.category } });
  }
  if (actions.length === 0) {
    actions.push({ type: "assign_folder", params: {} });
  }
  return {
    name: sender ? `Auto-handle ${sender}` : "New rule from inbox",
    priority: 100,
    conditions: sender
      ? [{ field: "sender_email", operator: "equals", value: sender }]
      : [],
    actions,
    is_active: true,
  };
}

// A rule is "add-sender-compatible" when it has at least one condition
// on sender_email or sender_domain with the equals operator — those are
// the conditions whose value is a set the append-sender endpoint extends.
function ruleAcceptsSender(rule: RuleDraft): boolean {
  return rule.conditions.some(
    (c) =>
      (c.field === "sender_email" || c.field === "sender_domain") &&
      c.operator === "equals",
  );
}

const FIELD_LABEL: Record<string, string> = {
  sender_email: "sender",
  sender_domain: "sender domain",
  subject: "subject",
  category: "category",
  customer_id: "customer",
  customer_matched: "matched-customer",
  delivered_to: "recipient",
};

const OPERATOR_LABEL: Record<string, string> = {
  equals: "is",
  contains: "contains",
  starts_with: "starts with",
  ends_with: "ends with",
  matches: "matches",
};

function humanizeConditions(conditions: RuleDraft["conditions"]): string {
  if (conditions.length === 0) return "always";
  return conditions
    .map((c) => {
      // Special: customer_matched reads more naturally as a whole phrase.
      if (c.field === "customer_matched") {
        const v = Array.isArray(c.value) ? c.value[0] : c.value;
        return v === "yes" ? "sender is a matched customer" : "sender is not a matched customer";
      }
      const field = FIELD_LABEL[c.field] ?? c.field;
      const op = OPERATOR_LABEL[c.operator] ?? c.operator;
      if (Array.isArray(c.value)) {
        if (c.value.length === 0) return `${field} ${op} (none)`;
        if (c.value.length === 1) return `${field} ${op} "${c.value[0]}"`;
        if (c.value.length <= 3) {
          return `${field} ${op} any of "${c.value.join('", "')}"`;
        }
        return `${field} ${op} any of ${c.value.length} values`;
      }
      return `${field} ${op} "${c.value}"`;
    })
    .join(" and ");
}

function humanizeActions(
  actions: RuleDraft["actions"],
  folderNameById: Map<string, string>,
): string {
  return actions
    .map((a) => {
      switch (a.type) {
        case "route_to_spam":
          return "→ Spam folder";
        case "assign_folder": {
          const fid = typeof a.params?.folder_id === "string" ? a.params.folder_id : null;
          const name = fid ? folderNameById.get(fid) : null;
          return name ? `→ ${name} folder` : "→ folder";
        }
        case "assign_tag":
          return `tag as ${typeof a.params?.tag === "string" ? a.params.tag : "?"}`;
        case "assign_category":
          return `category: ${typeof a.params?.category === "string" ? a.params.category : "?"}`;
        case "set_visibility": {
          const slugs = Array.isArray(a.params?.role_slugs) ? a.params.role_slugs : [];
          return slugs.length > 0
            ? `visible to ${slugs.join(", ")}`
            : "visible to everyone";
        }
        case "mark_as_read":
          return "mark read";
        case "suppress_contact_prompt":
          return "skip contact prompt";
        case "skip_customer_match":
          return "don't auto-match to past customer";
        default:
          return a.type;
      }
    })
    .join(", ");
}

function SortableRuleRow({
  rule,
  folderNameById,
  onEdit,
  onToggleActive,
  onDelete,
  threadContext,
  onAddSender,
  addingSenderFor,
  onApplyToExisting,
  applyingTo,
}: {
  rule: RuleRow;
  folderNameById: Map<string, string>;
  onEdit: (rule: RuleRow) => void;
  onToggleActive: (rule: RuleRow, next: boolean) => void;
  onDelete: (rule: RuleRow) => void;
  threadContext: ThreadContext | null;
  onAddSender: (rule: RuleRow) => void;
  addingSenderFor: string | null;
  onApplyToExisting: (rule: RuleRow) => void;
  applyingTo: string | null;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: rule.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const summary = `${humanizeConditions(rule.conditions)} ${humanizeActions(rule.actions, folderNameById)}`;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-2 border-b px-2 py-1.5 hover:bg-muted/40"
    >
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab text-muted-foreground hover:text-foreground shrink-0"
        aria-label="Drag to reorder"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex-1 min-w-0 text-sm truncate">
              {rule.name && (
                <span className="font-medium mr-2">{rule.name}</span>
              )}
              <span className="text-muted-foreground">{summary}</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom" align="start" className="max-w-md">
            <p className="text-xs">
              {rule.name ? `${rule.name} — ${summary}` : summary}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <Switch
        checked={rule.is_active}
        onCheckedChange={(v) => onToggleActive(rule, v)}
        className="shrink-0"
      />
      {threadContext && ruleAcceptsSender(rule) && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 shrink-0 gap-1"
          onClick={() => onAddSender(rule)}
          disabled={addingSenderFor !== null}
          title={`Add ${threadContext.contact_email} to this rule's sender list`}
        >
          <Plus className="h-3.5 w-3.5" />
          Add sender
        </Button>
      )}
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
        onClick={() => onApplyToExisting(rule)}
        disabled={applyingTo !== null}
        title="Apply this rule to existing matching emails"
      >
        {applyingTo === rule.id ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <PlayCircle className="h-3.5 w-3.5" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 shrink-0"
        onClick={() => onEdit(rule)}
      >
        <Pencil className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
        onClick={() => onDelete(rule)}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

export default function InboxRulesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const threadIdParam = searchParams.get("thread_id");
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [folders, setFolders] = useState<InboxFolder[]>([]);
  const [permissions, setPermissions] = useState<PermissionCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<RuleDraft | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<RuleRow | null>(null);
  // Apply-to-existing flow: clicking the Play icon on a rule row first
  // does a dry run to populate the preview dialog, then on confirm runs
  // the real apply. `applyingTo` holds the rule id mid-request so the
  // row's icon spins; `applyPreview` holds the dry-run result + the
  // rule itself so the AlertDialog can describe what's about to change.
  const [applyingTo, setApplyingTo] = useState<string | null>(null);
  const [applyPreview, setApplyPreview] = useState<
    | {
        rule: RuleRow;
        matched: number;
        applied: number;
        skipped_overrides: number;
        has_body_condition: boolean;
        mutates_thread: boolean;
        sample: { thread_id: string; subject: string | null; contact_email: string }[];
      }
    | null
  >(null);
  const [confirmingApply, setConfirmingApply] = useState(false);
  const [threadContext, setThreadContext] = useState<ThreadContext | null>(null);
  const [addingSenderFor, setAddingSenderFor] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const load = useCallback(async () => {
    try {
      const [rulesData, foldersData, permsData] = await Promise.all([
        api.get<RuleRow[]>("/v1/inbox-rules"),
        api.get<{ folders: InboxFolder[] }>("/v1/inbox-folders"),
        api.get<PermissionCatalog>("/v1/permissions/catalog").catch(() => null),
      ]);
      setRules(rulesData);
      setFolders(foldersData.folders || []);
      setPermissions(permsData);
    } catch {
      toast.error("Failed to load inbox rules");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Fetch thread context when arriving from a thread's wand icon. Pulls
  // the same /v1/admin/agent-threads/{id} endpoint that the thread detail
  // sheet uses, so a thread that loads in the inbox loads here.
  useEffect(() => {
    if (!threadIdParam) {
      setThreadContext(null);
      return;
    }
    api.get<{
      id: string;
      subject: string | null;
      contact_email: string;
      category: string | null;
      sender_tag: string | null;
      folder_id: string | null;
    }>(`/v1/admin/agent-threads/${threadIdParam}`)
      .then((t) =>
        setThreadContext({
          id: t.id,
          subject: t.subject,
          contact_email: t.contact_email,
          category: t.category,
          sender_tag: t.sender_tag,
          folder_id: t.folder_id,
        }),
      )
      .catch(() => {
        toast.error("Couldn't load thread context");
        setThreadContext(null);
      });
  }, [threadIdParam]);

  const handleAddSender = async (rule: RuleRow) => {
    if (!threadContext) return;
    setAddingSenderFor(rule.id);
    try {
      await api.post(
        `/v1/inbox-rules/${rule.id}/append-sender?thread_id=${encodeURIComponent(threadContext.id)}`,
        { value: threadContext.contact_email.toLowerCase() },
      );
      toast.success(`Added ${threadContext.contact_email} to "${rule.name || "rule"}"`);
      router.push(`/inbox?thread=${threadContext.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to add sender");
    } finally {
      setAddingSenderFor(null);
    }
  };

  const folderNameById = useMemo(
    () => new Map(folders.map((f) => [f.id, f.name])),
    [folders],
  );

  const handleSave = async (
    draft: RuleDraft,
    options: { applyToExisting: boolean },
  ) => {
    try {
      let savedRuleId: string | null = null;
      if (draft.id) {
        await api.put(`/v1/inbox-rules/${draft.id}`, {
          name: draft.name || null,
          conditions: draft.conditions,
          actions: draft.actions,
          is_active: draft.is_active,
        });
        savedRuleId = draft.id;
        toast.success("Rule updated");
      } else {
        const created = await api.post<{ id: string }>("/v1/inbox-rules", {
          name: draft.name || null,
          conditions: draft.conditions,
          actions: draft.actions,
          is_active: draft.is_active,
        });
        savedRuleId = created.id;
        toast.success("Rule created");
      }
      await load();

      // Back-apply to existing matches (Gmail's "Also apply filter to
      // matching conversations" behavior). Skip silently when the rule
      // is purely advisory (no thread mutations) or when no threads match.
      if (options.applyToExisting && savedRuleId) {
        try {
          const result = await api.post<{
            matched: number; applied: number;
            mutates_thread: boolean; has_body_condition: boolean;
          }>(`/v1/inbox-rules/${savedRuleId}/apply-to-existing`, { dry_run: false });
          if (result.applied > 0) {
            toast.success(
              `Applied to ${result.applied} existing email${result.applied === 1 ? "" : "s"}`,
            );
          } else if (result.matched === 0) {
            toast.info("No existing emails matched this rule");
          } else if (!result.mutates_thread) {
            // Pure advisory rule (assign_tag etc) — no retroactive change.
            // Silent.
          }
          if (result.has_body_condition) {
            toast.info("Body conditions don't apply retroactively");
          }
        } catch (e) {
          toast.error(
            e instanceof Error ? e.message : "Save succeeded, but back-apply failed",
          );
        }
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    }
  };

  const handleApplyToExistingClick = async (rule: RuleRow) => {
    setApplyingTo(rule.id);
    try {
      const preview = await api.post<{
        matched: number; applied: number; skipped_overrides: number;
        has_body_condition: boolean; mutates_thread: boolean;
        sample: { thread_id: string; subject: string | null; contact_email: string }[];
      }>(`/v1/inbox-rules/${rule.id}/apply-to-existing`, { dry_run: true });

      if (preview.matched === 0) {
        toast.info("No existing emails match this rule");
        return;
      }
      if (!preview.mutates_thread) {
        toast.info("This rule has no thread-mutating actions to back-apply");
        return;
      }
      setApplyPreview({ rule, ...preview });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setApplyingTo(null);
    }
  };

  const handleConfirmApply = async () => {
    if (!applyPreview) return;
    setConfirmingApply(true);
    try {
      const result = await api.post<{ matched: number; applied: number }>(
        `/v1/inbox-rules/${applyPreview.rule.id}/apply-to-existing`,
        { dry_run: false },
      );
      toast.success(
        `Applied to ${result.applied} email${result.applied === 1 ? "" : "s"}`,
      );
      setApplyPreview(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setConfirmingApply(false);
    }
  };

  const handleToggleActive = async (rule: RuleRow, next: boolean) => {
    try {
      await api.put(`/v1/inbox-rules/${rule.id}`, { is_active: next });
      setRules((rs) =>
        rs.map((r) => (r.id === rule.id ? { ...r, is_active: next } : r)),
      );
    } catch {
      toast.error("Failed to toggle rule");
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await api.delete(`/v1/inbox-rules/${confirmDelete.id}`);
      setRules((rs) => rs.filter((r) => r.id !== confirmDelete.id));
      toast.success("Rule deleted");
    } catch {
      toast.error("Delete failed");
    } finally {
      setConfirmDelete(null);
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = rules.findIndex((r) => r.id === active.id);
    const newIndex = rules.findIndex((r) => r.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    const reordered = arrayMove(rules, oldIndex, newIndex);
    setRules(reordered);
    try {
      await api.post("/v1/inbox-rules/reorder", {
        rule_ids: reordered.map((r) => r.id),
      });
    } catch {
      toast.error("Failed to save new order");
      load();
    }
  };

  return (
    <PageLayout
      title="Inbox Rules"
      secondaryActions={<BackButton fallback="/inbox" label="" />}
      action={
        <Button
          size="sm"
          onClick={() =>
            setEditing(
              threadContext ? draftFromThread(threadContext) : { ...EMPTY_DRAFT },
            )
          }
        >
          <Plus className="h-3.5 w-3.5 mr-1" /> Add rule
        </Button>
      }
    >
      {threadContext && (
        <div className="flex items-center gap-2 rounded-md border border-purple-200 bg-purple-50 px-3 py-2 text-sm dark:border-purple-800 dark:bg-purple-950/30">
          <Wand2 className="h-4 w-4 text-purple-600 dark:text-purple-400 shrink-0" />
          <span className="flex-1 text-purple-900 dark:text-purple-200 min-w-0 truncate">
            Adding from thread <span className="font-mono text-xs">{threadContext.contact_email}</span>
            {threadContext.subject ? <> &middot; <span className="italic truncate">{threadContext.subject}</span></> : null}
            . Click <span className="font-medium">Add sender</span> on an existing rule, or <span className="font-medium">Add rule</span> to create a new one prefilled from this thread.
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-purple-700 hover:bg-purple-100 dark:text-purple-300 dark:hover:bg-purple-900/30"
            onClick={() => router.replace("/inbox/rules")}
            title="Clear thread context"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : rules.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No rules yet. Click <span className="font-medium">Add rule</span> to route or tag inbound email.
        </p>
      ) : (
        <div className="rounded-md border">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={rules.map((r) => r.id)}
              strategy={verticalListSortingStrategy}
            >
              {rules.map((r) => (
                <SortableRuleRow
                  key={r.id}
                  rule={r}
                  folderNameById={folderNameById}
                  onEdit={(rule) => setEditing({ ...rule })}
                  onToggleActive={handleToggleActive}
                  onDelete={(rule) => setConfirmDelete(rule)}
                  threadContext={threadContext}
                  onAddSender={handleAddSender}
                  addingSenderFor={addingSenderFor}
                  onApplyToExisting={handleApplyToExistingClick}
                  applyingTo={applyingTo}
                />
              ))}
            </SortableContext>
          </DndContext>
        </div>
      )}

      {editing && (
        <RuleEditorDialog
          open={editing !== null}
          onOpenChange={(open) => !open && setEditing(null)}
          initialDraft={editing}
          folders={folders}
          permissions={permissions}
          onSave={handleSave}
          onFolderCreated={(f) =>
            setFolders((current) => {
              if (current.some((existing) => existing.id === f.id)) return current;
              return [...current, f];
            })
          }
          existingTags={Array.from(new Set(
            rules.flatMap((r) =>
              (r.actions || [])
                .filter((a) => a.type === "assign_tag")
                .map((a) => (typeof a.params?.tag === "string" ? a.params.tag : ""))
                .filter(Boolean),
            ),
          ))}
        />
      )}

      <AlertDialog
        open={!!confirmDelete}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this rule?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. Inbound emails that previously matched
              this rule will go through whatever other rules remain.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Apply-to-existing preview confirm. Built from the dry-run
          response: shows match count + a sample of which threads will
          change so the user can sanity-check before committing. */}
      <AlertDialog
        open={!!applyPreview}
        onOpenChange={(o) => { if (!o) setApplyPreview(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Apply rule to existing emails?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-sm">
                <p>
                  Found <span className="font-semibold">{applyPreview?.matched}</span>{" "}
                  matching email{applyPreview?.matched === 1 ? "" : "s"}.
                  This will run the rule&apos;s actions against{" "}
                  {applyPreview && applyPreview.matched - applyPreview.skipped_overrides > 0
                    ? `${applyPreview.matched - applyPreview.skipped_overrides} of them`
                    : "them"}
                  {applyPreview && applyPreview.skipped_overrides > 0
                    ? ` (${applyPreview.skipped_overrides} skipped — already manually moved by you)`
                    : ""}
                  .
                </p>
                {applyPreview && applyPreview.sample.length > 0 && (
                  <div className="rounded-md border p-2 max-h-40 overflow-y-auto bg-muted/30">
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      Sample:
                    </p>
                    <ul className="space-y-0.5 text-xs">
                      {applyPreview.sample.map((s) => (
                        <li key={s.thread_id} className="truncate">
                          <span className="font-mono">{s.contact_email}</span>
                          {s.subject ? <> — {s.subject}</> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {applyPreview?.has_body_condition && (
                  <p className="text-xs text-amber-600">
                    Note: body conditions don&apos;t apply retroactively, so the count
                    above only considers other conditions.
                  </p>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={confirmingApply}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmApply} disabled={confirmingApply}>
              {confirmingApply ? "Applying…" : "Apply"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
