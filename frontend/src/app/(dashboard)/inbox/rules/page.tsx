"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

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
import { ArrowLeft, GripVertical, Pencil, Plus, Trash2 } from "lucide-react";
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
          const fid = a.params?.folder_id;
          const name = fid ? folderNameById.get(fid) : null;
          return name ? `→ ${name} folder` : "→ folder";
        }
        case "assign_tag":
          return `tag as ${a.params?.tag ?? "?"}`;
        case "assign_category":
          return `category: ${a.params?.category ?? "?"}`;
        case "set_visibility":
          return `visibility: ${a.params?.permission_slug ?? a.params?.slug ?? "?"}`;
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
}: {
  rule: RuleRow;
  folderNameById: Map<string, string>;
  onEdit: (rule: RuleRow) => void;
  onToggleActive: (rule: RuleRow, next: boolean) => void;
  onDelete: (rule: RuleRow) => void;
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
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [folders, setFolders] = useState<InboxFolder[]>([]);
  const [permissions, setPermissions] = useState<PermissionCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<RuleDraft | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<RuleRow | null>(null);

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

  const folderNameById = useMemo(
    () => new Map(folders.map((f) => [f.id, f.name])),
    [folders],
  );

  const handleSave = async (draft: RuleDraft) => {
    try {
      if (draft.id) {
        await api.put(`/v1/inbox-rules/${draft.id}`, {
          name: draft.name || null,
          conditions: draft.conditions,
          actions: draft.actions,
          is_active: draft.is_active,
        });
        toast.success("Rule updated");
      } else {
        await api.post("/v1/inbox-rules", {
          name: draft.name || null,
          conditions: draft.conditions,
          actions: draft.actions,
          is_active: draft.is_active,
        });
        toast.success("Rule created");
      }
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
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
      secondaryActions={
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push("/inbox")}
          aria-label="Back to inbox"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
      }
      action={
        <Button size="sm" onClick={() => setEditing({ ...EMPTY_DRAFT })}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add rule
        </Button>
      }
    >
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
    </PageLayout>
  );
}
