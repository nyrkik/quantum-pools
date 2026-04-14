"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertTriangle, Search, User, Users, Bot, MailX, UserCheck, CheckCheck } from "lucide-react";

interface ThreadStats {
  total: number;
  pending: number;
  stale_pending: number;
  open_actions: number;
  failed?: number;
}

type AssignFilter = "all" | "mine";

interface InboxFiltersProps {
  assignFilter: AssignFilter;
  onAssignFilterChange: (f: AssignFilter) => void;
  searchInput: string;
  onSearchInputChange: (v: string) => void;
  onSearch: () => void;
  stats: ThreadStats | null;
  groupByClient?: boolean;
  onGroupByClientChange?: (v: boolean) => void;
  clientsOnlyFilter?: boolean;
  onClientsOnlyFilterChange?: (v: boolean) => void;
  handledFilter?: boolean;
  onHandledFilterChange?: (v: boolean) => void;
  staleFilter?: boolean;
  onStaleFilterChange?: (v: boolean) => void;
  failedFilter?: boolean;
  onFailedFilterChange?: (v: boolean) => void;
  autoHandledFilter?: boolean;
  onAutoHandledFilterChange?: (v: boolean) => void;
  autoHandledTodayCount?: number;  // for chip-style count
  // Ops chips (Failed, Auto-Handled, Stale) are owner/admin only —
  // billing/ops triage is not a manager concern. Backend stats also zero these
  // out for non-managers as defense in depth.
  canManageInbox?: boolean;
}

export function InboxFilters({
  assignFilter,
  onAssignFilterChange,
  searchInput,
  onSearchInputChange,
  onSearch,
  stats,
  groupByClient,
  onGroupByClientChange,
  clientsOnlyFilter,
  onClientsOnlyFilterChange,
  handledFilter,
  onHandledFilterChange,
  staleFilter,
  onStaleFilterChange,
  failedFilter,
  onFailedFilterChange,
  autoHandledFilter,
  onAutoHandledFilterChange,
  autoHandledTodayCount,
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
      {onHandledFilterChange && (
        <Button
          variant={handledFilter ? "default" : "outline"}
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => onHandledFilterChange(!handledFilter)}
          title="Show threads already marked handled"
        >
          <CheckCheck className="h-3.5 w-3.5 mr-1" />
          Handled
        </Button>
      )}
      {onGroupByClientChange && (
        <Button
          variant={groupByClient ? "default" : "outline"}
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => onGroupByClientChange(!groupByClient)}
        >
          <Users className="h-3.5 w-3.5 mr-1" />
          By Client
        </Button>
      )}
      {canManageInbox && stats && (stats.failed ?? 0) > 0 && onFailedFilterChange && (
        <Button
          variant={failedFilter ? "destructive" : "outline"}
          size="sm"
          className={`h-7 px-2.5 text-xs gap-1 ${!failedFilter ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400" : ""}`}
          onClick={() => onFailedFilterChange(!failedFilter)}
        >
          <MailX className="h-3.5 w-3.5" />
          {stats.failed} Failed
        </Button>
      )}
      {canManageInbox && onAutoHandledFilterChange && (
        <Button
          variant={autoHandledFilter ? "default" : "outline"}
          size="sm"
          className={`h-7 px-2.5 text-xs gap-1 ${!autoHandledFilter ? "border-purple-300 bg-purple-50 text-purple-700 hover:bg-purple-100 dark:border-purple-800 dark:bg-purple-950/30 dark:text-purple-400" : ""}`}
          onClick={() => onAutoHandledFilterChange(!autoHandledFilter)}
          title="Show all emails the AI auto-handled (moved/tagged without human action)"
        >
          <Bot className="h-3.5 w-3.5" />
          Auto-Handled
          {(autoHandledTodayCount ?? 0) > 0 && (
            <span className="ml-0.5 text-[10px] font-semibold opacity-70">+{autoHandledTodayCount}</span>
          )}
        </Button>
      )}
      {canManageInbox && stats && stats.pending > 0 && onStaleFilterChange && (
        <Button
          variant={staleFilter ? "destructive" : "outline"}
          size="sm"
          className={`h-7 px-2.5 text-xs gap-1 ${!staleFilter ? "border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400" : ""}`}
          onClick={() => onStaleFilterChange(!staleFilter)}
        >
          <AlertTriangle className="h-3.5 w-3.5" />
          {stats.pending} Pending
        </Button>
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
