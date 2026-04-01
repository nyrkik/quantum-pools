"use client";

import { useState, useEffect, use } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, CheckCircle2, FileText } from "lucide-react";

interface EstimateData {
  estimate_number: string;
  subject: string | null;
  customer_name: string | null;
  org_name: string | null;
  org_logo_url: string | null;
  org_color: string | null;
  line_items: { description: string; quantity: number; unit_price: number; total: number }[];
  total: number;
  terms: {
    payment_terms_days: number;
    estimate_validity_days: number;
    late_fee_pct: number;
    warranty_days: number;
    custom_terms: string | null;
  };
  status: string;
  approved_at: string | null;
  approval_evidence: {
    signed_by: string | null;
    signature: string | null;
    sent_to_email: string | null;
    ip_address: string | null;
    method: string | null;
    timestamp: string | null;
  } | null;
  revision_count: number;
  revised_at: string | null;
}

export default function ApprovePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const isAdminView = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("view") === "admin";
  const [data, setData] = useState<EstimateData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);
  const [consent, setConsent] = useState(false);
  const [signature, setSignature] = useState("");
  const [approveError, setApproveError] = useState("");
  useEffect(() => {
    fetch(`/api/v1/public/estimate/${token}`)
      .then(async (res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((d) => {
        setData(d);
        if (d.status === "approved") setApproved(true);
        if (d.recipient_name) setSignature(d.recipient_name);
      })
      .catch(() => setError("This estimate is no longer available."))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleApprove = async () => {
    if (!signature.trim() || !consent) return;
    setApproving(true);
    setApproveError("");
    try {
      const res = await fetch(`/api/v1/public/estimate/${token}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: signature.trim(),
          signature: signature.trim(),
          user_agent: navigator.userAgent,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Approval failed");
      }
      setApproved(true);
    } catch (e: unknown) {
      setApproveError(e instanceof Error ? e.message : "Failed to submit approval.");
    } finally {
      setApproving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Card className="max-w-md w-full mx-4">
          <CardContent className="py-12 text-center">
            <FileText className="h-12 w-12 text-slate-300 mx-auto mb-4" />
            <p className="text-lg font-medium text-slate-700">Estimate Unavailable</p>
            <p className="text-sm text-slate-500 mt-2">This estimate is no longer available or the link has expired. Please contact us if you need assistance.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const brandColor = data.org_color || "#2563eb";

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="max-w-lg mx-auto space-y-4">
        {/* Header */}
        <div className="text-center space-y-2">
          {data.org_name && (
            <h1 className="text-lg font-semibold text-slate-800">{data.org_name}</h1>
          )}
          <p className="text-sm text-slate-500">Estimate {data.estimate_number}</p>
        </div>

        {/* Estimate card */}
        <Card className="shadow-md">
          <CardContent className="py-6 space-y-5">
            {data.subject && (
              <h2 className="text-base font-semibold text-slate-800">{data.subject}</h2>
            )}

            {data.customer_name && (
              <p className="text-sm text-slate-500">Prepared for {data.customer_name}</p>
            )}

            {/* Revision banner removed — customer always sees the latest version.
                Internal revision tracking is in the admin view only. */}

            {/* Line items */}
            <div className="space-y-2">
              {/* Desktop table layout */}
              <div className="hidden sm:grid grid-cols-[1fr_60px_80px_80px] gap-2 text-xs text-slate-500 font-medium uppercase tracking-wide border-b pb-2">
                <span>Description</span>
                <span className="text-center">Qty</span>
                <span className="text-right">Price</span>
                <span className="text-right">Total</span>
              </div>
              {data.line_items.map((li, i) => (
                <div key={i}>
                  {/* Desktop row */}
                  <div className="hidden sm:grid grid-cols-[1fr_60px_80px_80px] gap-2 text-sm py-1.5">
                    <span className="break-words">{li.description}</span>
                    <span className="text-center text-slate-500">{li.quantity}</span>
                    <span className="text-right text-slate-500">${li.unit_price.toFixed(2)}</span>
                    <span className="text-right font-medium">${li.total.toFixed(2)}</span>
                  </div>
                  {/* Mobile card */}
                  <div className="sm:hidden border-b py-2 space-y-1">
                    <p className="text-sm font-medium break-words">{li.description}</p>
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Qty {li.quantity} x ${li.unit_price.toFixed(2)}</span>
                      <span className="font-medium text-sm text-slate-800">${li.total.toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              ))}
              <div className="border-t pt-3 flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-800">Total</span>
                <span className="text-lg font-bold" style={{ color: brandColor }}>
                  ${data.total.toFixed(2)}
                </span>
              </div>
            </div>

            {/* Approval section */}
            {approved ? (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 space-y-3">
                <div className="text-center space-y-2">
                  <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto" />
                  <p className="text-sm font-medium text-green-800">Estimate Approved</p>
                  <p className="text-xs text-green-600">Thank you! We&apos;ll be in touch to schedule the work.</p>
                </div>
                {data.approval_evidence && (
                  <div className="border-t border-green-200 pt-3 mt-3 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wide text-green-700 font-semibold">Approval Verification</p>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-green-800">
                      {data.approval_evidence.signature && (
                        <>
                          <span className="text-green-600">Signed by</span>
                          <span className="italic">{data.approval_evidence.signature}</span>
                        </>
                      )}
                      {data.approval_evidence.sent_to_email && (
                        <>
                          <span className="text-green-600">Sent to</span>
                          <span>{data.approval_evidence.sent_to_email}</span>
                        </>
                      )}
                      {data.approval_evidence.timestamp && (
                        <>
                          <span className="text-green-600">Date & time</span>
                          <span>{new Date(data.approval_evidence.timestamp).toLocaleString()}</span>
                        </>
                      )}
                      {data.approval_evidence.ip_address && (
                        <>
                          <span className="text-green-600">IP address</span>
                          <span>{data.approval_evidence.ip_address}</span>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4 border-t pt-4">
                {/* Terms */}
                <div className="space-y-2">
                  <p className="text-xs font-medium text-slate-600 uppercase tracking-wide">Terms & Conditions</p>
                  {data.terms?.custom_terms ? (
                    <div className="text-[11px] text-slate-500 leading-relaxed max-h-40 overflow-y-auto pr-1 whitespace-pre-line">
                      {data.terms.custom_terms}
                    </div>
                  ) : (
                    <div className="text-[11px] text-slate-500 leading-relaxed space-y-1.5 max-h-40 overflow-y-auto pr-1">
                      <p>1. <strong>Scope of Work.</strong> This estimate covers only the services and materials described above. Any additional work discovered during service will require separate written approval before proceeding.</p>
                      <p>2. <strong>Pricing.</strong> Prices are valid for {data.terms?.estimate_validity_days ?? 30} days from the date of this estimate. Material costs are subject to change based on supplier pricing at time of service.</p>
                      <p>3. <strong>Payment.</strong> Payment is due net {data.terms?.payment_terms_days ?? 30} from date of invoice unless other arrangements have been made in writing. A late fee of {data.terms?.late_fee_pct ?? 1.5}% per month may apply to overdue balances.</p>
                      <p>4. <strong>Warranty.</strong> Labor is warranted for {data.terms?.warranty_days ?? 30} days from completion. Manufacturer warranties apply to all parts and equipment installed. No warranty is provided on customer-supplied materials.</p>
                      <p>5. <strong>Access.</strong> Customer agrees to provide reasonable access to the service area. {data.org_name} is not responsible for delays caused by access issues.</p>
                      <p>6. <strong>Cancellation.</strong> Cancellation after approval may be subject to a restocking fee for any materials already ordered.</p>
                      <p>7. <strong>Liability.</strong> {data.org_name} carries general liability and workers&apos; compensation insurance. Liability is limited to the total value of this estimate.</p>
                    </div>
                  )}
                </div>

                {isAdminView ? (
                  <div className="bg-slate-50 border rounded-lg p-4 text-center">
                    <p className="text-sm text-slate-500">Awaiting customer approval</p>
                  </div>
                ) : (
                  <>
                {/* Signature */}
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Sign here</Label>
                    <Input
                      value={signature}
                      onChange={(e) => setSignature(e.target.value)}
                      placeholder="Please enter your first and last name"
                      className="h-10 text-base italic"
                      autoFocus
                    />
                  </div>
                </div>

                <div className="bg-slate-50 rounded-md p-3 border">
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-300"
                    />
                    <span className="text-xs text-slate-600 leading-relaxed">
                      I, <strong>{signature || "___"}</strong>, authorize the work described in this estimate totaling{" "}
                      <strong>${data.total.toFixed(2)}</strong> and agree to the terms and conditions above. I understand this
                      constitutes a binding authorization to proceed with the described services.
                    </span>
                  </label>
                </div>

                <Button
                  className="w-full"
                  style={{ backgroundColor: brandColor }}
                  disabled={!signature.trim() || !consent || approving}
                  onClick={handleApprove}
                >
                  {approving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                  Approve & Authorize
                </Button>

                {approveError && (
                  <p className="text-xs text-red-500 text-center">{approveError}</p>
                )}
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-[10px] text-slate-400 text-center">
          This estimate was sent by {data.org_name}. Questions? Reply to the original email.
        </p>
      </div>
    </div>
  );
}
