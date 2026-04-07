"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { formatCurrency } from "@/lib/format";

export interface ScatterPoint {
  x: number;
  y: number;
  z: number;
  name: string;
  id: string;
  rate: number;
  minutes: number;
}

interface ScatterQuadrantChartProps {
  data: ScatterPoint[];
  targetMarginPct: number;
  hoveredId: string | null;
}

export function ScatterQuadrantChart({ data, targetMarginPct, hoveredId }: ScatterQuadrantChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Rate per Hour vs Margin</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="x"
                name="$/hr"
                label={{ value: "$/hr", position: "insideBottom", offset: -5 }}
                tickFormatter={(v) => `$${v}`}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Margin"
                label={{ value: "Margin %", angle: -90, position: "insideLeft" }}
              />
              <ZAxis type="number" dataKey="z" range={[40, 200]} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-background border rounded-md shadow-md px-3 py-2 text-sm">
                      <p className="font-semibold">{d.name}</p>
                      <p className="text-muted-foreground">${d.x}/hr · {d.y.toFixed(1)}% margin</p>
                      <p className="text-muted-foreground text-xs">{formatCurrency(d.rate)}/mo · {d.minutes} min/visit</p>
                    </div>
                  );
                }}
              />
              <Scatter data={data}>
                {data.map((entry, i) => {
                  const isHovered = entry.id === hoveredId;
                  const baseColor = entry.y >= targetMarginPct ? "#22c55e" : entry.y >= 0 ? "#eab308" : "#ef4444";
                  return (
                    <Cell
                      key={i}
                      fill={isHovered ? "#2989BE" : baseColor}
                      stroke={isHovered ? "#fff" : "none"}
                      strokeWidth={isHovered ? 2 : 0}
                      r={isHovered ? 8 : undefined}
                    />
                  );
                })}
              </Scatter>
            </ScatterChart>
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
