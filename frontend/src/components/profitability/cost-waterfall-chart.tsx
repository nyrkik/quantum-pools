"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { formatCurrency } from "@/lib/format";
import type { CostBreakdown } from "@/types/profitability";

interface CostWaterfallChartProps {
  costBreakdown: CostBreakdown;
}

export function CostWaterfallChart({ costBreakdown: cb }: CostWaterfallChartProps) {
  const waterfallData = [
    { name: "Revenue", value: cb.revenue, fill: "#3b82f6" },
    { name: "Labor", value: -cb.labor_cost, fill: "#ef4444" },
    { name: "Chemical", value: -cb.chemical_cost, fill: "#f97316" },
    { name: "Travel", value: -cb.travel_cost, fill: "#eab308" },
    { name: "Overhead", value: -cb.overhead_cost, fill: "#8b5cf6" },
    { name: "Profit", value: cb.profit, fill: cb.profit >= 0 ? "#22c55e" : "#ef4444" },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cost Breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={waterfallData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip formatter={(value) => [formatCurrency(Math.abs(value as number)), ""]} />
            <Bar dataKey="value">
              {waterfallData.map((entry, i) => (
                <Cell key={i} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
