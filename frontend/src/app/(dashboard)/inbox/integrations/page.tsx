"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
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
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Save } from "lucide-react";
import {
  Loader2,
  Mail,
  Plug,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Clock,
  PenLine,
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
    router.replace("/inbox/integrations");
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

        <SignatureSection />

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


interface SignaturePreviewResult {
  plain: string;
  html: string;
  logo_url: string | null;
  website_url: string | null;
  org_name: string | null;
  sender_first_name: string | null;
}

interface UserSigData {
  email_signature: string | null;
  email_signoff: string | null;
  org_auto_signature_prefix: boolean;
  org_include_logo_in_signature: boolean;
  org_allow_per_user_signature: boolean;
  org_signature_fallback: string | null;
  org_name: string | null;
  org_logo_url: string | null;
}

interface OrgSigData {
  email_signature: string | null;
  auto_signature_prefix: boolean;
  include_logo_in_signature: boolean;
  allow_per_user_signature: boolean;
  logo_url?: string | null;
  website_url?: string | null;
}

/**
 * SignatureSection — single surface for both admin and per-user signature
 * config. Lives at /inbox/integrations and holds BOTH form states so the
 * live preview reflects every in-flight edit across both cards. The old
 * split previews diverged because each card had its own form + preview;
 * this unified section fixes that.
 *
 * Layout:
 *   ┌─ Preview (one, shared) ─────────┐
 *   └─────────────────────────────────┘
 *   ┌─ Your email signature ──────────┐
 *   │  Sign-off, personal info        │  (per-user, everyone sees)
 *   └─────────────────────────────────┘
 *   ┌─ Email Signature (admin only) ──┐
 *   │  Toggles + shared org footer    │  (hidden if non-admin)
 *   └─────────────────────────────────┘
 */
function SignatureSection() {
  const perms = usePermissions();
  const isAdmin = perms.role === "owner" || perms.role === "admin";

  const [userLoaded, setUserLoaded] = useState<UserSigData | null>(null);
  const [userSig, setUserSig] = useState("");
  const [userSignoff, setUserSignoff] = useState("");
  const [userSaving, setUserSaving] = useState(false);

  const [orgLoaded, setOrgLoaded] = useState<OrgSigData | null>(null);
  const [orgForm, setOrgForm] = useState<OrgSigData>({
    email_signature: "",
    auto_signature_prefix: true,
    include_logo_in_signature: false,
    allow_per_user_signature: true,
    logo_url: null,
    website_url: null,
  });
  const [orgSaving, setOrgSaving] = useState(false);

  const [preview, setPreview] = useState<SignaturePreviewResult | null>(null);

  const loadUser = useCallback(async () => {
    try {
      const data = await api.get<UserSigData>("/v1/auth/me/email-signature");
      setUserLoaded(data);
      setUserSig(data?.email_signature ?? "");
      setUserSignoff(data?.email_signoff ?? "");
    } catch { /* ignore */ }
  }, []);

  const loadOrg = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const data = await api.get<OrgSigData>("/v1/branding");
      setOrgLoaded(data);
      setOrgForm({
        email_signature: data.email_signature ?? "",
        auto_signature_prefix: data.auto_signature_prefix,
        include_logo_in_signature: data.include_logo_in_signature,
        allow_per_user_signature: data.allow_per_user_signature,
        logo_url: data.logo_url ?? null,
        website_url: data.website_url ?? null,
      });
    } catch { /* ignore */ }
  }, [isAdmin]);

  useEffect(() => { loadUser(); loadOrg(); }, [loadUser, loadOrg]);

  // Live preview combines both forms' unsaved state.
  // Admin form takes precedence for org-level fields when available;
  // non-admins pass only user fields and inherit current org state from
  // userLoaded snapshot.
  useEffect(() => {
    if (!userLoaded) return;
    const t = setTimeout(async () => {
      try {
        const p = await api.post<SignaturePreviewResult>("/v1/auth/me/email-signature/preview", {
          user_signature: userSig,
          user_signoff: userSignoff,
          auto_signature_prefix: isAdmin ? orgForm.auto_signature_prefix : undefined,
          include_logo_in_signature: isAdmin ? orgForm.include_logo_in_signature : undefined,
          allow_per_user_signature: isAdmin ? orgForm.allow_per_user_signature : undefined,
          website_url: isAdmin ? orgForm.website_url : undefined,
          org_signature: isAdmin ? orgForm.email_signature : undefined,
          use_current_user: true,
        });
        setPreview(p);
      } catch { /* ignore */ }
    }, 250);
    return () => clearTimeout(t);
  }, [userSig, userSignoff, orgForm, userLoaded, isAdmin]);

  const userDirty = !!userLoaded && (
    userSig !== (userLoaded.email_signature ?? "") ||
    userSignoff !== (userLoaded.email_signoff ?? "")
  );

  const orgDirty = !!orgLoaded && (
    (orgForm.email_signature ?? "") !== (orgLoaded.email_signature ?? "") ||
    orgForm.auto_signature_prefix !== orgLoaded.auto_signature_prefix ||
    orgForm.include_logo_in_signature !== orgLoaded.include_logo_in_signature ||
    orgForm.allow_per_user_signature !== orgLoaded.allow_per_user_signature ||
    (orgForm.website_url ?? "") !== (orgLoaded.website_url ?? "")
  );

  const saveUser = async () => {
    setUserSaving(true);
    try {
      await api.put("/v1/auth/me/email-signature", {
        email_signature: userSig || null,
        email_signoff: userSignoff || null,
      });
      toast.success("Your signature saved");
      await loadUser();
    } catch {
      toast.error("Failed to save");
    } finally {
      setUserSaving(false);
    }
  };

  const saveOrg = async () => {
    setOrgSaving(true);
    try {
      await api.put("/v1/branding", {
        email_signature: orgForm.email_signature || null,
        auto_signature_prefix: orgForm.auto_signature_prefix,
        include_logo_in_signature: orgForm.include_logo_in_signature,
        allow_per_user_signature: orgForm.allow_per_user_signature,
        website_url: orgForm.website_url || null,
      });
      toast.success("Organization signature settings saved");
      await loadOrg();
      // User preview inherits org state from userLoaded; reload so it's
      // in sync with the saved values.
      await loadUser();
    } catch {
      toast.error("Failed to save");
    } finally {
      setOrgSaving(false);
    }
  };

  if (!userLoaded) return null;

  // Which admin toggles to reflect in the preview. If admin is editing,
  // use their form state; otherwise use what userLoaded reports.
  const effectiveIncludeLogo = isAdmin && orgLoaded
    ? orgForm.include_logo_in_signature
    : userLoaded.org_include_logo_in_signature;
  const effectiveLogoUrl = isAdmin && orgLoaded ? orgForm.logo_url : userLoaded.org_logo_url;
  const showLogoUrl = effectiveIncludeLogo ? effectiveLogoUrl ?? null : null;
  const logoAvailable = !!effectiveLogoUrl;
  const effectiveWebsiteUrl = isAdmin && orgLoaded
    ? orgForm.website_url ?? null
    : preview?.website_url ?? null;

  // When admin has disabled per-user customization, the personal section
  // still renders but its inputs are disabled with an explanation. That
  // way users see their current (saved) values and the reason they can't
  // edit. If nothing's saved + it's disabled, we show a status message.
  const perUserAllowed = isAdmin && orgLoaded
    ? orgForm.allow_per_user_signature
    : userLoaded.org_allow_per_user_signature;

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <PenLine className="h-4 w-4 text-primary" />
          Email Signature
        </CardTitle>
        <CardDescription>
          Signature applied to outbound customer emails. Admin-controlled format and footer;
          each user adds their own personal info above the shared footer.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Preview — always on top, always reflects live form state */}
        <section className="space-y-1.5">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-medium">Preview</div>
          <p className="text-[11px] text-muted-foreground -mt-0.5">
            Live — reflects unsaved edits anywhere on this page. This is literally what recipients see.
          </p>
          <SignaturePreview preview={preview} showLogoUrl={showLogoUrl} websiteUrl={effectiveWebsiteUrl} />
        </section>

        {/* Per-user section */}
        <section className="space-y-3 border-t pt-5 max-w-2xl">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-medium">Your personal info</div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {perUserAllowed
                ? userLoaded.org_auto_signature_prefix
                  ? "Your first name and organization name are auto-added above this. Type just your personal contact details (phone, title, pronouns)."
                  : "The organization's shared footer is appended below this. Type your personal contact details (phone, title, pronouns)."
                : "The organization admin has disabled per-user signature customization — every outbound uses the organization defaults below."}
            </p>
          </div>

          <div className="space-y-1">
            <Label className="text-sm font-medium">Sign-off (optional)</Label>
            <Input
              type="text"
              value={userSignoff}
              onChange={(e) => setUserSignoff(e.target.value)}
              placeholder="e.g. Best, — leave blank to skip"
              maxLength={50}
              disabled={!perUserAllowed}
              className="text-sm max-w-xs"
            />
            <p className="text-[10px] text-muted-foreground">
              Rendered on its own line above your name. Common choices: &quot;Best,&quot; &quot;Regards,&quot; &quot;v/r,&quot; &quot;Cheers,&quot;.
            </p>
          </div>
          <div className="space-y-1">
            <Label className="text-sm font-medium">Signature text</Label>
            <Textarea
              value={userSig}
              onChange={(e) => setUserSig(e.target.value)}
              rows={4}
              placeholder={"e.g.\n(555) 555-1234\nyour-title@example.com"}
              disabled={!perUserAllowed}
              className="text-sm font-mono"
            />
          </div>
          {perUserAllowed && (
            <Button
              onClick={saveUser}
              disabled={userSaving || !userDirty}
              size="sm"
            >
              {userSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
              Save
            </Button>
          )}
        </section>

        {/* Admin section */}
        {isAdmin && orgLoaded && (
          <section className="space-y-3 border-t pt-5 max-w-2xl">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-medium">Organization settings (admin only)</div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Format and shared footer applied to every outbound email regardless of who sent it.
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <label className="flex items-start gap-2 cursor-pointer text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={orgForm.allow_per_user_signature}
                  onChange={(e) =>
                    setOrgForm((f) => ({ ...f, allow_per_user_signature: e.target.checked }))
                  }
                />
                <div>
                  <div className="font-medium">Let users customize their signature</div>
                  <div className="text-[11px] text-muted-foreground">
                    When off, every outbound uses only the org footer below — users can&apos;t add a personal sign-off or personal info. Use for absolute brand consistency.
                  </div>
                </div>
              </label>
              <label className="flex items-start gap-2 cursor-pointer text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={orgForm.auto_signature_prefix}
                  onChange={(e) =>
                    setOrgForm((f) => ({ ...f, auto_signature_prefix: e.target.checked }))
                  }
                />
                <div>
                  <div className="font-medium">Auto-add sender name and organization name</div>
                  <div className="text-[11px] text-muted-foreground">
                    Prepends each sender&apos;s first name and the organization name above their signature text. Keeps outbound branding consistent across every sender.
                  </div>
                </div>
              </label>
              <label className={cn("flex items-start gap-2 text-sm", logoAvailable ? "cursor-pointer" : "cursor-not-allowed opacity-60")}>
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={orgForm.include_logo_in_signature}
                  disabled={!logoAvailable}
                  onChange={(e) =>
                    setOrgForm((f) => ({ ...f, include_logo_in_signature: e.target.checked }))
                  }
                />
                <div>
                  <div className="font-medium">Include logo in signature</div>
                  <div className="text-[11px] text-muted-foreground">
                    {logoAvailable
                      ? "Adds your uploaded logo at the bottom of the signature as an inline image. Renders in Gmail, Apple Mail, Outlook."
                      : "Upload a logo under Branding (Settings) first to enable this."}
                  </div>
                </div>
              </label>
            </div>

            <div className="space-y-1">
              <Label className="text-sm font-medium">Website URL</Label>
              <p className="text-[11px] text-muted-foreground">
                When the logo is enabled, clicking it in a recipient&apos;s inbox opens this URL. Leave blank for a static (non-clickable) logo.
              </p>
              <Input
                type="url"
                value={orgForm.website_url ?? ""}
                onChange={(e) =>
                  setOrgForm((f) => ({ ...f, website_url: e.target.value }))
                }
                placeholder="e.g. https://your-company.com"
                className="text-sm max-w-sm"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-sm font-medium">Organization footer (shared by all users)</Label>
              <p className="text-[11px] text-muted-foreground">
                Appended to every outbound email from every sender — this is your standardized tail.
              </p>
              <Textarea
                value={orgForm.email_signature ?? ""}
                onChange={(e) =>
                  setOrgForm((f) => ({ ...f, email_signature: e.target.value }))
                }
                rows={4}
                placeholder={"e.g.\ncontact@your-company.com\nyour-company.com"}
                className="text-sm font-mono"
              />
            </div>

            <Button
              onClick={saveOrg}
              disabled={orgSaving || !orgDirty}
              size="sm"
            >
              {orgSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
              Save
            </Button>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function SignaturePreview({
  preview,
  showLogoUrl,
  websiteUrl,
}: {
  preview: SignaturePreviewResult | null;
  showLogoUrl: string | null;
  websiteUrl: string | null;
}) {
  // Preview matches send behavior: when both a logo and a website URL are
  // set, the logo is clickable. We normalize bare domains like
  // "sapphire-pools.com" to https for the preview href — matches server
  // composition in email_signature._normalize_website.
  const normalizedSite = websiteUrl?.trim()
    ? /^https?:\/\//i.test(websiteUrl.trim())
      ? websiteUrl.trim()
      : `https://${websiteUrl.trim()}`
    : null;
  const logoImg = showLogoUrl ? (
    <img
      src={showLogoUrl}
      alt="logo"
      style={{ maxWidth: 180, maxHeight: 60, height: "auto", display: "inline-block", border: 0 }}
    />
  ) : null;
  return (
    <div className="rounded-md border bg-background p-4 text-sm">
      {preview && preview.html ? (
        <>
          <div className="text-muted-foreground italic">Hi Jane,</div>
          <div className="text-muted-foreground italic">Thanks for reaching out. [the body of your email goes here.]</div>
          <div dangerouslySetInnerHTML={{ __html: preview.html }} />
          {logoImg && (
            <div className="mt-2">
              {normalizedSite ? (
                <a href={normalizedSite} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none" }}>
                  {logoImg}
                </a>
              ) : logoImg}
            </div>
          )}
        </>
      ) : (
        <div className="text-muted-foreground italic">No signature configured yet.</div>
      )}
    </div>
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
