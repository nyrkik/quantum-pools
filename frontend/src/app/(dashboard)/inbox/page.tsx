"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWSRefetch } from "@/lib/ws";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { toast } from "sonner";
import { PenSquare, Settings2, X, RefreshCw, AlertTriangle } from "lucide-react";
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
import { InboxFolderSidebar } from "@/components/inbox/inbox-folder-sidebar";
import { InboxFolderPills } from "@/components/inbox/inbox-folder-pills";

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

// Compact relative-time formatter for the "Synced Xm ago" indicator.
function formatRelativeShort(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  return `${days}d ago`;
}

// Sync is stale if it hasn't ticked in >5 min — the poller runs every 60s,
// so anything past that means polling is stuck or the integration is broken.
function isSyncStale(iso: string): boolean {
  return Date.now() - new Date(iso).getTime() > 5 * 60 * 1000;
}

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
  const [assignFilter, setAssignFilter] = useState<AssignFilter>("all");
  const [staleFilter, setStaleFilter] = useState(false);
  const [autoSentFilter, setAutoSentFilter] = useState(false);
  const [failedFilter, setFailedFilter] = useState(false);
  const [autoHandledFilter, setAutoHandledFilter] = useState(false);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(0);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [selectedFolderKey, setSelectedFolderKey] = useState<string | null>(null);
  const [defaultFolderResolved, setDefaultFolderResolved] = useState(false);

  // Set default folder to first custom folder (e.g., Clients) if one exists
  useEffect(() => {
    if (defaultFolderResolved) return;
    api.get<{ folders: { id: string; is_system: boolean; system_key: string | null }[] }>("/v1/inbox-folders")
      .then((d) => {
        const firstCustom = d.folders.find((f) => !f.is_system);
        if (firstCustom) {
          setSelectedFolderId(firstCustom.id);
          setSelectedFolderKey(null);
        } else {
          setSelectedFolderKey("inbox");
        }
        setDefaultFolderResolved(true);
      })
      .catch(() => {
        setSelectedFolderKey("inbox");
        setDefaultFolderResolved(true);
      });
  }, [defaultFolderResolved]);
  const [folderRefreshKey, setFolderRefreshKey] = useState(0);
  const [groupByClient, setGroupByClient] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  type IntegrationRow = { id: string; type: string; status: string; account_email: string | null; last_error: string | null; last_sync_at: string | null };
  const [allIntegrations, setAllIntegrations] = useState<IntegrationRow[]>([]);
  const brokenIntegrations = useMemo(
    () => allIntegrations.filter((i) => i.status === "error" || i.status === "disconnected"),
    [allIntegrations],
  );
  // Most recent sync across any connected gmail integration. Used to show
  // "Last synced 2m ago" so the user can see the polling loop is alive.
  const lastSyncIso = useMemo(() => {
    const times = allIntegrations
      .filter((i) => i.type === "gmail_api" && i.status === "connected" && i.last_sync_at)
      .map((i) => i.last_sync_at as string);
    if (!times.length) return null;
    return times.sort().slice(-1)[0];
  }, [allIntegrations]);

  // Surface email integrations + last sync time. Refetched on the same beats
  // the inbox already invalidates state (folderRefreshKey is bumped after every
  // successful Sync, after thread mutations, etc.), so this stays fresh without
  // a separate poll loop.
  useEffect(() => {
    api.get<{ integrations: IntegrationRow[] }>("/v1/email-integrations")
      .then((d) => setAllIntegrations(d.integrations || []))
      .catch(() => setAllIntegrations([]));
  }, [folderRefreshKey]);

  // Re-fetch on a slow tick (60s) so the "Last synced Nm ago" indicator
  // doesn't go stale just because the user is sitting on the inbox idle.
  useEffect(() => {
    const t = setInterval(() => {
      api.get<{ integrations: IntegrationRow[] }>("/v1/email-integrations")
        .then((d) => setAllIntegrations(d.integrations || []))
        .catch(() => {});
    }, 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const loadThreads = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });

    // Stale / Auto-Sent / Auto-Handled / Failed filters: search across ALL folders
    if (staleFilter) {
      params.set("status", "stale");
      params.set("exclude_spam", "false");
    } else if (autoSentFilter) {
      params.set("status", "auto_sent");
      params.set("exclude_spam", "false");
    } else if (autoHandledFilter) {
      params.set("status", "auto_handled");
      params.set("exclude_spam", "false");
    } else if (failedFilter) {
      params.set("status", "failed");
      params.set("exclude_spam", "false");
    } else {
      // Folder-based filtering
      if (selectedFolderKey) {
        params.set("folder", selectedFolderKey);
      } else if (selectedFolderId) {
        params.set("folder_id", selectedFolderId);
      }

      // Inbox: exclude spam/ignored (they have their own folders)
      // Non-inbox folders: show everything
      const isInbox = selectedFolderKey === "inbox" || (!selectedFolderKey && !selectedFolderId);
      if (isInbox) {
        params.set("exclude_spam", "true");
        params.set("exclude_ignored", "true");
      } else {
        params.set("exclude_spam", "false");
      }
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
  }, [search, page, assignFilter, staleFilter, autoSentFilter, autoHandledFilter, failedFilter, user?.id, selectedFolderId, selectedFolderKey]);

  const loadStats = useCallback(() => {
    api.get<ThreadStats>("/v1/admin/agent-threads/stats")
      .then(setStats)
      .catch(() => {});
  }, []);

  useEffect(() => { loadThreads(); }, [loadThreads]);
  useEffect(() => { loadStats(); }, [loadStats]);

  useWSRefetch(["thread.new", "thread.updated", "thread.message.new"], loadThreads, 500);
  useWSRefetch(["thread.new", "thread.updated", "thread.message.new", "thread.read"], loadStats, 300);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ignore when typing in input/textarea/contenteditable
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        // Next thread
        const idx = threads.findIndex((t) => t.id === selectedThreadId);
        if (idx < threads.length - 1 && threads.length > 0) {
          e.preventDefault();
          setSelectedThreadId(threads[Math.max(idx + 1, 0)].id);
        }
      } else if (e.key === "k" || e.key === "ArrowUp") {
        // Previous thread
        const idx = threads.findIndex((t) => t.id === selectedThreadId);
        if (idx > 0) {
          e.preventDefault();
          setSelectedThreadId(threads[idx - 1].id);
        }
      } else if (e.key === "Escape") {
        if (selectedThreadId) {
          e.preventDefault();
          setSelectedThreadId(null);
        }
      } else if (e.key === "/") {
        // Focus search
        e.preventDefault();
        const search = document.querySelector<HTMLInputElement>('input[placeholder="Search..."]');
        search?.focus();
      } else if (e.key === "g" && !selectedThreadId) {
        // "g" then folder shortcut — listen for next key
        const next = (e2: KeyboardEvent) => {
          window.removeEventListener("keydown", next);
          if (e2.key === "i") handleFolderSelect(null, "inbox");
          else if (e2.key === "s") {
            // Would need folder lookup; skip for now
          }
        };
        window.addEventListener("keydown", next, { once: true });
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [threads, selectedThreadId]);

  const handleFolderSelect = (folderId: string | null, systemKey: string | null) => {
    setSelectedFolderId(folderId);
    setSelectedFolderKey(systemKey);
    setPage(0);
  };

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(0);
  };

  const handleSelectThread = (id: string) => {
    setSelectedThreadId(id);
    // Optimistically mark read in local state — backend marks it read on detail GET
    setThreads((prev) => prev.map((t) => (t.id === id ? { ...t, is_unread: false } : t)));
    // Refresh stats so the unread count drops immediately
    loadStats();
    setFolderRefreshKey((k) => k + 1);
  };

  const handleCloseDetail = () => {
    setSelectedThreadId(null);
    loadThreads();
    loadStats();
  };

  const [syncing, setSyncing] = useState(false);
  const handleRefresh = async () => {
    setSyncing(true);
    try {
      const result = await api.post<{ synced: number; stats: { fetched: number; ingested: number; errors: number } }>(
        "/v1/email-integrations/sync-all",
        {},
      );
      const { ingested, errors } = result.stats;
      if (ingested > 0) {
        toast.success(`${ingested} new email${ingested === 1 ? "" : "s"} synced`);
      } else if (errors > 0) {
        toast.error(`Sync had ${errors} error${errors === 1 ? "" : "s"}`);
      } else {
        toast.success("Up to date");
      }
      loadThreads();
      loadStats();
      setFolderRefreshKey((k) => k + 1);
    } catch {
      toast.error("Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (!user) return null;

  return (
    <PageLayout
      title="Inbox"
      action={
        <Button size="sm" className="gap-1.5" onClick={() => openCompose()}>
          <PenSquare className="h-3.5 w-3.5" />
          New Email
        </Button>
      }
      secondaryActions={
        <>
          {lastSyncIso && (
            <span
              className={`text-[11px] hidden sm:inline ${
                isSyncStale(lastSyncIso) ? "text-amber-600 dark:text-amber-400 font-medium" : "text-muted-foreground"
              }`}
              title={`Last Gmail sync: ${new Date(lastSyncIso).toLocaleString()}`}
            >
              {isSyncStale(lastSyncIso) ? "⚠ " : ""}Synced {formatRelativeShort(lastSyncIso)}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={handleRefresh}
            disabled={syncing}
            title="Sync new email from Gmail"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
          </Button>
          {perms.can("inbox.manage") && (
            <Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)}>
              <Settings2 className="h-4 w-4" />
            </Button>
          )}
        </>
      }
    >
      {/* Email integration disconnected banner — surfaces silent OAuth failures.
          Without this, when Gmail tokens go bad we silently fall back to Postmark
          and the user never knows their integration is broken. */}
      {brokenIntegrations.length > 0 && perms.can("inbox.manage") && (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <div className="font-medium">
              {brokenIntegrations.length === 1
                ? `Email integration disconnected: ${brokenIntegrations[0].account_email || brokenIntegrations[0].type}`
                : `${brokenIntegrations.length} email integrations disconnected`}
            </div>
            <div className="text-xs opacity-80 mt-0.5">
              Outbound emails are falling through to the Postmark backup. Reconnect to restore Sent-folder visibility and inbox sync.
              {brokenIntegrations[0].last_error ? ` Last error: ${brokenIntegrations[0].last_error}` : ""}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={async () => {
              const broken = brokenIntegrations[0];
              if (broken.type === "gmail_api") {
                try {
                  const resp = await api.post<{ authorize_url: string }>(
                    "/v1/email-integrations/gmail/authorize",
                    { integration_id: broken.id },
                  );
                  window.location.href = resp.authorize_url;
                } catch (e) {
                  const msg = (e as { message?: string })?.message || "Failed to start OAuth";
                  toast.error(msg);
                }
              } else {
                // Non-Gmail (managed mode etc.) — drop user on the settings page
                // since reconnect is provider-specific.
                window.location.href = "/settings/email";
              }
            }}
          >
            Reconnect
          </Button>
        </div>
      )}

      {/* Mobile folder pills */}
      <InboxFolderPills
        selectedFolderId={selectedFolderId}
        onSelectFolder={handleFolderSelect}
      />

      <div className="flex gap-3 w-full max-w-full overflow-hidden" style={{ height: "calc(100vh - 10rem)" }}>
        {/* Desktop folder sidebar */}
        <InboxFolderSidebar
          selectedFolderId={selectedFolderId}
          onSelectFolder={handleFolderSelect}
          className="hidden sm:flex w-40 shrink-0 border-r pr-3"
          refreshKey={folderRefreshKey}
          autoHandledToday={(stats as { auto_handled_today?: number } | null)?.auto_handled_today ?? 0}
        />

        {/* Thread list */}
        <div className={`min-w-0 space-y-2 transition-all overflow-y-auto overflow-x-hidden ${
          selectedThreadId ? "hidden lg:block lg:flex-[4] lg:shrink lg:min-w-0" : "flex-1"
        }`}>
          <InboxFilters
            assignFilter={assignFilter}
            onAssignFilterChange={(f) => { setAssignFilter(f); setPage(0); }}
            searchInput={searchInput}
            onSearchInputChange={setSearchInput}
            onSearch={handleSearch}
            stats={stats}
            groupByClient={groupByClient}
            onGroupByClientChange={setGroupByClient}
            staleFilter={staleFilter}
            onStaleFilterChange={(v) => { setStaleFilter(v); setAutoSentFilter(false); setAutoHandledFilter(false); setFailedFilter(false); setPage(0); }}
            autoSentFilter={autoSentFilter}
            onAutoSentFilterChange={(v) => { setAutoSentFilter(v); setStaleFilter(false); setAutoHandledFilter(false); setFailedFilter(false); setPage(0); }}
            failedFilter={failedFilter}
            onFailedFilterChange={(v) => { setFailedFilter(v); setStaleFilter(false); setAutoSentFilter(false); setAutoHandledFilter(false); setPage(0); }}
            autoHandledFilter={autoHandledFilter}
            onAutoHandledFilterChange={(v) => { setAutoHandledFilter(v); setStaleFilter(false); setAutoSentFilter(false); setFailedFilter(false); setPage(0); }}
            autoHandledTodayCount={(stats as { auto_handled_today?: number } | null)?.auto_handled_today ?? 0}
          />

          <InboxMobileList threads={threads} loading={loading} currentUserId={user.id} />

          <InboxThreadTable
            threads={threads}
            loading={loading}
            currentUserId={user.id}
            onSelectThread={handleSelectThread}
            selectedThreadId={selectedThreadId}
            onBulkAction={() => { loadThreads(); loadStats(); setFolderRefreshKey((k) => k + 1); }}
            compact={!!selectedThreadId}
            groupByClient={groupByClient}
          />

          <InboxPagination
            page={page}
            totalPages={totalPages}
            total={total}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        </div>

        {/* Desktop: inline detail pane (right side) */}
        {selectedThreadId && (
          <div className="hidden sm:flex flex-[5] shrink min-w-0 flex-col rounded-lg border shadow-sm bg-background overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={handleCloseDetail}
                onAction={() => { loadThreads(); loadStats(); setFolderRefreshKey((k) => k + 1); }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Mobile only: sheet overlay — not rendered on desktop */}
      {isMobile && (
        <Sheet
          open={!!selectedThreadId}
          onOpenChange={(open) => { if (!open) handleCloseDetail(); }}
        >
          <SheetContent side="right" className="w-full p-0 flex flex-col">
            <SheetHeader className="px-4 pt-3 pb-2 border-b shrink-0">
              <SheetTitle className="text-base">Conversation</SheetTitle>
            </SheetHeader>
            <div className="flex-1 overflow-y-auto">
              {selectedThreadId && (
                <ThreadDetailSheet
                  threadId={selectedThreadId}
                  onClose={handleCloseDetail}
                  onAction={() => { loadThreads(); loadStats(); setFolderRefreshKey((k) => k + 1); }}
                />
              )}
            </div>
          </SheetContent>
        </Sheet>
      )}

      <InboxSettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </PageLayout>
  );
}
