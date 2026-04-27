"use client";

/**
 * Phase 3d.2 — LSI gauge.
 *
 * 3-band semicircle gauge: red (corrosive) / green (balanced) / red
 * (scaling). Pure SVG, no chart library. Mobile-first sizing — defaults
 * to 200px wide, scales with `size` prop.
 *
 * Why 3 bands not 5: amber-without-different-action is cosmetic. Tech
 * acts on either "balanced" (no chemistry adjustment past dosing
 * recommendations) or "out of balance" (corrosive AND scaling are both
 * problems requiring multi-parameter rebalance). Two-band feel,
 * three-color render to distinguish *which kind* of out-of-balance.
 *
 * Range: -1.5 to +1.5 (industry-typical extremes). Values outside
 * clamp to the edge of the dial.
 */

import { cn } from "@/lib/utils";

export interface LSIGaugeProps {
  /** LSI value, e.g. -0.34, +0.05. Clamped to [-1.5, +1.5]. */
  value: number;
  /** "corrosive" | "balanced" | "scaling" — used for the label only;
   *  band coloring is computed from `value` directly. */
  classification: "corrosive" | "balanced" | "scaling";
  /** Render in pixels (width). Height is auto-derived. */
  size?: number;
  /** Optional caption below the gauge — used to label the temp
   *  assumption ("temp: 75°F (assumed)"). */
  caption?: string;
  className?: string;
}

const RANGE_MIN = -1.5;
const RANGE_MAX = 1.5;
const BALANCED_LO = -0.3;
const BALANCED_HI = 0.3;

const COLOR_RED = "#dc2626"; // text-red-600
const COLOR_GREEN = "#16a34a"; // text-green-600
const COLOR_NEEDLE = "#0f172a"; // text-slate-900
const COLOR_TRACK_BG = "#e5e7eb"; // bg-muted-ish

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

/** Map LSI [-1.5..+1.5] to angle [-90°..+90°] (semicircle). */
function valueToAngle(value: number): number {
  const clamped = clamp(value, RANGE_MIN, RANGE_MAX);
  const fraction = (clamped - RANGE_MIN) / (RANGE_MAX - RANGE_MIN);
  return -90 + fraction * 180;
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arc(
  cx: number, cy: number, r: number,
  startAngle: number, endAngle: number,
): string {
  const start = polar(cx, cy, r, endAngle);
  const end = polar(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

export function LSIGauge({
  value,
  classification,
  size = 200,
  caption,
  className,
}: LSIGaugeProps) {
  const width = size;
  const height = Math.round(size * 0.65); // semicircle + label space
  const cx = width / 2;
  const cy = width / 2; // arc origin sits at semicircle center
  const r = width * 0.4;
  const trackWidth = Math.max(8, Math.round(width * 0.06));

  // Band angles. The semicircle spans -90° (left) to +90° (right).
  const ANGLE_BAL_LO = valueToAngle(BALANCED_LO);
  const ANGLE_BAL_HI = valueToAngle(BALANCED_HI);
  const needleAngle = valueToAngle(value);
  const needleEnd = polar(cx, cy, r - 5, needleAngle);

  return (
    <div
      className={cn("inline-flex flex-col items-center", className)}
      role="img"
      aria-label={`LSI ${value.toFixed(2)} (${classification})`}
    >
      <svg
        width={width}
        height={height + 30}
        viewBox={`0 0 ${width} ${height + 30}`}
        className="overflow-visible"
      >
        {/* Track shadow */}
        <path
          d={arc(cx, cy, r, -90, 90)}
          stroke={COLOR_TRACK_BG}
          strokeWidth={trackWidth + 2}
          fill="none"
          strokeLinecap="round"
        />
        {/* Corrosive band (left red) */}
        <path
          d={arc(cx, cy, r, -90, ANGLE_BAL_LO)}
          stroke={COLOR_RED}
          strokeWidth={trackWidth}
          fill="none"
          strokeLinecap="round"
        />
        {/* Balanced band (center green) */}
        <path
          d={arc(cx, cy, r, ANGLE_BAL_LO, ANGLE_BAL_HI)}
          stroke={COLOR_GREEN}
          strokeWidth={trackWidth}
          fill="none"
        />
        {/* Scaling band (right red) */}
        <path
          d={arc(cx, cy, r, ANGLE_BAL_HI, 90)}
          stroke={COLOR_RED}
          strokeWidth={trackWidth}
          fill="none"
          strokeLinecap="round"
        />
        {/* Needle */}
        <line
          x1={cx} y1={cy}
          x2={needleEnd.x} y2={needleEnd.y}
          stroke={COLOR_NEEDLE}
          strokeWidth={3}
          strokeLinecap="round"
        />
        {/* Pivot dot */}
        <circle cx={cx} cy={cy} r={5} fill={COLOR_NEEDLE} />
        {/* Numeric value below pivot */}
        <text
          x={cx}
          y={cy + 26}
          textAnchor="middle"
          className="fill-foreground text-lg font-semibold"
        >
          {value >= 0 ? "+" : ""}{value.toFixed(2)}
        </text>
      </svg>
      <div className="text-sm text-muted-foreground capitalize">
        {classification}
      </div>
      {caption ? (
        <div className="text-xs text-muted-foreground mt-1">{caption}</div>
      ) : null}
    </div>
  );
}
