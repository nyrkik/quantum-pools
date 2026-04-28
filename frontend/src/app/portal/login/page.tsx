"use client";

import { useState } from "react";
import { Loader2, Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function PortalLoginPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || submitting) return;
    setSubmitting(true);
    try {
      // We deliberately ignore the response status — the API always returns
      // 200 even when the email is unknown (enumeration protection). The
      // confirmation screen below makes the same promise either way.
      await fetch("/api/v1/portal/request-link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
        credentials: "include",
      });
    } catch {
      // Even on network error, surface the same message — the alternative
      // is leaking the request flow to whoever's watching.
    } finally {
      setSent(true);
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md shadow-sm">
        <CardContent className="p-6 sm:p-8">
          {sent ? (
            <div className="text-center space-y-3">
              <Mail className="h-10 w-10 text-primary mx-auto" />
              <h1 className="text-xl font-semibold">Check your email</h1>
              <p className="text-sm text-muted-foreground">
                If <strong>{email}</strong> is on file, we just sent a sign-in link.
                The link expires in 15 minutes.
              </p>
              <p className="text-xs text-muted-foreground">
                Didn&apos;t arrive? Check spam, or{" "}
                <button
                  type="button"
                  onClick={() => setSent(false)}
                  className="text-primary hover:underline"
                >
                  try a different email
                </button>
                .
              </p>
            </div>
          ) : (
            <>
              <h1 className="text-xl font-semibold mb-1">Sign in</h1>
              <p className="text-sm text-muted-foreground mb-6">
                Enter the email your service company has on file. We&apos;ll send
                you a one-click sign-in link.
              </p>
              <form onSubmit={onSubmit} className="space-y-4">
                <Input
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={submitting}
                  autoFocus
                />
                <Button type="submit" className="w-full" disabled={submitting || !email.trim()}>
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Sending…
                    </>
                  ) : (
                    "Send sign-in link"
                  )}
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
