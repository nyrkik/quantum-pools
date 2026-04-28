"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { LogOut, Loader2, ArrowRight, CheckCircle2, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

interface PortalMe {
  contact: {
    id: string | null;
    first_name: string | null;
    last_name: string | null;
    email: string | null;
  };
  customer: {
    id: string;
    display_name: string;
    company_name: string | null;
  };
  org: {
    id: string | null;
    name: string;
    branding_color: string | null;
    logo_url: string | null;
  };
  open_invoice_count: number;
  open_balance: number;
  has_card_on_file: boolean;
  card_last4: string | null;
  card_brand: string | null;
  autopay_enabled: boolean;
}

interface PortalInvoice {
  id: string;
  invoice_number: string | null;
  subject: string | null;
  status: string;
  issue_date: string | null;
  due_date: string | null;
  paid_date: string | null;
  total: number;
  amount_paid: number;
  balance: number;
  po_number: string | null;
  payment_token: string | null;
}

interface PortalPayment {
  id: string;
  amount: number;
  payment_method: string;
  payment_date: string | null;
  reference_number: string | null;
  is_autopay: boolean;
  invoice_id: string | null;
}

type TabKey = "billing" | "methods" | "history";

function fmt(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function PortalLandingPage() {
  const router = useRouter();
  const [me, setMe] = useState<PortalMe | null>(null);
  const [openInvoices, setOpenInvoices] = useState<PortalInvoice[] | null>(null);
  const [historyInvoices, setHistoryInvoices] = useState<PortalInvoice[] | null>(null);
  const [payments, setPayments] = useState<PortalPayment[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [signingOut, setSigningOut] = useState(false);
  const [tab, setTab] = useState<TabKey>("billing");
  const [autopayBusy, setAutopayBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/v1/portal/me", { credentials: "include" });
        if (cancelled) return;
        if (r.status === 401) {
          router.replace("/portal/login");
          return;
        }
        if (!r.ok) throw new Error();
        const meData: PortalMe = await r.json();
        setMe(meData);

        // Fan out the rest in parallel
        const [openR, paidR, payR] = await Promise.all([
          fetch("/api/v1/portal/invoices?status_filter=open", { credentials: "include" }),
          fetch("/api/v1/portal/invoices?status_filter=paid", { credentials: "include" }),
          fetch("/api/v1/portal/payments", { credentials: "include" }),
        ]);
        if (cancelled) return;
        if (openR.ok) setOpenInvoices((await openR.json()).items);
        if (paidR.ok) setHistoryInvoices((await paidR.json()).items);
        if (payR.ok) setPayments((await payR.json()).items);
      } catch {
        if (!cancelled) router.replace("/portal/login");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function logout() {
    setSigningOut(true);
    try {
      await fetch("/api/v1/portal/logout", { method: "POST", credentials: "include" });
    } catch {
      // Even on error, route to login (cookie may already be cleared server-side).
    } finally {
      router.replace("/portal/login");
    }
  }

  async function toggleAutopay(next: boolean) {
    if (!me || autopayBusy) return;
    setAutopayBusy(true);
    try {
      const r = await fetch("/api/v1/portal/autopay", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(payload?.detail || "Failed to update autopay");
      }
      const out = await r.json();
      setMe({ ...me, autopay_enabled: out.autopay_enabled });
      toast.success(out.autopay_enabled ? "Autopay enabled" : "Autopay disabled");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setAutopayBusy(false);
    }
  }

  if (loading || !me) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
      </div>
    );
  }

  const greeting =
    me.contact.first_name?.trim() ||
    me.contact.email?.split("@")[0] ||
    "there";

  const TABS: { key: TabKey; label: string; badge?: number }[] = [
    {
      key: "billing",
      label: "Billing",
      badge: openInvoices?.length || undefined,
    },
    { key: "methods", label: "Payment methods" },
    { key: "history", label: "History" },
  ];

  return (
    <div className="min-h-screen">
      <header className="bg-background border-b">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {me.org.logo_url ? (
              <Image
                src={me.org.logo_url}
                alt={me.org.name}
                width={36}
                height={36}
                className="rounded object-contain"
              />
            ) : null}
            <div className="min-w-0">
              <div className="font-semibold truncate">{me.org.name}</div>
              <div className="text-xs text-muted-foreground truncate">
                Customer portal
              </div>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={logout} disabled={signingOut}>
            <LogOut className="h-4 w-4 mr-1.5" />
            Sign out
          </Button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Hi {greeting},</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Signed in as {me.contact.email} for {me.customer.display_name}.
          </p>
        </div>

        {/* Top-line balance. Stays visible across all tabs because it's
            the single most important number on this page. */}
        <Card className="shadow-sm">
          <CardContent className="p-5 sm:p-6 flex items-center justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Open balance
              </div>
              <div className="text-3xl font-semibold mt-1 tabular-nums">
                {fmt(me.open_balance)}
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {me.open_invoice_count === 0
                  ? "Nothing outstanding."
                  : me.open_invoice_count === 1
                  ? "1 invoice outstanding"
                  : `${me.open_invoice_count} invoices outstanding`}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tab bar */}
        <div className="border-b flex gap-4 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={
                "py-2 text-sm whitespace-nowrap border-b-2 -mb-px " +
                (tab === t.key
                  ? "border-primary text-foreground font-medium"
                  : "border-transparent text-muted-foreground hover:text-foreground")
              }
            >
              {t.label}
              {t.badge ? (
                <span className="ml-1.5 text-xs text-muted-foreground">
                  {t.badge}
                </span>
              ) : null}
            </button>
          ))}
        </div>

        {tab === "billing" && (
          <BillingTab invoices={openInvoices} />
        )}
        {tab === "methods" && (
          <MethodsTab
            me={me}
            onToggleAutopay={toggleAutopay}
            autopayBusy={autopayBusy}
          />
        )}
        {tab === "history" && (
          <HistoryTab invoices={historyInvoices} payments={payments} />
        )}
      </main>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tabs
