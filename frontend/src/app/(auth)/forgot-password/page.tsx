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
import { toast } from "sonner";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/v1/auth/forgot-password", { email });
      setSent(true);
      toast.success("Check your email for a reset link");
    } catch {
      toast.error("Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Reset Password</CardTitle>
        <CardDescription>
          {sent
            ? "If an account exists with that email, a reset link was sent. The link expires in 1 hour."
            : "Enter your email to receive a reset link"}
        </CardDescription>
      </CardHeader>
      {!sent && (
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Sending..." : "Send reset link"}
            </Button>
            <div className="text-sm text-muted-foreground text-center space-x-1">
              <Link
                href="/forgot-email"
                className="underline hover:text-foreground"
              >
                Forgot email?
              </Link>
              <span>&middot;</span>
              <Link href="/login" className="underline hover:text-foreground">
                Back to sign in
              </Link>
            </div>
          </CardFooter>
        </form>
      )}
    </Card>
  );
}
