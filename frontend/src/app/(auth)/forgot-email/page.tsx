"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";

type RecoverResponse = {
  message: string;
  email_hint: string | null;
};

export default function ForgotEmailPage() {
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RecoverResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await api.post<RecoverResponse>("/v1/auth/recover-email", { phone });
      setResult(res);
    } catch {
      setResult({
        message: "Something went wrong. Please try again later.",
        email_hint: null,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Find your email</CardTitle>
        <CardDescription>
          {result
            ? result.email_hint
              ? "We found a matching account."
              : "If a matching account exists, we&apos;ll show a hint below."
            : "Enter the phone number on your QuantumPools account."}
        </CardDescription>
      </CardHeader>

      {result?.email_hint ? (
        <>
          <CardContent className="space-y-2">
            <p className="text-sm text-muted-foreground">Your email looks like:</p>
            <p className="font-mono text-lg">{result.email_hint}</p>
            <p className="text-xs text-muted-foreground pt-2">
              Recognize it? Sign in with that address, or use{" "}
              <Link href="/forgot-password" className="underline hover:text-foreground">
                forgot password
              </Link>{" "}
              to reset.
            </p>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button asChild className="w-full">
              <Link href="/login">Back to sign in</Link>
            </Button>
          </CardFooter>
        </>
      ) : result ? (
        <>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {result.message} If you don&apos;t have a phone on file, contact your organization
              admin to look up your email.
            </p>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button variant="outline" className="w-full" onClick={() => setResult(null)}>
              Try a different number
            </Button>
            <Link
              href="/login"
              className="text-sm text-muted-foreground underline hover:text-foreground"
            >
              Back to sign in
            </Link>
          </CardFooter>
        </>
      ) : (
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="phone">Phone number</Label>
              <Input
                id="phone"
                type="tel"
                placeholder="(555) 123-4567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
                autoFocus
              />
            </div>
            <p className="text-xs text-muted-foreground">
              We&apos;ll show you a masked hint of the email on file — enough to jog your memory
              without exposing the full address.
            </p>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Find my email
            </Button>
            <Link
              href="/login"
              className="text-sm text-muted-foreground underline hover:text-foreground"
            >
              Back to sign in
            </Link>
          </CardFooter>
        </form>
      )}
    </Card>
  );
}
