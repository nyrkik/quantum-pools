"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Bot,
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
export type StatusFilter = "all" | "pending" | "handled" | "auto_handled";

interface InboxFiltersProps {
  assignFilter: AssignFilter;
  onAssignFilterChange: (f: AssignFilter) => void;
  clientsOnlyFilter?: boolean;
  onClientsOnlyFilterChange?: (v: boolean) => void;
  statusFilter: StatusFilter;
  onStatusFilterChange: (s: StatusFilter) => void;
  autoHandledTodayCount?: number;
  stats: ThreadStats | null;
  onOpenSettings: () => void;
  searchInput: string;
  onSearchInputChange: (v: string) => void;
  onSearch: () => void;
  /** Owner/admin: shows the Auto-Handled segment alongside the others.
   *  Ops chips were separate buttons in the pre-rework layout; now folded
   *  into the single status axis so there's one thing to change. */
  canManageInbox?: boolean;
}

/** Segmented status control — single-select lifecycle axis. Replaces the
 *  scattered Handled / Auto-Handled / Pending chips from pre-2026-04-24.
 *  Auto-Handled is a subtype of handled (AI closed it without human action),
 *  so admins get a 4th pill; regular users see 3. */
function StatusSegmented({
  value,
  onChange,
  autoHandledTodayCount,
  canManageInbox,
}: {
  value: StatusFilter;
  onChange: (s: StatusFilter) => void;
  autoHandledTodayCount?: number;
  canManageInbox?: boolean;
}) {
  const options: Array<{ key: StatusFilter; label: string; icon: React.ReactNode; badge?: number }> = [
    { key: "all", label: "All", icon: <Circle className="h-3.5 w-3.5" /> },
    { key: "pending", label: "Pending", icon: <Clock className="h-3.5 w-3.5" /> },
    { key: "handled", label: "Handled", icon: <CheckCheck className="h-3.5 w-3.5" /> },
  ];
  if (canManageInbox) {
    options.push({
      key: "auto_handled",
      label: "Auto",
      icon: <Bot className="h-3.5 w-3.5" />,
      badge: autoHandledTodayCount && autoHandledTodayCount > 0 ? autoHandledTodayCount : undefined,
    });
  }

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
            {opt.badge !== undefined && (
              <span className="ml-0.5 text-[10px] font-semibold opacity-70">+{opt.badge}</span>
            )}
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
  autoHandledTodayCount,
  stats: _stats,
  onOpenSettings,
  searchInput,
  onSearchInputChange,
  onSearch,
  canManageInbox = false,
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
        autoHandledTodayCount={autoHandledTodayCount}
        canManageInbox={canManageInbox}
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
