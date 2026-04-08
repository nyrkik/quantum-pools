"use client";

import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import { toast } from "sonner";

interface CaseOwnerProps {
  caseId: string;
  managerName: string | null;
  currentActor: string | null;
  onReassigned?: () => void;
}

export function CaseOwner({ caseId, managerName, currentActor, onReassigned }: CaseOwnerProps) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const members = useTeamMembersFull();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleSelect = async (member: { user_id: string; first_name: string; last_name: string }) => {
    setSaving(true);
    const name = `${member.first_name} ${member.last_name}`.trim();
    try {
      await api.put(`/v1/cases/${caseId}`, {
        manager_name: name,
        assigned_to_user_id: member.user_id,
      });
      onReassigned?.();
      setOpen(false);
    } catch {
      toast.error("Failed to reassign");
    } finally {
      setSaving(false);
    }
  };

  // What to display
  const manager = managerName || "Unassigned";
  const actorDiffers = currentActor && currentActor !== managerName && currentActor !== "Awaiting customer";
  const isAwaiting = currentActor === "Awaiting customer";

  return (
    <div ref={containerRef} className="relative inline-block">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className="text-left text-sm hover:underline cursor-pointer"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(!open);
          }}
        >
          {managerName || <span className="text-muted-foreground text-xs">Unassigned</span>}
        </button>
        {isAwaiting && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 italic">
            awaiting customer
          </span>
        )}
        {actorDiffers && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
            {currentActor}
          </span>
        )}
      </div>
      {open && (
        <div
          className="absolute z-50 mt-1 left-0 bg-background border rounded-md shadow-md py-1 min-w-[160px] max-h-48 overflow-y-auto flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {members.map((m) => {
            const name = `${m.first_name} ${m.last_name}`.trim();
            const isCurrent = name === managerName;
            return (
              <button
                key={m.user_id}
                type="button"
                disabled={saving}
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-muted/50 ${
                  isCurrent ? "font-medium text-primary" : ""
                }`}
                onClick={() => handleSelect(m)}
              >
                {m.first_name}
                {isCurrent && <span className="text-xs text-muted-foreground ml-1.5">(current)</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