// ─────────────────────────────────────────────────────────────────────────────

function BillingTab({ invoices }: { invoices: PortalInvoice[] | null }) {
  if (invoices === null) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading invoices…
      </div>
    );
  }
  if (invoices.length === 0) {
    return (
      <Card className="shadow-sm">
        <CardContent className="py-8 text-center text-muted-foreground text-sm">
          No outstanding invoices.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="space-y-2">
      {invoices.map((inv) => (
        <Card key={inv.id} className="shadow-sm">
          <CardContent className="p-4 flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">
                  {inv.invoice_number ? `#${inv.invoice_number}` : "Invoice"}
                </span>
                {inv.subject && (
                  <span className="text-sm text-muted-foreground truncate">
                    — {inv.subject}
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                Issued {fmtDate(inv.issue_date)}
                {inv.due_date && ` · Due ${fmtDate(inv.due_date)}`}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-semibold tabular-nums">
                {fmt(inv.balance)}
              </div>
              {inv.payment_token ? (
                <Link href={`/pay/${inv.payment_token}`}>
                  <Button size="sm" className="mt-1">
                    Pay
                    <ArrowRight className="h-3.5 w-3.5 ml-1" />
                  </Button>
                </Link>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function MethodsTab({
  me,
  onToggleAutopay,
  autopayBusy,
}: {
  me: PortalMe;
  onToggleAutopay: (next: boolean) => Promise<void>;
  autopayBusy: boolean;
}) {
  return (
    <div className="space-y-3">
      <Card className="shadow-sm">
        <CardContent className="p-5">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Card on file
          </div>
          <div className="mt-2">
            {me.has_card_on_file ? (
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <span className="font-medium capitalize">
                  {me.card_brand ?? "Card"} ending {me.card_last4}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-muted-foreground">
                <AlertCircle className="h-4 w-4" />
                <span className="text-sm">No payment method on file.</span>
              </div>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            Add or update your payment method by contacting {me.org.name} —
            self-serve card management is coming soon to this portal.
          </p>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardContent className="p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="font-medium">Autopay</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {me.has_card_on_file
                  ? "Charge your card automatically when invoices are due."
                  : "Add a payment method first to enable autopay."}
              </div>
            </div>
            <Switch
              checked={me.autopay_enabled}
              disabled={autopayBusy || !me.has_card_on_file}
              onCheckedChange={onToggleAutopay}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function HistoryTab({
  invoices,
  payments,
}: {
  invoices: PortalInvoice[] | null;
  payments: PortalPayment[] | null;
}) {
  if (invoices === null || payments === null) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading history…
      </div>
    );
  }
  if (invoices.length === 0 && payments.length === 0) {
    return (
      <Card className="shadow-sm">
        <CardContent className="py-8 text-center text-muted-foreground text-sm">
          No payment or invoice history yet.
        </CardContent>
      </Card>
    );
  }

  // Merge into one timeline sorted by date desc. Invoices go in by paid_date
  // (or issue_date as fallback so unpaid-but-historical entries still sort).
  type Row =
    | { kind: "invoice"; date: string; data: PortalInvoice }
    | { kind: "payment"; date: string; data: PortalPayment };
  const rows: Row[] = [
    ...invoices.map((i) => ({
      kind: "invoice" as const,
      date: i.paid_date || i.issue_date || "",
      data: i,
    })),
    ...payments.map((p) => ({
      kind: "payment" as const,
      date: p.payment_date || "",
      data: p,
    })),
  ].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));

  return (
    <div className="space-y-2">
      {rows.map((row, idx) =>
        row.kind === "invoice" ? (
          <Card key={`inv-${row.data.id}-${idx}`} className="shadow-sm">
            <CardContent className="p-4 flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">
                    Invoice {row.data.invoice_number ? `#${row.data.invoice_number}` : ""}
                  </span>
                  <span className="text-xs text-muted-foreground capitalize">
                    {row.data.status}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Paid {fmtDate(row.data.paid_date)}
                </div>
              </div>
              <div className="font-semibold tabular-nums shrink-0">
                {fmt(row.data.total)}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card key={`pay-${row.data.id}-${idx}`} className="shadow-sm">
            <CardContent className="p-4 flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">Payment received</span>
                  <span className="text-xs text-muted-foreground capitalize">
                    {row.data.payment_method}
                    {row.data.is_autopay && " · autopay"}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {fmtDate(row.data.payment_date)}
                  {row.data.reference_number && ` · #${row.data.reference_number}`}
                </div>
              </div>
              <div className="font-semibold tabular-nums shrink-0 text-green-700 dark:text-green-500">
                +{fmt(row.data.amount)}
              </div>
            </CardContent>
          </Card>
        )
      )}
    </div>
  );
}
