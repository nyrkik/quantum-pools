"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Loader2,
  Mail,
  Plug,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Clock,
} from "lucide-react";

interface EmailIntegration {
  id: string;
  type: "managed" | "gmail_api" | "ms_graph" | "forwarding" | "manual";
  status: "setup_required" | "connecting" | "connected" | "error" | "disconnected";
  account_email: string | null;
  inbound_sender_address: string | null;
  outbound_provider: string | null;
  is_primary: boolean;
  last_sync_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  created_at: string | null;
}

interface ListResponse {
  integrations: EmailIntegration[];
}

const TYPE_LABELS: Record<EmailIntegration["type"], string> = {
  managed: "Managed (Postmark + Cloudflare)",
  gmail_api: "Gmail",
  ms_graph: "Microsoft 365",
  forwarding: "Email Forwarding",
  manual: "Manual",
};

function statusBadge(status: EmailIntegration["status"]) {
  switch (status) {
    case "connected":
      return (
        <Badge variant="default" className="gap-1">
          <CheckCircle2 className="h-3 w-3" />
          Connected
        </Badge>
      );
    case "connecting":
      return (
        <Badge variant="outline" className="gap-1 border-amber-400 text-amber-600">
          <Loader2 className="h-3 w-3 animate-spin" />
          Connecting
        </Badge>
      );
    case "error":
      return (
        <Badge variant="destructive" className="gap-1">
          <AlertCircle className="h-3 w-3" />
          Error
        </Badge>
      );
    case "setup_required":
      return (
        <Badge variant="outline" className="border-amber-400 text-amber-600">
          Setup Required
        </Badge>
      );
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString();
}

function EmailSettingsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [integrations, setIntegrations] = useState<EmailIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<EmailIntegration | null>(null);

  const load = useCallback(async () => {
    try {
      const intData = await api.get<ListResponse>("/v1/email-integrations");
      setIntegrations(intData.integrations || []);
    } catch (e) {
      toast.error("Failed to load email integrations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Handle ?gmail=connected / ?gmail=error from OAuth callback redirect
  useEffect(() => {
    const gmail = searchParams.get("gmail");
    if (!gmail) return;
    if (gmail === "connected") {
      const account = searchParams.get("account");
      toast.success(account ? `Gmail connected: ${account}` : "Gmail connected");
    } else if (gmail === "error") {
      const reason = searchParams.get("reason") || "unknown";
      toast.error(`Gmail connection failed: ${reason}`);
    }
    // Clean the query string so the toast doesn't fire again on re-renders
    router.replace("/settings/email");
  }, [searchParams, router]);

  const handleConnectGmail = async (reauthIntegrationId?: string) => {
    setConnecting(true);
    try {
      const resp = await api.post<{ authorize_url: string; integration_id: string }>(
        "/v1/email-integrations/gmail/authorize",
        reauthIntegrationId ? { integration_id: reauthIntegrationId } : {}
      );
      window.location.href = resp.authorize_url;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to start Gmail OAuth";
      toast.error(msg);
      setConnecting(false);
    }
  };

  const handleSync = async (integration: EmailIntegration, incremental: boolean) => {
    setSyncingId(integration.id);
    try {
      const params = new URLSearchParams();
      if (incremental) params.set("incremental", "true");
      else params.set("days", "30");
      const result = await api.post<{ stats: Record<string, number> }>(
        `/v1/email-integrations/${integration.id}/sync?${params.toString()}`,
        {}
      );
      const s = result.stats;
      toast.success(
        `Sync complete — fetched ${s.fetched}, ingested ${s.ingested}, skipped ${s.skipped}, errors ${s.errors}`
      );
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Sync failed";
      toast.error(msg);
    } finally {
      setSyncingId(null);
    }
  };

  const handleDisconnect = async () => {
    if (!confirmDelete) return;
    try {
      await api.delete<{ ok: boolean }>(`/v1/email-integrations/${confirmDelete.id}`);
      toast.success("Integration disconnected");
      setConfirmDelete(null);
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to disconnect";
      toast.error(msg);
    }
  };

  const hasGmailConnected = integrations.some(
    (i) => i.type === "gmail_api" && i.status === "connected"
  );

  return (
    <PageLayout title="Email Integrations" subtitle="Connect your inbox so QP can send and receive customer email on your behalf.">
      <div className="space-y-4">
        {/* Connect new integration */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Plug className="h-4 w-4 text-primary" />
              Connect a new mailbox
            </CardTitle>
            <CardDescription>
              Choose how QuantumPools should handle your customer email. Most teams use Gmail.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => handleConnectGmail()}
                disabled={connecting}
                variant={hasGmailConnected ? "outline" : "default"}
              >
                {connecting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Mail className="h-4 w-4" />
                )}
                {hasGmailConnected ? "Connect another Gmail" : "Connect Gmail"}
              </Button>
              <Button variant="outline" disabled title="Coming soon">
                Connect Microsoft 365
              </Button>
              <Button variant="outline" disabled title="Coming soon">
                Use Email Forwarding
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              Gmail uses Google&apos;s OAuth — you&apos;ll be redirected to Google to grant access. We never see your password,
              and you can disconnect at any time.
            </p>
          </CardContent>
        </Card>

        {/* Existing integrations */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Connected Mailboxes</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : integrations.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No mailboxes connected yet. Connect Gmail above to get started.
              </p>
            ) : (
              <div className="space-y-3">
                {integrations.map((ei) => (
                  <div
                    key={ei.id}
                    className="rounded-lg border bg-muted/50 p-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium truncate">
                          {ei.account_email || ei.inbound_sender_address || "(no address)"}
                        </span>
                        {statusBadge(ei.status)}
                        {ei.is_primary && (
                          <Badge variant="outline" className="border-blue-400 text-blue-600">
                            Primary
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {TYPE_LABELS[ei.type]}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Last sync: {formatRelative(ei.last_sync_at)}
                      </div>
                      {ei.last_error && (
                        <div className="text-xs text-destructive mt-2 flex items-start gap-1">
                          <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                          <span className="break-words">{ei.last_error}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {ei.type === "gmail_api" && (ei.status === "error" || ei.status === "disconnected") && (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => handleConnectGmail(ei.id)}
                          disabled={connecting}
                          title="Re-authenticate this Gmail account (preserves sync history)"
                        >
                          {connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                          Reconnect
                        </Button>
                      )}
                      {ei.type === "gmail_api" && ei.status === "connected" && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleSync(ei, true)}
                            disabled={syncingId === ei.id}
                            title="Incremental sync (changes since last run)"
                          >
                            {syncingId === ei.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <RefreshCw className="h-4 w-4" />
                            )}
                            Sync
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleSync(ei, false)}
                            disabled={syncingId === ei.id}
                            title="Pull last 30 days"
                          >
                            Backfill 30d
                          </Button>
                        </>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => setConfirmDelete(ei)}
                        title="Disconnect"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

      </div>

      <AlertDialog open={!!confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect this mailbox?</AlertDialogTitle>
            <AlertDialogDescription>
              QuantumPools will stop sending and receiving email through{" "}
              <strong>{confirmDelete?.account_email}</strong>. Stored OAuth tokens will be destroyed.
              Past synced messages stay in your inbox. You can reconnect later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDisconnect}>Disconnect</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}

export default function EmailSettingsPage() {
  return (
    <Suspense fallback={
      <PageLayout title="Email Integrations">
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </PageLayout>
    }>
      <EmailSettingsContent />
    </Suspense>
  );
}
