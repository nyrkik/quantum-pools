"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { CheckCircle2, Circle, X } from "lucide-react";
import type { JobTask } from "@/types/agent";

interface TasksSectionProps {
  actionId: string;
  tasks: JobTask[];
  onUpdate: () => void;
}

export function TasksSection({ actionId, tasks, onUpdate }: TasksSectionProps) {
  const [newTitle, setNewTitle] = useState("");
  const [adding, setAdding] = useState(false);

  const handleAdd = async () => {
    if (!newTitle.trim()) return;
    setAdding(true);
    try {
      await api.post(`/v1/admin/agent-actions/${actionId}/tasks`, { title: newTitle });
      setNewTitle("");
      onUpdate();
    } catch { toast.error("Failed to add task"); }
    finally { setAdding(false); }
  };

  const handleToggle = async (taskId: string, currentStatus: string) => {
    const newStatus = currentStatus === "done" ? "open" : "done";
    try {
      await api.put(`/v1/admin/agent-actions/${actionId}/tasks/${taskId}`, { status: newStatus });
      onUpdate();
    } catch { toast.error("Failed"); }
  };

  const handleDelete = async (taskId: string) => {
    try {
      await api.delete(`/v1/admin/agent-actions/${actionId}/tasks/${taskId}`);
      onUpdate();
    } catch { toast.error("Failed"); }
  };

  const openTasks = tasks.filter(t => t.status !== "cancelled");
  const doneCount = openTasks.filter(t => t.status === "done").length;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-1">
          Tasks
          {openTasks.length > 0 && (
            <span className="text-[10px] bg-muted rounded-full px-1.5">{doneCount}/{openTasks.length}</span>
          )}
        </p>
      </div>

      {openTasks.length > 0 && (
        <div className="space-y-1 mb-2">
          {openTasks.map((t) => (
            <div key={t.id} className="flex items-center gap-2 py-1 group">
              <button
                onClick={() => handleToggle(t.id, t.status)}
                className="flex-shrink-0"
              >
                {t.status === "done" ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground hover:text-amber-500" />
                )}
              </button>
              <span className={`text-sm flex-1 ${t.status === "done" ? "line-through text-muted-foreground" : ""}`}>
                {t.title}
              </span>
              {t.assigned_to && (
                <span className="text-[10px] text-muted-foreground">{t.assigned_to}</span>
              )}
              <button
                onClick={() => handleDelete(t.id)}
                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <Input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Add a task..."
          className="text-sm h-7 flex-1"
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAdd(); } }}
        />
        <Button size="sm" className="h-7 text-xs" onClick={handleAdd} disabled={adding || !newTitle.trim()}>
          Add
        </Button>
      </div>
    </div>
  );
}
