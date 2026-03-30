"use client";

import { useState, useEffect, use } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, FileText } from "lucide-react";
import { getBackendOrigin } from "@/lib/api";

interface EstimateData {
  estimate_number: string;
  subject: string | null;
  customer_name: string | null;
  org_name: string | null;
  org_logo_url: string | null;
  org_color: string | null;
  line_items: { description: string; quantity: number; unit_price: number; total: number }[];
  total: number;
  status: string;
  approved_at: string | null;
}

export default function ApprovePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<EstimateData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const backendOrigin = getBackendOrigin();

  useEffect(() => {
    fetch(`${backendOrigin}/api/v1/public/estimate/${token}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("Estimate not found");
        return res.json();
      })
      .then((d) => {
        setData(d);
        if (d.status === "approved") setApproved(true);
        if (d.customer_name) setName(d.customer_name);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, backendOrigin]);

  const handleApprove = async () => {
    if (!name.trim()) return;
    setApproving(true);
    try {
      const res = await fetch(`${backendOrigin}/api/v1/public/estimate/${token}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), email: email.trim() || null }),
      });
      if (!res.ok) throw new Error("Approval failed");
      setApproved(true);
    } catch {
      setError("Failed to submit approval. Please try again.");
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
            <p className="text-lg font-medium text-slate-700">{error || "Estimate not found"}</p>
            <p className="text-sm text-slate-500 mt-2">This link may have expired or is invalid.</p>
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

            {/* Line items */}
            <div className="space-y-2">
              <div className="grid grid-cols-[1fr_60px_80px_80px] gap-2 text-xs text-slate-500 font-medium uppercase tracking-wide border-b pb-2">
                <span>Description</span>
                <span className="text-center">Qty</span>
                <span className="text-right">Price</span>
                <span className="text-right">Total</span>
              </div>
              {data.line_items.map((li, i) => (
                <div key={i} className="grid grid-cols-[1fr_60px_80px_80px] gap-2 text-sm py-1.5">
                  <span>{li.description}</span>
                  <span className="text-center text-slate-500">{li.quantity}</span>
                  <span className="text-right text-slate-500">${li.unit_price.toFixed(2)}</span>
                  <span className="text-right font-medium">${li.total.toFixed(2)}</span>
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
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center space-y-2">
                <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto" />
                <p className="text-sm font-medium text-green-800">Estimate Approved</p>
                <p className="text-xs text-green-600">Thank you! We'll be in touch to schedule the work.</p>
              </div>
            ) : (
              <div className="space-y-3 border-t pt-4">
                <p className="text-sm text-slate-600">To approve this estimate, please confirm below:</p>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Your Name *</Label>
                    <Input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Full name"
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Email (optional)</Label>
                    <Input
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="your@email.com"
                      className="h-9"
                      type="email"
                    />
                  </div>
                </div>
                <Button
                  className="w-full"
                  style={{ backgroundColor: brandColor }}
                  disabled={!name.trim() || approving}
                  onClick={handleApprove}
                >
                  {approving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                  Approve Estimate
                </Button>
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
