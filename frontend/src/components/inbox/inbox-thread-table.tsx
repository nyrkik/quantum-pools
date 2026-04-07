"use client";

import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Loader2, Lock, ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";
import { StatusBadge, UrgencyBadge, CategoryBadge } from "@/components/inbox/inbox-badges";

interface InboxThreadTableProps {
  threads: Thread[];
  loading: boolean;
  currentUserId: string;
  onSelectThread: (id: string) => void;
}

export function InboxThreadTable({ threads, loading, currentUserId, onSelectThread }: InboxThreadTableProps) {
  const router = useRouter();

  return (
    <Card className="shadow-sm hidden sm:block">
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
                className={`cursor-pointer transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 touch-manipulation ${
                  i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""
                } ${t.has_pending ? "border-l-4 border-l-amber-400" : ""} ${t.is_unread ? "font-medium" : ""}`}
                onClick={() => onSelectThread(t.id)}
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
                        {t.assigned_to_user_id === currentUserId ? "Mine" : t.assigned_to_name}
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
  );
}
