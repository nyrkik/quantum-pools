import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  AlertTriangle,
} from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { marginColor } from "./margin-helpers";

interface SummaryCardsProps {
  revenue: number;
  cost: number;
  targetMarginPct: number;
  belowTargetCount: number;
  totalAccounts: number;
}

export function SummaryCards({ revenue, cost, targetMarginPct, belowTargetCount, totalAccounts }: SummaryCardsProps) {
  const profit = revenue - cost;
  const margin = revenue > 0 ? (profit / revenue * 100) : 0;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Monthly Revenue</CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(revenue)}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Monthly Profit</CardTitle>
          {profit >= 0 ? (
            <TrendingUp className="h-4 w-4 text-green-600" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-600" />
          )}
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${profit >= 0 ? "text-green-600" : "text-red-600"}`}>
            {formatCurrency(profit)}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Avg Margin</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${marginColor(margin, targetMarginPct)}`}>
            {margin.toFixed(1)}%
          </div>
          <p className="text-xs text-muted-foreground">Target: {targetMarginPct}%</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Below Target</CardTitle>
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-yellow-600">{belowTargetCount}</div>
          <p className="text-xs text-muted-foreground">
            of {totalAccounts} accounts
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
