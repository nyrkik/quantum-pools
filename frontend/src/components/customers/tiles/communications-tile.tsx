"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Mail } from "lucide-react";
import { StatusBadge, UrgencyBadge } from "@/components/inbox/inbox-badges";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";

interface CommunicationsTileProps {
  customerId: string;
}

export function CommunicationsTile({ customerId }: CommunicationsTileProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);

  const load = () => {
    api.get<{ items: Thread[] }>(`/v1/admin/agent-threads?customer_id=${customerId}&limit=5`)
      .then((d) => setThreads(d.items || []))
      .catch(() => {})
      .finally(() => setLoaded(true));
  };

  useEffect(() => { load(); }, [customerId]);

  if (!loaded) return null;

  return (
    <>
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm font-semibold">
            <span className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-muted-foreground" />
              Communications
            </span>
            {threads.length > 0 && (
              <Link href={`/inbox?customer_id=${customerId}`} className="text-xs text-muted-foreground hover:text-primary font-normal">
                View all →
              </Link>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {threads.length === 0 ? (
            <p className="text-sm text-muted-foreground">No emails</p>
          ) : (
            <div className="divide-y">
              {threads.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center gap-2 py-2 text-sm cursor-pointer hover:bg-muted/50 -mx-2 px-2 rounded transition-colors"
                  onClick={() => setSelectedThreadId(t.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium text-xs">
                      {t.subject || t.last_snippet || "No subject"}
                      {t.is_unread && (
                        <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-blue-500 align-middle" />
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <StatusBadge status={t.status} />
                    <span className="text-[10px] text-muted-foreground">
                      {formatTime(t.last_message_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Sheet open={!!selectedThreadId} onOpenChange={(open) => { if (!open) { setSelectedThreadId(null); load(); } }}>
        <SheetContent className="w-full sm:max-w-lg flex flex-col h-full px-4 sm:px-6">
          <SheetHeader className="flex-shrink-0">
            <SheetTitle className="text-base">Conversation</SheetTitle>
          </SheetHeader>
          {selectedThreadId && (
            <div className="flex-1 overflow-hidden">
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={() => setSelectedThreadId(null)}
                onAction={() => load()}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
