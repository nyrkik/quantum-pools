"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Mail } from "lucide-react";
import { StatusBadge, UrgencyBadge } from "@/components/inbox/inbox-badges";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";

interface CommunicationsTileProps {
  customerId: string;
}

export function CommunicationsTile({ customerId }: CommunicationsTileProps) {
  const router = useRouter();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ items: Thread[] }>(
        `/v1/admin/agent-threads?customer_id=${customerId}&limit=3`
      )
      .then((d) => {
        if (!cancelled) setThreads(d.items || []);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => { cancelled = true; };
  }, [customerId]);

  if (!loaded) return null;

  return (
    <Card
      className="shadow-sm cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => router.push(`/inbox?customer_id=${customerId}`)}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <span className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-muted-foreground" />
            Communications
          </span>
          {threads.length > 0 && (
            <span className="text-xs text-muted-foreground font-normal">View all</span>
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
                className="flex items-center gap-2 py-2 text-sm"
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
                  <UrgencyBadge urgency={t.urgency} />
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
  );
}
