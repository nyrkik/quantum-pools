"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Route } from "lucide-react";

export default function RoutesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Routes</h1>
        <p className="text-muted-foreground">
          Route optimization and map view
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Route className="h-5 w-5" />
            Coming in Phase 2
          </CardTitle>
          <CardDescription>
            Leaflet maps, OR-Tools VRP optimization, and drag-drop route editing
            will be available here.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Add customers, properties, and techs first to prepare for route
            optimization.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
