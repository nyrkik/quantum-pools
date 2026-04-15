"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2 } from "lucide-react";
import type { CaseJob } from "./case-components";

interface Props {
  caseId: string;
  cascadeJobs: CaseJob[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}

export function ReopenCaseDialog({ caseId, cascadeJobs, open, onOpenChange, onDone }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.put(`/v1/cases/${caseId}`, { status: "open" });
      if (selected.size > 0) {
        const result = await api.post<{ reopened: number }>(
          `/v1/cases/${caseId}/reopen-jobs`,
          { job_ids: Array.from(selected) },
        );
        toast.success(`Case reopened · ${result.reopened} job(s) reopened`);
      } else {
        toast.success("Case reopened");
      }
      onOpenChange(false);
      onDone();
    } catch (e: unknown) {
      const msg = e instanceof Error && e.message ? e.message : "Failed to reopen case";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Reopen case</DialogTitle>
          <DialogDescription>
            {cascadeJobs.length > 0
              ? `${cascadeJobs.length} job(s) were auto-closed when this case closed. Select any you'd like to reopen.`
              : "Reopen this case."}
          </DialogDescription>
        </DialogHeader>
        {cascadeJobs.length > 0 && (
          <div className="max-h-80 overflow-y-auto space-y-2 rounded border p-2">
            {cascadeJobs.map((job) => (
              <label
                key={job.id}
                className="flex items-start gap-2 text-sm cursor-pointer hover:bg-muted/50 rounded p-1"
              >
                <Checkbox
                  checked={selected.has(job.id)}
                  onCheckedChange={() => toggle(job.id)}
                  className="mt-0.5"
                />
                <span className="flex-1 min-w-0">
                  <span className="block truncate">{job.description}</span>
                  <span className="block text-xs text-muted-foreground">
                    {job.action_type}
                    {job.completed_at && ` · closed ${new Date(job.completed_at).toLocaleDateString()}`}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
        <DialogFooter className="gap-2">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={submitting}>
            {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
            Reopen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
