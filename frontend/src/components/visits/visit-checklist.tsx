"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ChevronUp, Loader2, Plus, MessageSquare } from "lucide-react";
import type { VisitChecklistItem } from "@/types/visit";

interface VisitChecklistProps {
  visitId: string;
  items: VisitChecklistItem[];
  onUpdate: (items: VisitChecklistItem[]) => void;
}

const CATEGORY_ORDER = ["Cleaning", "Equipment", "Chemical", "Safety"];
const CATEGORY_LABELS: Record<string, string> = {
  cleaning: "Cleaning",
  equipment: "Equipment",
  chemical: "Chemical",
  safety: "Safety",
};

export function VisitChecklist({ visitId, items, onUpdate }: VisitChecklistProps) {
  const [open, setOpen] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [newItemText, setNewItemText] = useState("");
  const [showAddItem, setShowAddItem] = useState(false);

  const completedCount = items.filter((i) => i.completed).length;
  const totalCount = items.length;
  const pct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const toggleItem = useCallback(
    async (item: VisitChecklistItem) => {
      const updated = { ...item, completed: !item.completed };
      const newItems = items.map((i) => (i.id === item.id ? updated : i));
      onUpdate(newItems);
      setSaving(item.id);
      try {
        await api.put(`/v1/visits/${visitId}/checklist`, [
          { id: item.id, completed: updated.completed, notes: item.notes },
        ]);
      } catch {
        onUpdate(items);
        toast.error("Failed to save checklist");
      } finally {
        setSaving(null);
      }
    },
    [visitId, items, onUpdate]
  );

  const grouped = CATEGORY_ORDER.map((cat) => {
    const key = cat.toLowerCase();
    return {
      label: cat,
      items: items.filter((i) => (i.category || "").toLowerCase() === key),
    };
  }).filter((g) => g.items.length > 0);

  // Items with unrecognized categories
  const otherItems = items.filter(
    (i) => !CATEGORY_ORDER.map((c) => c.toLowerCase()).includes((i.category || "").toLowerCase())
  );
  if (otherItems.length > 0) {
    grouped.push({ label: "Other", items: otherItems });
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center justify-between rounded-lg bg-muted/60 px-4 py-3 text-left">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Checklist</span>
            <Badge variant="secondary" className="text-xs">
              {completedCount}/{totalCount}
            </Badge>
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="space-y-1 pt-2">
          {/* Progress bar */}
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>

          {grouped.map((group) => (
            <div key={group.label} className="pt-2">
              <p className="mb-1 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <label
                    key={item.id}
                    className="flex items-center gap-3 rounded-md px-2 py-2.5 active:bg-muted/60 cursor-pointer"
                  >
                    <div className="relative">
                      <Checkbox
                        checked={item.completed}
                        onCheckedChange={() => toggleItem(item)}
                        className="h-6 w-6 rounded-md"
                      />
                      {saving === item.id && (
                        <Loader2 className="absolute -right-5 top-0.5 h-4 w-4 animate-spin text-muted-foreground" />
                      )}
                    </div>
                    <span className={`text-sm flex-1 ${item.completed ? "text-muted-foreground line-through" : ""}`}>
                      {item.name}
                    </span>
                    {item.notes && <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />}
                  </label>
                ))}
              </div>
            </div>
          ))}

          {/* Add ad-hoc item */}
          {showAddItem ? (
            <div className="flex items-center gap-2 px-2 pt-2">
              <Input
                value={newItemText}
                onChange={(e) => setNewItemText(e.target.value)}
                placeholder="Item name..."
                className="h-9 text-sm"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setShowAddItem(false);
                    setNewItemText("");
                  }
                }}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { setShowAddItem(false); setNewItemText(""); }}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="mt-1 text-muted-foreground"
              onClick={() => setShowAddItem(true)}
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add Item
            </Button>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
