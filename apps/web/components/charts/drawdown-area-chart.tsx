"use client";

/**
 * TradeDNA Phase 8C - Underwater Drawdown Curve Chart Component.
 */

import React, { useState } from "react";
import { EquityPoint } from "@/lib/types";
import { cn } from "@/lib/utils";

interface DrawdownAreaChartProps {
  data: EquityPoint[];
  maxDrawdownPct?: string;
  className?: string;
  height?: number;
}

export function DrawdownAreaChart({
  data,
  maxDrawdownPct = "0.00%",
  className,
  height = 200,
}: DrawdownAreaChartProps) {
  const [hovered, setHovered] = useState<EquityPoint | null>(null);

  if (!data || data.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center text-xs font-mono text-slate-500",
          className
        )}
        style={{ height }}
      >
        No drawdown data available.
      </div>
    );
  }

  const ddValues = data.map((d) => parseFloat(d.drawdown_pct.replace("%", "")));
  const maxDD = Math.max(...ddValues, parseFloat(maxDrawdownPct.replace("%", "")), 5);

  const width = 800;
  const margin = { top: 15, right: 25, bottom: 25, left: 55 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;

  const points = data.map((d, i) => {
    const val = parseFloat(d.drawdown_pct.replace("%", ""));
    const x = margin.left + (i / Math.max(1, data.length - 1)) * chartWidth;
    const y = margin.top + (val / maxDD) * chartHeight;
    return { x, y, data: d };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaPath = `M ${margin.left} ${margin.top} ${points.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ")} L ${margin.left + chartWidth} ${margin.top} Z`;

  return (
    <div className={cn("flex flex-col space-y-2", className)}>
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-rose-500" />
          <span className="font-semibold text-slate-300">Underwater Drawdown Trajectory</span>
        </div>
        <span className="font-mono text-rose-400 font-bold">
          Max Threshold: {maxDrawdownPct}
        </span>
      </div>

      <div className="relative rounded-xl border border-slate-800/80 bg-[#0a0f1d] p-2">
        {hovered && (
          <div className="absolute top-2 right-2 z-10 rounded-lg border border-slate-700 bg-slate-950/90 p-2 text-xs shadow-xl pointer-events-none">
            <div className="text-[10px] text-slate-400 font-mono">
              {new Date(hovered.timestamp).toLocaleString()}
            </div>
            <div className="text-sm font-bold font-mono text-rose-400">
              Drawdown: -{hovered.drawdown_pct}
            </div>
          </div>
        )}

        <svg viewBox={`0 0 ${width} ${height}`} className="w-full select-none" style={{ height }}>
          <defs>
            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.05" />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.4" />
            </linearGradient>
          </defs>

          {/* Zero baseline (Peak) */}
          <line
            x1={margin.left}
            y1={margin.top}
            x2={width - margin.right}
            y2={margin.top}
            stroke="#10b981"
            strokeWidth="1.5"
          />
          <text
            x={margin.left - 6}
            y={margin.top + 4}
            textAnchor="end"
            fill="#10b981"
            fontSize="10"
            fontFamily="monospace"
          >
            0.0%
          </text>

          {/* Max DD line */}
          <line
            x1={margin.left}
            y1={margin.top + chartHeight}
            x2={width - margin.right}
            y2={margin.top + chartHeight}
            stroke="#1e293b"
            strokeDasharray="4 4"
          />
          <text
            x={margin.left - 6}
            y={margin.top + chartHeight}
            textAnchor="end"
            fill="#f43f5e"
            fontSize="10"
            fontFamily="monospace"
          >
            -{maxDD.toFixed(1)}%
          </text>

          {/* Drawdown Area */}
          <path d={areaPath} fill="url(#ddGrad)" />

          {/* Drawdown Line */}
          <path
            d={linePath}
            fill="none"
            stroke="#f43f5e"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
}
