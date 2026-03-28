"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText } from "lucide-react";

interface InvoiceRow {
  id: string;
  invoice_number: string;
  subject: string | null;
  status: string;
  total: number;
  issue_date: string;
}

const STATUS_COLOR: Record<string, string> = {
  draft: "text-muted-foreground",
  sent: "text-blue-600",
  paid: "text-green-600",
  overdue: "text-red-600",
  void: "text-muted-foreground line-through",
};

interface InvoicesTileProps {
  customerId: string;
}

export function InvoicesTile({ customerId }: InvoicesTileProps) {
  const router = useRouter();
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get<{ items: InvoiceRow[] }>(`/v1/invoices?customer_id=${customerId}&limit=5`)
      .then((d) => { if (!cancelled) setInvoices(d.items || []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [customerId]);

  if (!loaded || invoices.length === 0) return null;

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <span className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            Invoices
          </span>
          <Link href={`/invoices?customer_id=${customerId}`} className="text-xs text-muted-foreground hover:text-primary font-normal">
            View all →
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {invoices.map((inv) => (
            <div
              key={inv.id}
              className="flex items-center justify-between py-2 text-sm cursor-pointer hover:bg-muted/50 -mx-2 px-2 rounded transition-colors"
              onClick={() => router.push(`/invoices/${inv.id}`)}
            >
              <div className="min-w-0">
                <span className="font-mono text-xs text-muted-foreground">{inv.invoice_number}</span>
                {inv.subject && <span className="ml-2 text-xs truncate">{inv.subject}</span>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className={`text-xs font-medium capitalize ${STATUS_COLOR[inv.status] || ""}`}>{inv.status}</span>
                <span className="text-sm font-medium">${inv.total.toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
