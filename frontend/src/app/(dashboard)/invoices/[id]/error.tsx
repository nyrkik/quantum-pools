"use client";

import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";

export default function InvoiceError({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <p className="text-muted-foreground">Something went wrong loading this page</p>
      <p className="text-xs text-muted-foreground/60">{error.message}</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => reset()}>Retry</Button>
        <Button variant="outline" size="sm" onClick={() => router.push("/invoices")}>Back to Invoices</Button>
      </div>
    </div>
  );
}
