"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Shield } from "lucide-react";

export default function EMDPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">EMD Intelligence</h1>
        <p className="text-muted-foreground">
          Inspection scraping and violation analysis
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Coming in Phase 5
          </CardTitle>
          <CardDescription>
            Playwright scraping, PDF extraction, violation severity scoring, AI
            summaries, and lead generation.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
