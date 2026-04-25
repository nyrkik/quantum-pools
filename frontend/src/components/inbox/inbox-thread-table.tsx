"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import {
  Loader2,
  Lock,
  ArrowDownLeft,
  ArrowUpRight,
  Eye,
  EyeOff,
  FolderInput,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";
import { StatusBadge, UrgencyBadge, CategoryBadge, AIBadge } from "@/components/inbox/inbox-badges";
import { SENDER_TAG_STYLES } from "./contact-learning-modal";
import type { InboxFolderItem } from "./inbox-folder-sidebar";

interface InboxThreadTableProps {
  threads: Thread[];
  loading: boolean;
  currentUserId: string;
  onSelectThread: (id: string) => void;
  selectedThreadId?: string | null;
  onBulkAction?: () => void;
  compact?: boolean;
  groupByClient?: boolean;
}

export function InboxThreadTable({ threads, loading, currentUserId, onSelectThread, selectedThreadId, onBulkAction, compact, groupByClient }: InboxThreadTableProps) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [acting, setActing] = useState(false);
  const [folders, setFolders] = useState<InboxFolderItem[]>([]);

  // Clear selection when threads change
  useEffect(() => { setSelected(new Set()); }, [threads]);

  // Load folders for move-to menu
  useEffect(() => {
    api.get<{ folders: InboxFolderItem[] }>("/v1/inbox-folders")
      .then((d) => setFolders(d.folders))
      .catch(() => {});
  }, []);

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === threads.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(threads.map((t) => t.id)));
    }
  };

  const ids = Array.from(selected);

  const bulkAction = async (action: string, extra?: Record<string, unknown>) => {
    if (ids.length === 0) return;
    setActing(true);
    try {
      await api.post(`/v1/admin/agent-threads/bulk/${action}`, { thread_ids: ids, ...extra });
      toast.success(`${ids.length} thread${ids.length > 1 ? "s" : ""} updated`);
      setSelected(new Set());
      onBulkAction?.();
    } catch {
      toast.error("Bulk action failed");
    } finally {
      setActing(false);
    }
  };

  const [bulkAllSenders, setBulkAllSenders] = useState(false);

  const bulkMoveSenders = async (folderId: string | null) => {
    if (ids.length === 0) return;
    // Get unique sender emails from selected threads
    const senderEmails = [...new Set(
      threads.filter((t) => selected.has(t.id)).map((t) => t.contact_email)
    )];
    setActing(true);
    try {
      for (const email of senderEmails) {
        await api.post("/v1/inbox-folders/move-sender", { sender_email: email, folder_id: folderId });
      }
      toast.success(`All threads from ${senderEmails.length} sender${senderEmails.length > 1 ? "s" : ""} moved`);
      setSelected(new Set());
      setBulkAllSenders(false);
      onBulkAction?.();
    } catch {
      toast.error("Failed to move");
    } finally {
      setActing(false);
    }
  };

  // Group threads by client when enabled
  const groupedThreads = (() => {
    if (!groupByClient) return null;
    const groups: { label: string; threads: Thread[] }[] = [];
    const byClient = new Map<string, Thread[]>();
    for (const t of threads) {
      const key = t.customer_name || t.contact_email;
      if (!byClient.has(key)) byClient.set(key, []);
      byClient.get(key)!.push(t);
    }
    // Sort groups: groups with pending threads first, then alphabetical
    const entries = [...byClient.entries()].sort((a, b) => {
      const aPending = a[1].some((t) => t.has_pending);
      const bPending = b[1].some((t) => t.has_pending);
      if (aPending !== bPending) return aPending ? -1 : 1;
      return a[0].localeCompare(b[0]);
    });
    for (const [label, groupThreads] of entries) {
      groups.push({ label, threads: groupThreads });
    }
    return groups;
  })();

  const hasSelection = selected.size > 0;

  return (
    <>
      {/* Floating bulk action bar */}
      {hasSelection && (
        <div className="hidden sm:flex items-center gap-2 px-3 py-2 mb-2 rounded-lg border bg-background shadow-sm">
          <span className="text-xs font-medium text-muted-foreground">
            {selected.size} selected
          </span>
          <div className="h-4 w-px bg-border" />
          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={() => bulkAction("mark-read")} disabled={acting}>
            <Eye className="h-3 w-3" /> Mark Read
          </Button>
          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={() => bulkAction("mark-unread")} disabled={acting}>
            <EyeOff className="h-3 w-3" /> Mark Unread
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" disabled={acting}>
                <FolderInput className="h-3 w-3" /> Move to
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <div className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
                  <Checkbox checked={bulkAllSenders} onCheckedChange={(v) => setBulkAllSenders(!!v)} />
                  All from selected senders
                </label>
              </div>
              <div className="h-px bg-border my-1" />
              <DropdownMenuItem onClick={() => bulkAllSenders ? bulkMoveSenders(null) : bulkAction("move", { folder_id: null })}>
                Inbox
              </DropdownMenuItem>
              {folders.filter((f) => f.system_key !== "inbox").map((f) => (
                <DropdownMenuItem key={f.id} onClick={() => bulkAllSenders ? bulkMoveSenders(f.id) : bulkAction("move", { folder_id: f.id })}>
                  {f.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => bulkAction("spam")}
            disabled={acting}
            title="Mark as spam — suppresses sender for all users and moves all their threads"
          >
            <ShieldAlert className="h-3 w-3" /> Spam
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => bulkAction("not-spam")}
            disabled={acting}
            title="Not spam — removes sender suppression and moves all their threads to Inbox"
          >
            <ShieldCheck className="h-3 w-3" /> Not Spam
          </Button>
          {acting && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        </div>
      )}

      <Card className="shadow-sm hidden sm:block overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              {!compact && (
                <TableHead className="w-8 px-2">
                  <Checkbox
                    checked={threads.length > 0 && selected.size === threads.length}
                    onCheckedChange={toggleAll}
                    aria-label="Select all"
                  />
                </TableHead>
              )}
              <TableHead className="text-xs font-medium uppercase tracking-wide w-20">Time</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">From</TableHead>
              {!compact && <TableHead className="text-xs font-medium uppercase tracking-wide hidden sm:table-cell">Subject</TableHead>}
              {!compact && <TableHead className="text-xs font-medium uppercase tracking-wide w-16 text-center hidden md:table-cell">Msgs</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={compact ? 3 : 5} className="text-center py-12">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : threads.length === 0 ? (
              <TableRow>
                <TableCell colSpan={compact ? 3 : 5} className="text-center py-12 text-muted-foreground">
                  No threads found
                </TableCell>
              </TableRow>
            ) : (
              (() => {
                const colSpan = compact ? 2 : 5;
                const renderRow = (t: Thread, i: number) => {
                  const isSelected = t.id === selectedThreadId;
                  return (
                  <TableRow
                    key={t.id}
                    className={`cursor-pointer transition-colors touch-manipulation relative ${
                      isSelected
                        ? "bg-blue-100 dark:bg-blue-950/50 hover:bg-blue-100 dark:hover:bg-blue-950/50"
                        : t.has_pending
                        ? "bg-amber-50 dark:bg-amber-950/30 hover:bg-blue-50 dark:hover:bg-blue-950"
                        : `${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""} hover:bg-blue-50 dark:hover:bg-blue-950`
                    } ${t.is_unread ? "font-medium" : ""}`}
                    onClick={() => onSelectThread(t.id)}
                    style={
                      isSelected
                        ? { boxShadow: "inset 4px 0 0 0 #3b82f6" }
                        : t.has_pending
                        ? { boxShadow: "inset 4px 0 0 0 #f59e0b" }
                        : undefined
                    }
                  >
                    {!compact && (
                      <TableCell className="px-2" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={selected.has(t.id)}
                          onCheckedChange={() => toggleOne(t.id)}
                          aria-label={`Select ${t.subject || t.contact_email}`}
                        />
                      </TableCell>
                    )}
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        {t.is_unread && <span className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0" />}
                        {formatTime(t.last_message_at)}
                      </div>
                    </TableCell>
                    <TableCell className={compact ? "max-w-[250px]" : "max-w-[200px]"}>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`truncate ${t.is_unread ? "font-semibold" : ""}`}
                          title={t.contact_email}
                        >
                          {t.customer_name || t.contact_email}
                          {t.customer_name && t.contact_person_name && (
                            <span className="font-normal text-muted-foreground"> ({t.contact_person_name})</span>
                          )}
                        </span>
                        {t.visibility_role_slugs && t.visibility_role_slugs.length > 0 && (
                          <span title={`Visible to: ${t.visibility_role_slugs.join(", ")}`}>
                            <Lock className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                          </span>
                        )}
                        {t.assigned_to_name && (
                          <Badge variant="secondary" className="text-[10px] px-1.5 flex-shrink-0">
                            {t.assigned_to_user_id === currentUserId ? "Mine" : t.assigned_to_name}
                          </Badge>
                        )}
                        <span className="flex items-center gap-0.5 sm:hidden flex-shrink-0 ml-auto">
                          <StatusBadge status={t.status} />
                          <UrgencyBadge urgency={t.urgency} />
                        </span>
                      </div>
                      <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                        {/* Standard order: sender tag → category → status → stale warning.
                            Reading flow: "who is this?" → "what kind?" → "what state?" → "needs attention?" */}
                        {(() => {
                          const effectiveTag = t.matched_customer_id ? "client" : t.sender_tag;
                          if (!effectiveTag) return null;
                          const style = SENDER_TAG_STYLES[effectiveTag];
                          if (!style) return null;
                          return (
                            <span className={`px-1.5 py-0 rounded text-[9px] font-medium ${style.bg} ${style.text}`}>
                              {effectiveTag.charAt(0).toUpperCase() + effectiveTag.slice(1)}
                            </span>
                          );
                        })()}
                        <CategoryBadge category={t.category} />
                        <StatusBadge status={t.status} />
                        <AIBadge show={t.was_auto_handled} />
                        {t.has_pending && t.last_message_at &&
                          (Date.now() - new Date(t.last_message_at).getTime()) > 30 * 60 * 1000 && (
                          <span className="px-1.5 py-0 rounded text-[9px] font-medium bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400">
                            Stale
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 sm:hidden mt-0.5">
                        {t.last_direction === "outbound" ? (
                          <span className="flex-shrink-0"><ArrowUpRight className="h-3 w-3 text-blue-500" /></span>
                        ) : (
                          <span className="flex-shrink-0"><ArrowDownLeft className="h-3 w-3 text-green-600" /></span>
                        )}
                        {/* FB-50: who on the team replied last. */}
                        {t.last_direction === "outbound" && t.last_outbound_from_name && (
                          <span className="text-[10px] text-muted-foreground shrink-0">
                            {t.last_outbound_from_name.split(" ")[0]}:
                          </span>
                        )}
                        <span className={`text-xs truncate ${t.is_unread ? "font-semibold" : "text-muted-foreground"}`}>
                          {t.subject || t.last_snippet || "No subject"}
                        </span>
                      </div>
                    </TableCell>
                    {!compact && (
                      <TableCell className="max-w-[250px] text-sm hidden sm:table-cell">
                        <div className="flex items-center gap-1.5">
                          {t.last_direction === "outbound" ? (
                            <span className="flex-shrink-0" title="Last: sent"><ArrowUpRight className="h-3 w-3 text-blue-500" /></span>
                          ) : (
                            <span className="flex-shrink-0" title="Last: received"><ArrowDownLeft className="h-3 w-3 text-green-600" /></span>
                          )}
                          {/* FB-50: who on the team replied last. */}
                          {t.last_direction === "outbound" && t.last_outbound_from_name && (
                            <span className="text-xs text-muted-foreground shrink-0">
                              {t.last_outbound_from_name.split(" ")[0]}:
                            </span>
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
                    )}
                    {!compact && (
                      <TableCell className="text-center hidden md:table-cell">
                        {t.message_count > 1 && (
                          <Badge variant="secondary" className="text-[10px] px-1.5">
                            {t.message_count}
                          </Badge>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                  );
                };

                if (groupedThreads) {
                  return groupedThreads.map((group) => (
                    <React.Fragment key={group.label}>
                      <TableRow>
                        <TableCell
                          colSpan={colSpan}
                          className="bg-primary text-primary-foreground px-4 py-1.5 text-xs font-medium uppercase tracking-wide"
                        >
                          {group.label}
                          <span className="ml-2 opacity-70">{group.threads.length}</span>
                        </TableCell>
                      </TableRow>
                      {group.threads.map((t, i) => renderRow(t, i))}
                    </React.Fragment>
                  ));
                }
                return threads.map((t, i) => renderRow(t, i));
              })()
            )}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
