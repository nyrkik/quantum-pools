"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { PageLayout } from "@/components/layout/page-layout";
import {
  RuleEditorDialog,
  type RuleDraft,
} from "@/components/inbox/rule-editor-dialog";
import { api } from "@/lib/api";
import { GripVertical, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

interface InboxFolder {
  id: string;
  name: string;
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

function summarizeConditions(c: RuleDraft["conditions"]): string {
  if (c.length === 0) return "(always)";
  return c
    .map((cc) => `${cc.field} ${cc.operator} "${cc.value}"`)
    .join(" AND ");
}

function summarizeActions(a: RuleDraft["actions"]): string {
  return a
    .map((aa) => {
      const key = Object.values(aa.params || {})[0];
      return key ? `${aa.type}(${key})` : aa.type;
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

  const actionsForDisplay = rule.actions.map((a) => {
    if (a.type === "assign_folder") {
      const fid = a.params?.folder_id;
      const name = fid ? folderNameById.get(fid) : null;
      return { ...a, params: name ? { folder: name } : a.params };
    }
    return a;
  });

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="grid grid-cols-[auto,1fr,2fr,2fr,auto,auto] items-center gap-3 rounded-md border bg-card px-3 py-2 shadow-sm"
    >
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab text-muted-foreground hover:text-foreground"
        aria-label="Drag to reorder"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <div className="min-w-0">
        <div className="text-sm truncate">
          {rule.name || (
            <span className="text-muted-foreground italic">(unnamed)</span>
          )}
        </div>
        {rule.created_by === "migration" && (
          <Badge variant="outline" className="mt-1 text-[10px]">
            migrated
          </Badge>
        )}
      </div>
      <div className="text-xs text-muted-foreground truncate">
        {summarizeConditions(rule.conditions)}
      </div>
      <div className="text-xs text-muted-foreground truncate">
        {summarizeActions(actionsForDisplay)}
      </div>
      <Switch
        checked={rule.is_active}
        onCheckedChange={(v) => onToggleActive(rule, v)}
      />
      <div className="flex items-center">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onEdit(rule)}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => onDelete(rule)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

export default function InboxRulesPage() {
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [folders, setFolders] = useState<InboxFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<RuleDraft | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<RuleRow | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const load = useCallback(async () => {
    try {
      const [rulesData, foldersData] = await Promise.all([
        api.get<RuleRow[]>("/v1/inbox-rules"),
        api.get<{ folders: InboxFolder[] }>("/v1/inbox-folders"),
      ]);
      setRules(rulesData);
      setFolders(foldersData.folders || []);
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
      // Reload from server to get back to a known-good state.
      load();
    }
  };

  return (
    <PageLayout title="Inbox Rules">
      <div className="space-y-4 max-w-6xl">
        <Card className="shadow-sm">
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>Rules</CardTitle>
                <CardDescription>
                  Every inbound email runs through these rules in order.
                  Drag <GripVertical className="inline h-3.5 w-3.5" /> to
                  reorder. All conditions in a rule must match (AND).
                </CardDescription>
              </div>
              <Button onClick={() => setEditing({ ...EMPTY_DRAFT })}>
                <Plus className="h-3.5 w-3.5 mr-1" /> Add rule
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : rules.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No rules yet. Create one above to route or tag inbound email.
              </p>
            ) : (
              <div className="space-y-2">
                <div className="grid grid-cols-[auto,1fr,2fr,2fr,auto,auto] gap-3 px-3 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  <span className="w-4" aria-hidden />
                  <span>Name</span>
                  <span>Conditions</span>
                  <span>Actions</span>
                  <span>Active</span>
                  <span className="w-14 text-right">Edit</span>
                </div>
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
          </CardContent>
        </Card>
      </div>

      {editing && (
        <RuleEditorDialog
          open={editing !== null}
          onOpenChange={(open) => !open && setEditing(null)}
          initialDraft={editing}
          folders={folders}
          onSave={handleSave}
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
