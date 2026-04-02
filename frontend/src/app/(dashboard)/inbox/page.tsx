"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
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
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
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
  ArrowDownLeft,
  ArrowUpRight,
} from "lucide-react";
import { useCompose } from "@/components/email/compose-provider";
import { PageLayout } from "@/components/layout/page-layout";
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
  const router = useRouter();
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
    <PageLayout
      title="Inbox"
      icon={<Bot className="h-5 w-5 text-muted-foreground" />}
      action={
        <Button
          size="sm"
          className="gap-1.5"
          onClick={() => openCompose()}
        >
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
      {/* Filters: tabs + assign + search */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f}
              variant={filter === f ? "default" : "outline"}
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={() => handleFilterChange(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </Button>
          ))}
        </div>
        <Button
          variant={assignFilter === "mine" ? "default" : "outline"}
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => { setAssignFilter(assignFilter === "mine" ? "all" : "mine"); setPage(0); }}
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
              <TableHead className="text-xs font-medium uppercase tracking-wide hidden sm:table-cell">Subject</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-16 text-center hidden md:table-cell">Msgs</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-28 hidden lg:table-cell">Category</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-24 hidden sm:table-cell">Status</TableHead>
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
                  <TableCell className="max-w-[200px]">
                    <div className="flex items-center gap-1.5">
                      <span className={`truncate ${t.is_unread ? "font-semibold" : ""}`}>
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
                      {/* Mobile: inline status icons */}
                      <span className="flex items-center gap-0.5 sm:hidden flex-shrink-0 ml-auto">
                        <StatusBadge status={t.status} />
                        <UrgencyBadge urgency={t.urgency} />
                      </span>
                    </div>
                    {t.customer_address && (
                      <p className="text-[10px] text-muted-foreground truncate">{t.customer_address}</p>
                    )}
                    {t.contact_name && (
                      <p className="text-[10px] text-muted-foreground truncate">Contact: {t.contact_name}</p>
                    )}
                    {/* Mobile: subject below name */}
                    <div className="flex items-center gap-1 sm:hidden mt-0.5">
                      {t.last_direction === "outbound" ? (
                        <span className="flex-shrink-0"><ArrowUpRight className="h-3 w-3 text-blue-500" /></span>
                      ) : (
                        <span className="flex-shrink-0"><ArrowDownLeft className="h-3 w-3 text-green-600" /></span>
                      )}
                      <span className={`text-xs truncate ${t.is_unread ? "font-semibold" : "text-muted-foreground"}`}>
                        {t.subject || t.last_snippet || "No subject"}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[250px] text-sm hidden sm:table-cell">
                    <div className="flex items-center gap-1.5">
                      {t.last_direction === "outbound" ? (
                        <span className="flex-shrink-0" title="Last: sent"><ArrowUpRight className="h-3 w-3 text-blue-500" /></span>
                      ) : (
                        <span className="flex-shrink-0" title="Last: received"><ArrowDownLeft className="h-3 w-3 text-green-600" /></span>
                      )}
                      <span className={`truncate ${t.is_unread ? "font-semibold" : t.has_pending ? "" : "text-muted-foreground"}`}>
                        {t.subject || t.last_snippet || "No subject"}
                      </span>
                    </div>
                    {t.case_id && (
                      <Badge
                        variant="outline"
                        className="text-[9px] px-1 ml-1.5 border-blue-300 text-blue-600 cursor-pointer hover:bg-blue-50"
                        onClick={(e) => { e.stopPropagation(); router.push(`/cases/${t.case_id}`); }}
                      >
                        Case
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-center hidden md:table-cell">
                    {t.message_count > 1 && (
                      <Badge variant="secondary" className="text-[10px] px-1.5">
                        {t.message_count}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">
                    <CategoryBadge category={t.category} />
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
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

      {/* Thread detail overlay */}
      <Overlay open={!!selectedThreadId} onOpenChange={(open) => { if (!open) { setSelectedThreadId(null); loadThreads(); } }}>
        <OverlayContent className="max-w-xl">
          <OverlayHeader>
            <OverlayTitle>Conversation</OverlayTitle>
          </OverlayHeader>
          {selectedThreadId && (
            <OverlayBody className="p-0">
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={() => setSelectedThreadId(null)}
                onAction={() => { loadThreads(); loadStats(); }}
              />
            </OverlayBody>
          )}
        </OverlayContent>
      </Overlay>

      <InboxSettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </PageLayout>
  );
}
