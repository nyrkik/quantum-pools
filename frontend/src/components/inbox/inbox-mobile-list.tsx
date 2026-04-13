"use client";

import { Badge } from "@/components/ui/badge";
import { Loader2, ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";
import { StatusBadge, UrgencyBadge } from "@/components/inbox/inbox-badges";

interface InboxMobileListProps {
  threads: Thread[];
  loading: boolean;
  currentUserId: string;
}

export function InboxMobileList({ threads, loading, currentUserId }: InboxMobileListProps) {
  return (
    <div className="sm:hidden space-y-1">
      {loading ? (
        <div className="text-center py-12"><Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" /></div>
      ) : threads.length === 0 ? (
        <p className="text-center py-12 text-muted-foreground text-sm">No threads found</p>
      ) : threads.map((t) => (
        <a
          key={t.id}
          href={`/inbox/${t.id}`}
          className={`block w-full text-left px-3 py-2.5 rounded-lg border active:bg-blue-50 transition-colors ${
            t.has_pending ? "bg-amber-50 dark:bg-amber-950/30 border-l-4 border-l-amber-500" : "bg-background"
          } ${t.is_unread ? "font-medium" : ""}`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              {t.is_unread && <span className="h-2 w-2 rounded-full bg-blue-500 shrink-0" />}
              <span className={`text-sm truncate ${t.is_unread ? "font-semibold" : ""}`}>
                {t.customer_name || t.contact_email.split("@")[0]}
              </span>
              {t.assigned_to_name && (
                <Badge variant="secondary" className="text-[10px] px-1.5 shrink-0">
                  {t.assigned_to_user_id === currentUserId ? "Mine" : t.assigned_to_name}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <StatusBadge status={t.status} />
              <UrgencyBadge urgency={t.urgency} />
              <span className="text-[10px] text-muted-foreground">{formatTime(t.last_message_at)}</span>
            </div>
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            {t.last_direction === "outbound" ? (
              <ArrowUpRight className="h-3 w-3 text-blue-500 shrink-0" />
            ) : (
              <ArrowDownLeft className="h-3 w-3 text-green-600 shrink-0" />
            )}
            <span className={`text-xs truncate ${t.is_unread ? "font-semibold" : "text-muted-foreground"}`}>
              {t.subject || t.last_snippet || "No subject"}
            </span>
          </div>
        </a>
      ))}
    </div>
  );
}
