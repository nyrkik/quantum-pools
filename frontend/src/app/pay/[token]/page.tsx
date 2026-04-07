"use client";

import { useState, useEffect, use } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle2, FileText, CreditCard, AlertCircle } from "lucide-react";

interface InvoiceData {
  invoice_number: string;
  document_type: string;
  subject: string | null;
  customer_name: string | null;
  org_name: string | null;
  org_color: string | null;
  status: string;
  issue_date: string | null;
  due_date: string | null;
  line_items: { description: string; quantity: number; unit_price: number; total: number }[];
  subtotal: number;
  tax_amount: number;
  discount: number;
  total: number;
  amount_paid: number;
  balance: number;
  paid_date: string | null;
  notes: string | null;
}

export default function PayInvoicePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const paymentStatus = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("status") : null;
  const [data, setData] = useState<InvoiceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payLoading, setPayLoading] = useState(false);
  const [payError, setPayError] = useState("");

  const [verified, setVerified] = useState(false);
  const isPaid = data?.status === "paid" || verified;
  const isOverdue = data?.status === "overdue";

  useEffect(() => {
    fetch(`/api/v1/public/invoice/${token}`)
      .then(async (res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((d) => {
        setData(d);
        // If returning from Stripe checkout, verify and record the payment
        if (paymentStatus === "success" && d.status !== "paid") {
          fetch(`/api/v1/public/invoice/${token}/verify-payment`, { method: "POST" })
            .then(r => r.json())
            .then(r => { if (r.status === "paid" || r.status === "already_paid") setVerified(true); })
            .catch(() => {});
        } else if (d.status === "paid") {
          setVerified(true);
        }
      })
      .catch(() => setError("This invoice is no longer available."))
      .finally(() => setLoading(false));
  }, [token, paymentStatus]);

  const [redirecting, setRedirecting] = useState(false);

  const handlePay = async () => {
    setPayLoading(true);
    setPayError("");
    try {
      const res = await fetch(`/api/v1/public/invoice/${token}/checkout`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Payment setup failed");
      }
      const { checkout_url } = await res.json();
      setRedirecting(true);
      window.location.href = checkout_url;
    } catch (e: unknown) {
      setPayError(e instanceof Error ? e.message : "Payment failed");
      setPayLoading(false);
    }
  };

  if (loading || redirecting || (paymentStatus === "success" && !verified)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center space-y-3">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400 mx-auto" />
          {redirecting && <p className="text-sm text-slate-500">Redirecting to payment...</p>}
          {paymentStatus === "success" && !verified && <p className="text-sm text-slate-500">Confirming payment...</p>}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Card className="max-w-md w-full mx-4">
          <CardContent className="py-12 text-center">
            <FileText className="h-12 w-12 text-slate-300 mx-auto mb-4" />
            <p className="text-lg font-medium text-slate-700">Invoice Unavailable</p>
            <p className="text-sm text-slate-500 mt-2">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const brandColor = data.org_color || "#2563eb";
  const docLabel = data.document_type === "estimate" ? "Estimate" : "Invoice";

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="max-w-lg mx-auto space-y-4">
        {/* Header */}
        <div className="text-center space-y-2">
          {data.org_name && (
            <h1 className="text-lg font-semibold text-slate-800">{data.org_name}</h1>
          )}
          <p className="text-sm text-slate-500">{docLabel} {data.invoice_number}</p>
        </div>

        {/* Invoice card */}
        <Card className="shadow-md">
          <CardContent className="py-6 space-y-5">
            {/* Status banner */}
            {isPaid && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center space-y-2">
                <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto" />
                <p className="text-sm font-medium text-green-800">Payment Received</p>
                <p className="text-xs text-green-600">Thank you for your payment!</p>
                {data.paid_date && (
                  <p className="text-[11px] text-green-700">
                    Paid on {new Date(data.paid_date).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
                    {" "} — Confirmation #{data.invoice_number}
                  </p>
                )}
              </div>
            )}

            {isOverdue && !isPaid && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-amber-600 shrink-0" />
                <p className="text-sm text-amber-800">This invoice is past due. Please pay at your earliest convenience.</p>
              </div>
            )}

            {data.subject && (
              <h2 className="text-base font-semibold text-slate-800">{data.subject}</h2>
            )}

            {data.customer_name && (
              <p className="text-sm text-slate-500">Billed to {data.customer_name}</p>
            )}

            {/* Dates */}
            <div className="flex gap-6 text-xs text-slate-500">
              {data.issue_date && <span>Issued: {new Date(data.issue_date).toLocaleDateString()}</span>}
              {data.due_date && <span>Due: {new Date(data.due_date).toLocaleDateString()}</span>}
            </div>

            {/* Line items */}
            <div className="space-y-2">
              <div className="hidden sm:grid grid-cols-[1fr_60px_80px_80px] gap-2 text-xs text-slate-500 font-medium uppercase tracking-wide border-b pb-2">
                <span>Description</span>
                <span className="text-center">Qty</span>
                <span className="text-right">Price</span>
                <span className="text-right">Total</span>
              </div>
              {data.line_items.map((li, i) => (
                <div key={i}>
                  <div className="hidden sm:grid grid-cols-[1fr_60px_80px_80px] gap-2 text-sm py-1.5">
                    <span className="break-words">{li.description}</span>
                    <span className="text-center text-slate-500">{li.quantity}</span>
                    <span className="text-right text-slate-500">${li.unit_price.toFixed(2)}</span>
                    <span className="text-right font-medium">${li.total.toFixed(2)}</span>
                  </div>
                  <div className="sm:hidden border-b py-2 space-y-1">
                    <p className="text-sm font-medium break-words">{li.description}</p>
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Qty {li.quantity} x ${li.unit_price.toFixed(2)}</span>
                      <span className="font-medium text-sm text-slate-800">${li.total.toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Totals */}
              <div className="border-t pt-3 space-y-1">
                {data.discount > 0 && (
                  <div className="flex justify-between text-sm text-slate-500">
                    <span>Discount</span>
                    <span>-${data.discount.toFixed(2)}</span>
                  </div>
                )}
                {data.tax_amount > 0 && (
                  <div className="flex justify-between text-sm text-slate-500">
                    <span>Tax</span>
                    <span>${data.tax_amount.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span className="font-semibold">Total</span>
                  <span className="font-bold">${data.total.toFixed(2)}</span>
                </div>
                {data.amount_paid > 0 && !isPaid && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>Paid</span>
                    <span>-${data.amount_paid.toFixed(2)}</span>
                  </div>
                )}
                {data.balance > 0 && !isPaid && (
                  <div className="flex justify-between text-base pt-1">
                    <span className="font-semibold text-slate-800">Balance Due</span>
                    <span className="font-bold" style={{ color: brandColor }}>
                      ${data.balance.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {data.notes && (
              <div className="text-xs text-slate-500 bg-slate-50 rounded-md p-3 whitespace-pre-line">
                {data.notes}
              </div>
            )}

            {/* Pay button */}
            {!isPaid && data.balance > 0 && (
              <div className="pt-2 space-y-2">
                <Button
                  className="w-full gap-2 h-11 text-base"
                  style={{ backgroundColor: brandColor }}
                  onClick={handlePay}
                  disabled={payLoading}
                >
                  {payLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
                  Pay ${data.balance.toFixed(2)}
                </Button>
                {payError && <p className="text-xs text-red-500 text-center">{payError}</p>}
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-[10px] text-slate-400 text-center">
          This {docLabel.toLowerCase()} was sent by {data.org_name}. Questions? Reply to the original email.
        </p>
      </div>
    </div>
  );
}
