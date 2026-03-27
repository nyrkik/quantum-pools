"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { toast } from "sonner";
import {
  Loader2,
  Clock,
  Search,
  Bot,
  AlertTriangle,
  Mail,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  PenSquare,
  User,
  Lock,
  Settings2,
} from "lucide-react";
import { useCompose } from "@/components/email/compose-provider";
import { usePermissions } from "@/lib/permissions";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";
import { StatusBadge, UrgencyBadge, CategoryBadge } from "@/components/inbox/inbox-badges";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";
import { InboxSettingsSheet } from "@/components/inbox/inbox-settings-sheet";

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

const STATUS_FILTERS = ["clients", "all", "handled"] as const;
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
  const [filter, setFilter] = useState<typeof STATUS_FILTERS[number]>("clients");
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

  const handleFilterChange = (f: typeof STATUS_FILTERS[number]) => {
    setFilter(f);
    setPage(0);
  };

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(0);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Pending threads for "Needs Attention"
  const pendingThreads = filter === "clients" ? threads.filter((t) => t.has_pending) : [];

  if (!user) return null;

  return (
    <div className="p-4 sm:p-6 pt-16 sm:pt-6 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Bot className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-xl font-semibold">Inbox</h1>
        <div className="ml-auto flex items-center gap-2">
          {perms.can("inbox.manage") && (
            <Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)}>
              <Settings2 className="h-4 w-4" />
            </Button>
          )}
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => openCompose()}
          >
            <PenSquare className="h-3.5 w-3.5" />
            New Email
          </Button>
        </div>
      </div>

      {/* Stats tile */}
      {stats && (
        <button
          type="button"
          onClick={() => handleFilterChange("clients")}
          className={`w-full text-left rounded-lg border p-3 shadow-sm transition-colors ${
            stats.pending > 0
              ? "border-amber-300 bg-amber-50 dark:bg-amber-950/30 hover:bg-amber-100 dark:hover:bg-amber-950/50"
              : "bg-background hover:bg-muted/50"
          }`}
        >
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">{stats.total}</span>
              <span className="text-muted-foreground">threads</span>
            </div>
            {stats.pending > 0 && (
              <div className="flex items-center gap-1.5">
                <Clock className="h-4 w-4 text-amber-600" />
                <span className="font-medium text-amber-600">{stats.pending} pending</span>
                {stats.stale_pending > 0 && (
                  <span className="text-xs text-red-600">({stats.stale_pending} stale)</span>
                )}
              </div>
            )}
            {stats.open_actions > 0 && (
              <a
                href="/jobs"
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1.5 hover:underline"
              >
                <MessageSquare className="h-4 w-4 text-blue-600" />
                <span className="text-blue-600">{stats.open_actions} open jobs</span>
              </a>
            )}
          </div>
        </button>
      )}

      {/* Needs Attention */}
      {filter === "clients" && pendingThreads.length > 0 && (
        <Card className="shadow-sm border-amber-200 dark:border-amber-800">
          <CardHeader className="py-2 px-4">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
              Needs Attention
              <Badge variant="outline" className="border-amber-400 text-amber-600 ml-1 text-[10px] px-1.5">
                {pendingThreads.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 pt-0">
            <div className="space-y-1">
              {pendingThreads.slice(0, 5).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedThreadId(t.id)}
                  className="w-full text-left flex items-center gap-3 py-1.5 px-2 rounded hover:bg-amber-50 dark:hover:bg-amber-950/30 text-sm transition-colors"
                >
                  <span className="font-medium truncate flex-shrink-0 w-32">
                    {t.customer_name || t.contact_email.split("@")[0]}
                  </span>
                  <span className="text-muted-foreground truncate flex-1">
                    {t.last_snippet || t.subject || "No subject"}
                  </span>
                  <span className="text-xs text-muted-foreground flex-shrink-0">
                    {formatTime(t.last_message_at)}
                  </span>
                </button>
              ))}
              {pendingThreads.length > 5 && (
                <p className="text-xs text-muted-foreground pl-2">+ {pendingThreads.length - 5} more</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters + Search */}
      <div className="flex items-center gap-2 flex-wrap">
        {STATUS_FILTERS.map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            className="capitalize"
            onClick={() => handleFilterChange(f)}
          >
            {f}
          </Button>
        ))}
        <div className="h-5 w-px bg-border mx-1" />
        <Button
          variant={assignFilter === "mine" ? "default" : "outline"}
          size="sm"
          onClick={() => { setAssignFilter(assignFilter === "mine" ? "all" : "mine"); setPage(0); }}
        >
          <User className="h-3.5 w-3.5 mr-1" />
          Mine
        </Button>
        <div className="flex items-center gap-1 ml-auto">
          <Input
            placeholder="Search..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
            className="h-8 w-48 text-sm"
          />
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleSearch}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Thread table */}
      <Card className="shadow-sm">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide w-24">Time</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">From</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Subject</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-16 text-center">Msgs</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-28">Category</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-24">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-12">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : threads.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-12 text-muted-foreground">
                  No threads found
                </TableCell>
              </TableRow>
            ) : (
              threads.map((t, i) => (
                <TableRow
                  key={t.id}
                  className={`cursor-pointer transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 ${
                    i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""
                  } ${t.has_pending ? "border-l-4 border-l-amber-400" : ""} ${t.is_unread ? "font-medium" : ""}`}
                  onClick={() => setSelectedThreadId(t.id)}
                >
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      {t.is_unread && <span className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0" />}
                      {formatTime(t.last_message_at)}
                    </div>
                  </TableCell>
                  <TableCell className="truncate max-w-[180px]">
                    <div className="flex items-center gap-1.5">
                      <span className={t.is_unread ? "font-semibold" : t.has_pending ? "font-medium" : ""}>
                        {t.customer_name || t.contact_email.split("@")[0]}
                      </span>
                      {t.visibility_permission && (
                        <span title={`Restricted: ${t.visibility_permission}`}>
                          <Lock className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                        </span>
                      )}
                      {t.assigned_to_name && (
                        <Badge variant="secondary" className="text-[10px] px-1.5 flex-shrink-0">
                          {t.assigned_to_user_id === user?.id ? "Mine" : t.assigned_to_name}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="truncate max-w-[250px] text-sm">
                    <span className={t.is_unread ? "font-semibold" : t.has_pending ? "" : "text-muted-foreground"}>
                      {t.subject || t.last_snippet || "No subject"}
                    </span>
                  </TableCell>
                  <TableCell className="text-center">
                    {t.message_count > 1 && (
                      <Badge variant="secondary" className="text-[10px] px-1.5">
                        {t.message_count}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <CategoryBadge category={t.category} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <StatusBadge status={t.status} />
                      <UrgencyBadge urgency={t.urgency} />
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            {Array.from({ length: totalPages }, (_, i) => {
              // Show first, last, and pages around current
              if (i === 0 || i === totalPages - 1 || Math.abs(i - page) <= 1) {
                return (
                  <Button
                    key={i}
                    variant={i === page ? "default" : "ghost"}
                    size="icon"
                    className="h-8 w-8 text-xs"
                    onClick={() => setPage(i)}
                  >
                    {i + 1}
                  </Button>
                );
              }
              // Show ellipsis between gaps
              if (i === 1 && page > 2) return <span key={i} className="px-1">…</span>;
              if (i === totalPages - 2 && page < totalPages - 3) return <span key={i} className="px-1">…</span>;
              return null;
            })}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Thread detail sheet */}
      <Sheet open={!!selectedThreadId} onOpenChange={(open) => { if (!open) { setSelectedThreadId(null); loadThreads(); } }}>
        <SheetContent className="w-full sm:max-w-lg flex flex-col h-full px-4 sm:px-6">
          <SheetHeader className="flex-shrink-0">
            <SheetTitle className="text-base">Conversation</SheetTitle>
          </SheetHeader>
          {selectedThreadId && (
            <div className="flex-1 overflow-hidden">
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={() => setSelectedThreadId(null)}
                onAction={() => { loadThreads(); loadStats(); }}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>

      <InboxSettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
