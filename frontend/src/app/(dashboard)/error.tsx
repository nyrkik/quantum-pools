"use client";

import { Button } from "@/components/ui/button";

export default function DashboardError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 px-4">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <pre className="text-xs text-destructive bg-destructive/10 rounded p-3 max-w-lg overflow-auto whitespace-pre-wrap">
        {error.message}
        {error.stack && "\n\n" + error.stack.split("\n").slice(0, 5).join("\n")}
      </pre>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => reset()}>Retry</Button>
        <Button variant="outline" size="sm" onClick={() => window.location.href = "/invoices"}>Back to Invoices</Button>
      </div>
    </div>
  );
}
