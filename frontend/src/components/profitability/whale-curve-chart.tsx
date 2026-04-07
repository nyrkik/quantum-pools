"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { WhaleCurvePoint } from "@/types/profitability";

interface WhaleCurveChartProps {
  data: WhaleCurvePoint[];
  hoveredId: string | null;
}

export function WhaleCurveChart({ data, hoveredId }: WhaleCurveChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Whale Curve — Cumulative Profitability</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="rank"
                label={{ value: "Account Rank", position: "insideBottom", offset: -5 }}
              />
              <YAxis
                label={{ value: "Cumulative Profit %", angle: -90, position: "insideLeft" }}
              />
              <Tooltip
                formatter={(value) => [`${(value as number).toFixed(1)}%`, "Cumulative Profit"]}
                labelFormatter={(rank) => {
                  const pt = data.find((w) => w.rank === rank);
                  return pt ? pt.customer_name : `#${rank}`;
                }}
              />
              <Line
                type="monotone"
                dataKey="cumulative_profit_pct"
                stroke="#2989BE"
                strokeWidth={2}
                dot={(props: Record<string, unknown>) => {
                  const pt = data[props.index as number];
                  if (!pt || pt.customer_id !== hoveredId) return <circle key={props.index as number} r={0} />;
                  return <circle key={props.index as number} cx={props.cx as number} cy={props.cy as number} r={6} fill="#2989BE" stroke="#fff" strokeWidth={2} />;
                }}
                activeDot={{ r: 6, stroke: "#fff", strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-muted-foreground py-12 text-center">
            No data yet
          </p>
        )}
      </CardContent>
    </Card>
  );
}
