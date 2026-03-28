"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, DollarSign, ShieldAlert, Briefcase, MessageSquare } from "lucide-react";
import { api } from "@/lib/api";
import Link from "next/link";

interface DrainCoverAlert {
  wf_name: string;
  expires: string | null;
}

interface CustomerAlerts {
  overdue_balance: number;
  overdue_invoices: number;
  expiring_drain_covers: DrainCoverAlert[];
  pending_jobs: number;
  stale_threads: number;
}

interface AlertsSectionProps {
  customerId: string;
}

export function AlertsSection({ customerId }: AlertsSectionProps) {
  const [alerts, setAlerts] = useState<CustomerAlerts | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.get<CustomerAlerts>(`/v1/customers/${customerId}/alerts`).then((data) => {
      if (!cancelled) setAlerts(data);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [customerId]);

  if (!alerts) return null;

  const hasAlerts =
    alerts.overdue_invoices > 0 ||
    alerts.expiring_drain_covers.length > 0 ||
    alerts.pending_jobs > 0 ||
    alerts.stale_threads > 0;

  if (!hasAlerts) return null;

  return (
    <div id="alerts" className="space-y-2">
      {alerts.overdue_invoices > 0 && (
        <Link
          href={`/invoices?customer_id=${customerId}&status=overdue`}
          className="flex items-center gap-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 px-4 py-3 transition-colors hover:bg-red-100 dark:hover:bg-red-950/60"
        >
          <div className="flex items-center justify-center h-8 w-8 rounded-full bg-red-100 dark:bg-red-900/60">
            <DollarSign className="h-4 w-4 text-red-600 dark:text-red-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              ${alerts.overdue_balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} overdue
            </p>
            <p className="text-xs text-red-600 dark:text-red-400">
              {alerts.overdue_invoices} overdue invoice{alerts.overdue_invoices !== 1 ? "s" : ""}
            </p>
          </div>
          <span className="text-xs text-red-500 dark:text-red-400 font-medium">View Invoices</span>
        </Link>
      )}

      {alerts.expiring_drain_covers.map((dc, i) => {
        const expiryDate = dc.expires ? new Date(dc.expires) : null;
        const isExpired = expiryDate ? expiryDate < new Date() : false;
        return (
          <div
            key={`drain-${i}`}
            className="flex items-center gap-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 px-4 py-3"
          >
            <div className="flex items-center justify-center h-8 w-8 rounded-full bg-amber-100 dark:bg-amber-900/60">
              <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                {dc.wf_name} — drain cover {isExpired ? "expired" : "expiring"}
              </p>
              {expiryDate && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {isExpired ? "Expired" : "Expires"}{" "}
                  {expiryDate.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                </p>
              )}
            </div>
          </div>
        );
      })}

      {alerts.pending_jobs > 0 && (
        <Link
          href={`/jobs?customer_id=${customerId}&status=open`}
          className="flex items-center gap-3 rounded-lg bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900 px-4 py-3 transition-colors hover:bg-blue-100 dark:hover:bg-blue-950/60"
        >
          <div className="flex items-center justify-center h-8 w-8 rounded-full bg-blue-100 dark:bg-blue-900/60">
            <Briefcase className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-blue-800 dark:text-blue-300">
              {alerts.pending_jobs} pending job{alerts.pending_jobs !== 1 ? "s" : ""}
            </p>
          </div>
          <span className="text-xs text-blue-500 dark:text-blue-400 font-medium">View Jobs</span>
        </Link>
      )}

      {alerts.stale_threads > 0 && (
        <Link
          href={`/inbox?customer_id=${customerId}`}
          className="flex items-center gap-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 px-4 py-3 transition-colors hover:bg-amber-100 dark:hover:bg-amber-950/60"
        >
          <div className="flex items-center justify-center h-8 w-8 rounded-full bg-amber-100 dark:bg-amber-900/60">
            <MessageSquare className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
              {alerts.stale_threads} stale thread{alerts.stale_threads !== 1 ? "s" : ""}
            </p>
            <p className="text-xs text-amber-600 dark:text-amber-400">
              Awaiting response for 24+ hours
            </p>
          </div>
          <span className="text-xs text-amber-500 dark:text-amber-400 font-medium">View Inbox</span>
        </Link>
      )}
    </div>
  );
}
