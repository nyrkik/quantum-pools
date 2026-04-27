"use client";

/**
 * Promise tracker dashboard widget.
 *
 * Surfaces threads where the customer made a follow-up promise and
 * went silent past the agreed window. Backend computes
 * is_overdue server-side; the widget shows up to 5 most-overdue rows
 * with one-click "Open" / "Snooze 7d" / "Resolved" actions. Renders
 * nothing when no threads are awaiting (empty card hidden).
 *
 * Permission: requires inbox.manage. Renders nothing when user lacks it.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Clock, Loader2, Check, BellOff, ArrowRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
import { toast } from "sonner";


interface AwaitingItem {
  thread_id: string;
  subject: string | null;
  contact_email: string;
  customer_name: string | null;
  awaiting_reply_until: string;
  is_overdue: boolean;
  last_message_at: string | null;
  last_inbound_snippet: string | null;
}


function daysSince(iso: string): number {
  const ms = Date.now() - new Date(iso).getTime();
  return Math.floor(ms / (1000 * 60 * 60 * 24));
}


export function AwaitingReplyWidget() {
  const perms = usePermissions();
  const canManage = perms.can("inbox.manage");
  const [items, setItems] = useState<AwaitingItem[] | null>(null);
  const [overdueCount, setOverdueCount] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!canManage) return;
    setLoading(true);
    try {
      const res = await api.get<{
        items: AwaitingItem[];
        overdue_count: number;
        total: number;
      }>("/v1/inbox/awaiting-reply");
      // Show overdue first; cap at 5 in the widget
      const sorted = [...res.items].sort((a, b) => {
        if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
        return new Date(a.awaiting_reply_until).getTime() -
               new Date(b.awaiting_reply_until).getTime();
      });
      setItems(sorted.slice(0, 5));
      setOverdueCount(res.overdue_count);
    } catch (e) {
      // Silent fail — widget hides when items=null and not overdue
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => { refresh(); }, [refresh]);

  async function snooze(threadId: string) {
    setBusyId(threadId);
    try {
      const newUntil = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
      await api.patch(`/v1/admin/agent-threads/${threadId}/awaiting-reply`, {
        until: newUntil,
      });
      toast.success("Snoozed 7 days");
      await refresh();
    } catch (err) {
      toast.error((err as Error).message || "Snooze failed");
    } finally {
      setBusyId(null);
    }
  }

  async function resolve(threadId: string) {
    setBusyId(threadId);
    try {
      await api.patch(`/v1/admin/agent-threads/${threadId}/awaiting-reply`, {
        until: null,
      });
      toast.success("Marked resolved");
      await refresh();
    } catch (err) {
      toast.error((err as Error).message || "Resolve failed");
    } finally {
      setBusyId(null);
    }
  }

  if (!canManage) return null;
  if (!items || items.length === 0) return null;  // hide when empty

  return (
    <Card className="shadow-sm">
      <CardHeader className="bg-primary text-primary-foreground px-4 py-2.5">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Clock className="h-4 w-4 opacity-70" />
          Awaiting customer reply
          {overdueCount > 0 ? (
            <Badge variant="secondary" className="ml-auto border-amber-400 text-amber-700">
              {overdueCount} past due
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-2">
        {loading && items === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : (
          items.map((it) => {
            const ageDays = it.last_message_at ? daysSince(it.last_message_at) : null;
            return (
              <div
                key={it.thread_id}
                className={`rounded-md border ${it.is_overdue ? "border-l-4 border-l-amber-400" : ""} bg-muted/30 p-3`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm">
                        {it.customer_name || it.contact_email}
                      </span>
                      {ageDays !== null ? (
                        <Badge variant="outline" className="text-xs">
                          {ageDays}d ago
                        </Badge>
                      ) : null}
                      {it.is_overdue ? (
                        <Badge variant="outline" className="text-xs border-amber-400 text-amber-700">
                          past due
                        </Badge>
                      ) : null}
                    </div>
                    <div className="text-xs text-muted-foreground truncate mt-0.5">
                      {it.subject || "(no subject)"}
                    </div>
                    {it.last_inbound_snippet ? (
                      <div className="text-xs text-muted-foreground italic mt-1 line-clamp-2">
                        “{it.last_inbound_snippet.slice(0, 140)}”
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 justify-end mt-2">
                  <Link
                    href={`/inbox?thread=${it.thread_id}`}
                    className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground gap-1 px-2"
                    title="Open thread"
                  >
                    <ArrowRight className="h-3.5 w-3.5" />
                    Open
                  </Link>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busyId === it.thread_id}
                    onClick={() => snooze(it.thread_id)}
                    className="text-xs text-muted-foreground"
                    title="Snooze 7 days"
                  >
                    {busyId === it.thread_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <BellOff className="h-3.5 w-3.5 mr-1" />
                    )}
                    Snooze 7d
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busyId === it.thread_id}
                    onClick={() => resolve(it.thread_id)}
                    className="text-xs text-muted-foreground hover:text-green-600"
                    title="Mark resolved"
                  >
                    <Check className="h-3.5 w-3.5 mr-1" />
                    Resolved
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
