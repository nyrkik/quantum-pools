"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertTriangle, Search, User } from "lucide-react";

interface ThreadStats {
  total: number;
  pending: number;
  stale_pending: number;
  open_actions: number;
}

type StatusFilter = "clients" | "all" | "handled";
type AssignFilter = "all" | "mine";

interface InboxFiltersProps {
  filter: StatusFilter;
  onFilterChange: (f: StatusFilter) => void;
  assignFilter: AssignFilter;
  onAssignFilterChange: (f: AssignFilter) => void;
  searchInput: string;
  onSearchInputChange: (v: string) => void;
  onSearch: () => void;
  stats: ThreadStats | null;
}

const STATUS_FILTERS: StatusFilter[] = ["clients", "all", "handled"];

export function InboxFilters({
  filter,
  onFilterChange,
  assignFilter,
  onAssignFilterChange,
  searchInput,
  onSearchInputChange,
  onSearch,
  stats,
}: InboxFiltersProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1">
        {STATUS_FILTERS.map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            className="h-7 px-2.5 text-xs"
            onClick={() => onFilterChange(f)}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </Button>
        ))}
      </div>
      <Button
        variant={assignFilter === "mine" ? "default" : "outline"}
        size="sm"
        className="h-7 px-2.5 text-xs"
        onClick={() => onAssignFilterChange(assignFilter === "mine" ? "all" : "mine")}
      >
        <User className="h-3.5 w-3.5 mr-1" />
        Mine
      </Button>
      {stats && stats.stale_pending > 0 && (
        <span className="text-xs text-red-600 flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          {stats.stale_pending} stale
        </span>
      )}
      <div className="flex items-center gap-1 ml-auto">
        <Input
          placeholder="Search..."
          value={searchInput}
          onChange={(e) => onSearchInputChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSearch(); }}
          className="h-8 w-48 text-sm"
        />
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onSearch}>
          <Search className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
