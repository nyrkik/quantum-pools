"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface JobFilterBarProps {
  jobFilter: string;
  onFilterChange: (filter: string) => void;
  showCompleted: boolean;
  onShowCompletedChange: (show: boolean) => void;
  teamMembers: string[];
}

export function JobFilterBar({
  jobFilter,
  onFilterChange,
  showCompleted,
  onShowCompletedChange,
  teamMembers,
}: JobFilterBarProps) {
  return (
    <div className="flex flex-col sm:flex-row gap-3 justify-between">
      <div className="flex gap-2 items-center">
        <Button
          variant={jobFilter === "mine" ? "default" : "outline"}
          size="sm"
          className="h-7"
          onClick={() => onFilterChange("mine")}
        >
          My Jobs
        </Button>
        <Button
          variant={jobFilter === "all" ? "default" : "outline"}
          size="sm"
          className="h-7"
          onClick={() => onFilterChange("all")}
        >
          All
        </Button>
        {teamMembers.length > 0 && (
          <Select
            value={teamMembers.includes(jobFilter) ? jobFilter : ""}
            onValueChange={(v) => onFilterChange(v)}
          >
            <SelectTrigger className="h-7 w-40 text-xs">
              <SelectValue placeholder="Team member..." />
            </SelectTrigger>
            <SelectContent>
              {teamMembers.map((name) => (
                <SelectItem key={name} value={name} className="text-xs">
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={showCompleted}
            onChange={(e) => onShowCompletedChange(e.target.checked)}
            className="rounded"
          />
          Done
        </label>
      </div>
    </div>
  );
}
