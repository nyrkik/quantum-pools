"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import { Button } from "@/components/ui/button";
import { Mail, SquarePen } from "lucide-react";
import { StatusBadge, UrgencyBadge } from "@/components/inbox/inbox-badges";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";
import { useCompose } from "@/components/email/compose-provider";
import { formatTime } from "@/lib/format";
import type { Thread } from "@/types/agent";

interface CommunicationsTileProps {
  customerId: string;
  customerEmail?: string | null;
  customerName?: string;
}

export function CommunicationsTile({ customerId, customerEmail, customerName }: CommunicationsTileProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const { openCompose } = useCompose();

  const load = () => {
    api.get<{ items: Thread[] }>(`/v1/admin/agent-threads?customer_id=${customerId}&limit=5`)
      .then((d) => setThreads(d.items || []))
      .catch(() => {})
      .finally(() => setLoaded(true));
  };

  useEffect(() => { load(); }, [customerId]);

  const handleNewEmail = () => {
    openCompose({
      to: customerEmail || undefined,
      customerId,
      customerName,
    });
  };

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
            {customerEmail && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNewEmail} title="New email">
                <SquarePen className="h-3.5 w-3.5" />
              </Button>
            )}
          </CardTitle>
          {customerEmail && (
            <div className="space-y-0.5">
              {customerEmail.split(",").map((email) => (
                <p key={email.trim()} className="text-xs text-muted-foreground">{email.trim()}</p>
              ))}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {threads.length === 0 ? (
            <p className="text-sm text-muted-foreground">No emails</p>
          ) : (
            <div className="space-y-1">
              {threads.map((t) => (
                <div
                  key={t.id}
                  className="flex items-start gap-2 py-2 cursor-pointer hover:bg-muted/50 -mx-2 px-2 rounded transition-colors"
                  onClick={() => setSelectedThreadId(t.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium">
                      {t.subject || "No subject"}
                      {t.is_unread && (
                        <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-blue-500 align-middle" />
                      )}
                    </p>
                    {t.last_snippet && (
                      <p className="text-xs text-muted-foreground mt-0.5 break-words whitespace-pre-line">{t.last_snippet}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
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

      <Overlay open={!!selectedThreadId} onOpenChange={(open) => { if (!open) { setSelectedThreadId(null); load(); } }}>
        <OverlayContent className="max-w-xl">
          <OverlayHeader>
            <OverlayTitle>Conversation</OverlayTitle>
          </OverlayHeader>
          {selectedThreadId && (
            <OverlayBody className="p-0">
              <ThreadDetailSheet
                threadId={selectedThreadId}
                onClose={() => setSelectedThreadId(null)}
                onAction={() => load()}
              />
            </OverlayBody>
          )}
        </OverlayContent>
      </Overlay>
    </>
  );
}
