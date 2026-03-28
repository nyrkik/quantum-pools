"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, Mail, Plus } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { formatTime } from "@/lib/format";
import { useCompose } from "@/components/email/compose-provider";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";
import { StatusBadge, UrgencyBadge } from "@/components/inbox/inbox-badges";
import type { Thread } from "@/types/agent";

interface CommunicationSectionProps {
  customerId: string;
  customerEmail?: string;
  customerName?: string;
}

export function CommunicationSection({ customerId, customerEmail, customerName }: CommunicationSectionProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const { openCompose } = useCompose();

  const loadThreads = useCallback(() => {
    setLoading(true);
    api.get<{ items: Thread[] }>(`/v1/admin/agent-threads?customer_id=${customerId}&limit=10`)
      .then((data) => setThreads(data.items ?? []))
      .catch(() => setThreads([]))
      .finally(() => setLoading(false));
  }, [customerId]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  const handleNewEmail = () => {
    openCompose({
      to: customerEmail,
      customerId,
      customerName,
    });
  };

  const handleThreadAction = () => {
    loadThreads();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Header actions */}
      <div className="flex items-center justify-end">
        {customerEmail && (
          <Button variant="outline" size="sm" onClick={handleNewEmail}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            New Email
          </Button>
        )}
      </div>

      {/* Thread list */}
      {threads.length === 0 ? (
        <div className="text-center py-6">
          <Mail className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
          <p className="text-sm text-muted-foreground">No email threads with this customer</p>
        </div>
      ) : (
        <div className="space-y-1">
          {threads.map((thread) => (
            <button
              key={thread.id}
              onClick={() => setSelectedThreadId(thread.id)}
              className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors text-left border"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-sm font-medium truncate">
                    {thread.contact_email}
                  </span>
                  {thread.is_unread && (
                    <span className="h-2 w-2 rounded-full bg-blue-500 shrink-0" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground truncate">
                  {thread.subject || thread.last_snippet || "No subject"}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className="text-[10px] text-muted-foreground">
                  {formatTime(thread.last_message_at)}
                </span>
                <div className="flex items-center gap-1">
                  <StatusBadge status={thread.status} />
                  <UrgencyBadge urgency={thread.urgency} />
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Thread detail sheet */}
      <Sheet open={!!selectedThreadId} onOpenChange={(open) => { if (!open) setSelectedThreadId(null); }}>
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Thread</SheetTitle>
          </SheetHeader>
          {selectedThreadId && (
            <ThreadDetailSheet
              threadId={selectedThreadId}
              onClose={() => setSelectedThreadId(null)}
              onAction={handleThreadAction}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
