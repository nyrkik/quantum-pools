"use client";

import { useState, useEffect, use } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle2, CreditCard, Shield } from "lucide-react";
import { loadStripe, Stripe } from "@stripe/stripe-js";
import { Elements, CardElement, useStripe, useElements } from "@stripe/react-stripe-js";

interface CardStatus {
  customer_name: string;
  org_name: string | null;
  org_color: string | null;
  has_card: boolean;
  card_last4: string | null;
  card_brand: string | null;
  card_exp_month: number | null;
  card_exp_year: number | null;
  autopay_enabled: boolean;
}

function CardForm({
  token,
  clientSecret,
  data,
  onSuccess,
}: {
  token: string;
  clientSecret: string;
  data: CardStatus;
  onSuccess: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stripe || !elements) return;

    setSubmitting(true);
    setError("");

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) return;

    const { error: stripeError } = await stripe.confirmCardSetup(clientSecret, {
      payment_method: { card: cardElement },
    });

    if (stripeError) {
      setError(stripeError.message || "Failed to save card");
      setSubmitting(false);
      return;
    }

    // Enable autopay by default when saving card
    try {
      await fetch(`/api/v1/public/card/${token}/autopay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable: true }),
      });
    } catch {
      // Non-critical — card is saved regardless
    }

    setSubmitting(false);
    onSuccess();
  };

  const brandColor = data.org_color || "#2563eb";

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="bg-white border rounded-lg p-4">
        <CardElement
          options={{
            style: {
              base: {
                fontSize: "16px",
                color: "#1e293b",
                "::placeholder": { color: "#94a3b8" },
              },
              invalid: { color: "#ef4444" },
            },
          }}
        />
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <Button
        type="submit"
        className="w-full h-11 text-base gap-2"
        style={{ backgroundColor: brandColor }}
        disabled={submitting || !stripe}
      >
        {submitting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <CreditCard className="h-4 w-4" />
        )}
        {data.has_card ? "Update Card" : "Save Card"}
      </Button>

      <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
        <Shield className="h-3 w-3" />
        <span>Secured by Stripe. Your card details never touch our servers.</span>
      </div>
    </form>
  );
}

export default function CardSetupPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<CardStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(`/api/v1/public/card/${token}`)
      .then(async (res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((d) => setData(d))
      .catch(() => setError("This link is no longer valid."))
      .finally(() => setLoading(false));
  }, [token]);

  const startSetup = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/public/card/${token}/setup-intent`, { method: "POST" });
      if (!res.ok) throw new Error();
      const result = await res.json();
      setClientSecret(result.client_secret);
      setStripePromise(loadStripe(result.publishable_key));
    } catch {
      setError("Unable to start card setup. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // Auto-start setup intent on load if no card saved
  useEffect(() => {
    if (data && !data.has_card && !clientSecret) {
      startSetup();
    }
  }, [data]);

  if (loading && !data) {
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
            <CreditCard className="h-12 w-12 text-slate-300 mx-auto mb-4" />
            <p className="text-lg font-medium text-slate-700">Link Unavailable</p>
            <p className="text-sm text-slate-500 mt-2">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const brandColor = data.org_color || "#2563eb";

  if (saved) {
    return (
      <div className="min-h-screen bg-slate-50 py-8 px-4">
        <div className="max-w-md mx-auto space-y-4">
          <div className="text-center space-y-2">
            {data.org_name && <h1 className="text-lg font-semibold text-slate-800">{data.org_name}</h1>}
          </div>
          <Card className="shadow-md">
            <CardContent className="py-10 text-center space-y-3">
              <CheckCircle2 className="h-12 w-12 text-green-500 mx-auto" />
              <p className="text-lg font-semibold text-slate-800">Card Saved</p>
              <p className="text-sm text-slate-500">
                AutoPay is now active. Your future invoices will be charged automatically.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="max-w-md mx-auto space-y-4">
        <div className="text-center space-y-2">
          {data.org_name && <h1 className="text-lg font-semibold text-slate-800">{data.org_name}</h1>}
          <p className="text-sm text-slate-500">Payment Method Setup</p>
        </div>

        <Card className="shadow-md">
          <CardContent className="py-6 space-y-5">
            <p className="text-sm text-slate-600">
              Hi {data.customer_name}, save a card to enable automatic payments for your pool service.
            </p>

            {/* Current card info */}
            {data.has_card && (
              <div className="bg-slate-50 rounded-lg p-4 flex items-center gap-3">
                <CreditCard className="h-5 w-5 text-slate-400" />
                <div>
                  <p className="text-sm font-medium text-slate-700">
                    {data.card_brand ? data.card_brand.charAt(0).toUpperCase() + data.card_brand.slice(1) : "Card"} ending in {data.card_last4}
                  </p>
                  <p className="text-xs text-slate-500">
                    Expires {data.card_exp_month}/{data.card_exp_year}
                  </p>
                </div>
                {data.autopay_enabled && (
                  <span className="ml-auto text-xs font-medium px-2 py-1 rounded-full bg-green-100 text-green-700">
                    AutoPay On
                  </span>
                )}
              </div>
            )}

            {/* Card form or setup button */}
            {clientSecret && stripePromise ? (
              <Elements stripe={stripePromise} options={{ clientSecret }}>
                <CardForm
                  token={token}
                  clientSecret={clientSecret}
                  data={data}
                  onSuccess={() => setSaved(true)}
                />
              </Elements>
            ) : data.has_card ? (
              <Button
                className="w-full h-11 gap-2"
                variant="outline"
                onClick={startSetup}
                disabled={loading}
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
                Update Card
              </Button>
            ) : (
              <div className="text-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400 mx-auto" />
                <p className="text-xs text-slate-400 mt-2">Setting up...</p>
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-[10px] text-slate-400 text-center">
          Manage your payment method for {data.org_name}. You can update or remove your card at any time.
        </p>
      </div>
    </div>
  );
}
