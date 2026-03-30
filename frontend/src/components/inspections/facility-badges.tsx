"use client";

import { Badge } from "@/components/ui/badge";
import type { FacilityStatus } from "./inspection-types";

export function StatusBadge({ status }: { status: FacilityStatus }) {
  switch (status) {
    case "closure":
      return <Badge variant="destructive" className="text-xs font-semibold">Closed</Badge>;
    case "reinspection":
      return <Badge variant="outline" className="text-xs font-semibold border-amber-400 text-amber-600">Reinspection</Badge>;
    case "violations":
      return <Badge variant="outline" className="text-xs font-semibold border-amber-400 text-amber-600">Open</Badge>;
    case "compliant":
      return <Badge className="text-xs font-semibold bg-green-600 hover:bg-green-700 text-white">Open</Badge>;
  }
}
