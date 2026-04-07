"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWSRefetch } from "@/lib/ws";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { toast } from "sonner";
import { Bot, PenSquare, Settings2 } from "lucide-react";
import { useCompose } from "@/components/email/compose-provider";
import { PageLayout } from "@/components/layout/page-layout";
import { usePermissions } from "@/lib/permissions";
import type { Thread } from "@/types/agent";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";
import { InboxSettingsSheet } from "@/components/inbox/inbox-settings-sheet";
import { InboxFilters } from "@/components/inbox/inbox-filters";
import { InboxMobileList } from "@/components/inbox/inbox-mobile-list";
import { InboxThreadTable } from "@/components/inbox/inbox-thread-table";
import { InboxPagination } from "@/components/inbox/inbox-pagination";

// --- Types ---

interface ThreadStats {
  total: number;
  pending: number;
  stale_pending: number;
  open_actions: number;
}

interface PaginatedThreads {
  items: Thread[];
  total: number;
}

const PAGE_SIZE = 25;

type StatusFilter = "clients" | "all" | "handled";
type AssignFilter = "all" | "mine";

// --- Main Page ---

export default function InboxPage() {
  const { user } = useAuth();
  const { openCompose } = useCompose();
  const perms = usePermissions();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<ThreadStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<StatusFilter>("clients");
  const [assignFilter, setAssignFilter] = useState<AssignFilter>("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(0);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);

  const loadThreads = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (filter === "clients") {
      params.set("exclude_spam", "true");
      params.set("exclude_ignored", "true");
    } else if (filter === "handled") {
      params.set("status", "handled");
    } else if (filter === "all") {
      params.set("exclude_spam", "false");
    }
    if (search) params.set("search", search);
    if (assignFilter === "mine" && user?.id) params.set("assigned_to", user.id);

    api.get<PaginatedThreads>(`/v1/admin/agent-threads?${params}`)
      .then((data) => {
        setThreads(data.items);
        setTotal(data.total);
      })
      .catch(() => toast.error("Failed to load threads"))
      .finally(() => setLoading(false));
  }, [filter, search, page, assignFilter, user?.id]);

  const loadStats = useCallback(() => {
    api.get<ThreadStats>("/v1/admin/agent-threads/stats")
      .then(setStats)
      .catch(() => {});
  }, []);

  useEffect(() => { loadThreads(); }, [loadThreads]);
  useEffect(() => { loadStats(); }, [loadStats]);

  useWSRefetch(["thread.new", "thread.updated", "thread.message.new"], loadThreads, 500);
  useWSRefetch(["thread.new", "thread.updated", "thread.message.new", "thread.read"], loadStats, 300);

  const handleFilterChange = (f: StatusFilter) => {
    setFilter(f);
    setPage(0);
  };

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(0);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (!user) return null;

  return (
    <PageLayout
      title="Inbox"
      icon={<Bot className="h-5 w-5 text-muted-foreground" />}
      action={
        <Button size="sm" className="gap-1.5" onClick={() => openCompose()}>
          <PenSquare className="h-3.5 w-3.5" />
          New Email
        </Button>
      }
      secondaryActions={
        perms.can("inbox.manage") ? (
          <Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)}>
            <Settings2 className="h-4 w-4" />
          </Button>
        ) : undefined
      }
    >
      <InboxFilters
        filter={filter}
        onFilterChange={handleFilterChange}
        assignFilter={assignFilter}
        onAssignFilterChange={(f) => { setAssignFilter(f); setPage(0); }}
        searchInput={searchInput}
        onSearchInputChange={setSearchInput}
        onSearch={handleSearch}
        stats={stats}
      />

      <InboxMobileList threads={threads} loading={loading} currentUserId={user.id} />

      <InboxThreadTable
        threads={threads}
        loading={loading}
        currentUserId={user.id}
        onSelectThread={setSelectedThreadId}
      />

      <InboxPagination
        page={page}
        totalPages={totalPages}
        total={total}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />

      {/* Thread detail */}
      <Sheet open={!!selectedThreadId} onOpenChange={(open) => { if (!open) { setSelectedThreadId(null); loadThreads(); } }}>
        <SheetContent side="right" className="w-full sm:max-w-xl p-0 flex flex-col">
          <SheetHeader className="px-4 pt-3 pb-2 border-b shrink-0">
            <SheetTitle className="text-base">Conversation</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto">
            {selectedThreadId && (
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={() => setSelectedThreadId(null)}
                onAction={() => { loadThreads(); loadStats(); }}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>

      <InboxSettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </PageLayout>
  );
}
