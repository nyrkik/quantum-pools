"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertTriangle, Search, User, Users, Bot, MailX } from "lucide-react";

interface ThreadStats {
  total: number;
  pending: number;
  stale_pending: number;
  open_actions: number;
  auto_sent?: number;
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
  staleFilter?: boolean;
  onStaleFilterChange?: (v: boolean) => void;
  autoSentFilter?: boolean;
  onAutoSentFilterChange?: (v: boolean) => void;
  failedFilter?: boolean;
  onFailedFilterChange?: (v: boolean) => void;
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
  staleFilter,
  onStaleFilterChange,
  autoSentFilter,
  onAutoSentFilterChange,
  failedFilter,
  onFailedFilterChange,
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
      {stats && (stats.failed ?? 0) > 0 && onFailedFilterChange && (
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
      {stats && (stats.auto_sent ?? 0) > 0 && onAutoSentFilterChange && (
        <Button
          variant={autoSentFilter ? "default" : "outline"}
          size="sm"
          className={`h-7 px-2.5 text-xs gap-1 ${!autoSentFilter ? "border-sky-300 bg-sky-50 text-sky-700 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-400" : ""}`}
          onClick={() => onAutoSentFilterChange(!autoSentFilter)}
        >
          <Bot className="h-3.5 w-3.5" />
          Auto-Sent
        </Button>
      )}
      {stats && stats.pending > 0 && onStaleFilterChange && (
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
