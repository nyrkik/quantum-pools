"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  CheckCheck,
  Circle,
  Clock,
  Search,
  Settings,
  User,
  UserCheck,
} from "lucide-react";

interface ThreadStats {
  total: number;
  pending: number;
  stale_pending: number;
  open_actions: number;
}

export type AssignFilter = "all" | "mine";
export type StatusFilter = "all" | "pending" | "handled";

interface InboxFiltersProps {
  assignFilter: AssignFilter;
  onAssignFilterChange: (f: AssignFilter) => void;
  clientsOnlyFilter?: boolean;
  onClientsOnlyFilterChange?: (v: boolean) => void;
  statusFilter: StatusFilter;
  onStatusFilterChange: (s: StatusFilter) => void;
  stats: ThreadStats | null;
  onOpenSettings: () => void;
  searchInput: string;
  onSearchInputChange: (v: string) => void;
  onSearch: () => void;
}

/** Segmented status control — single-select lifecycle axis.
 *  All / Pending / Handled. Auto-handled threads now surface in the
 *  AI Review sidebar folder (admin-only); they appear in Handled for
 *  every role with the row-level "AI" pill marking them. */
function StatusSegmented({
  value,
  onChange,
}: {
  value: StatusFilter;
  onChange: (s: StatusFilter) => void;
}) {
  const options: Array<{ key: StatusFilter; label: string; icon: React.ReactNode }> = [
    { key: "all", label: "All", icon: <Circle className="h-3.5 w-3.5" /> },
    { key: "pending", label: "Pending", icon: <Clock className="h-3.5 w-3.5" /> },
    { key: "handled", label: "Handled", icon: <CheckCheck className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="inline-flex items-center rounded-md border bg-background overflow-hidden">
      {options.map((opt, i) => {
        const active = value === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => onChange(opt.key)}
            className={[
              "h-7 px-2.5 text-xs inline-flex items-center gap-1",
              i > 0 ? "border-l" : "",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted",
            ].join(" ")}
            aria-pressed={active}
            aria-label={`Filter: ${opt.label}`}
          >
            {opt.icon}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function InboxFilters({
  assignFilter,
  onAssignFilterChange,
  clientsOnlyFilter,
  onClientsOnlyFilterChange,
  statusFilter,
  onStatusFilterChange,
  stats: _stats,
  onOpenSettings,
  searchInput,
  onSearchInputChange,
  onSearch,
}: InboxFiltersProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Button
        variant={assignFilter === "mine" ? "default" : "outline"}
        size="sm"
        className="h-7 px-2.5 text-xs"
        onClick={() => onAssignFilterChange(assignFilter === "mine" ? "all" : "mine")}
      >
        <User className="h-3.5 w-3.5 mr-1" />
        Mine
      </Button>

      <StatusSegmented
        value={statusFilter}
        onChange={onStatusFilterChange}
      />

      {onClientsOnlyFilterChange && (
        <Button
          variant={clientsOnlyFilter ? "default" : "outline"}
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => onClientsOnlyFilterChange(!clientsOnlyFilter)}
          title="Only show threads matched to a customer"
        >
          <UserCheck className="h-3.5 w-3.5 mr-1" />
          Clients
        </Button>
      )}

      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 text-muted-foreground"
        onClick={onOpenSettings}
        title="Inbox settings"
        aria-label="Inbox settings"
      >
        <Settings className="h-3.5 w-3.5" />
      </Button>

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
