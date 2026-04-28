"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Phase = "consuming" | "error";

export default function PortalConsumeTokenPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("consuming");
  const [errorMsg, setErrorMsg] = useState<string>(
    "This sign-in link is invalid or has expired."
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/v1/portal/consume", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
          credentials: "include",
        });
        if (cancelled) return;
        if (res.ok) {
          // Cookie is set; portal landing reads it.
          router.replace("/portal");
          return;
        }
        const payload = await res.json().catch(() => ({}));
        if (payload?.detail) setErrorMsg(payload.detail);
        setPhase("error");
      } catch {
        if (!cancelled) setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, router]);

  if (phase === "consuming") {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-muted-foreground flex items-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin" />
          Signing you in…
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md shadow-sm">
        <CardContent className="p-6 sm:p-8 text-center space-y-3">
          <AlertCircle className="h-10 w-10 text-destructive mx-auto" />
          <h1 className="text-xl font-semibold">Sign-in link expired</h1>
          <p className="text-sm text-muted-foreground">{errorMsg}</p>
          <p className="text-xs text-muted-foreground">
            Sign-in links are valid for 15 minutes and can only be used once.
          </p>
          <Link href="/portal/login">
            <Button className="w-full mt-2">Send a new link</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
