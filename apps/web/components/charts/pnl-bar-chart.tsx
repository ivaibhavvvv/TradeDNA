"use client";

/**
 * TradeDNA Phase 8C - Daily Realized P&L Bar Chart Component.
 */

import React, { useState } from "react";
import { DailyPnlPoint } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface PnlBarChartProps {
  data: DailyPnlPoint[];
  currency?: string;
  className?: string;
  height?: number;
}

export function PnlBarChart({
  data,
  currency = "USD",
  className,
  height = 240,
}: PnlBarChartProps) {
  const [hovered, setHovered] = useState<DailyPnlPoint | null>(null);

  if (!data || data.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center text-xs font-mono text-slate-500",
          className
        )}
        style={{ height }}
      >
        No daily P&L data recorded in selected window.
      </div>
    );
  }

  const values = data.map((d) => parseFloat(d.pnl));
  const maxAbs = Math.max(...values.map(Math.abs), 100);
  const width = 800;
  const margin = { top: 20, right: 20, bottom: 30, left: 55 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const zeroY = margin.top + chartHeight / 2;

  const barWidth = Math.max(4, Math.min(24, (chartWidth / data.length) * 0.7));

  return (
    <div className={cn("flex flex-col space-y-2", className)}>
      <div className="relative rounded-xl border border-slate-800/80 bg-[#0a0f1d] p-2">
        {hovered && (
          <div className="absolute top-3 right-3 z-10 rounded-lg border border-slate-700 bg-slate-950/90 p-2 text-xs shadow-xl backdrop-blur-sm pointer-events-none">
            <div className="text-[10px] text-slate-400 font-mono">{hovered.date}</div>
            <div
              className={cn(
                "text-sm font-bold font-mono",
                parseFloat(hovered.pnl) >= 0 ? "text-emerald-400" : "text-rose-400"
              )}
            >
              {formatCurrency(hovered.pnl, currency)}
            </div>
            <div className="text-[10px] text-slate-300 font-mono">
              {hovered.trades_count} trades • {hovered.win_rate} win rate
            </div>
          </div>
        )}

        <svg viewBox={`0 0 ${width} ${height}`} className="w-full select-none" style={{ height }}>
          {/* Zero baseline */}
          <line
            x1={margin.left}
            y1={zeroY}
            x2={width - margin.right}
            y2={zeroY}
            stroke="#475569"
            strokeWidth="1.5"
          />

          {/* Upper and lower dashed grid */}
          <line
            x1={margin.left}
            y1={margin.top}
            x2={width - margin.right}
            y2={margin.top}
            stroke="#1e293b"
            strokeDasharray="4 4"
          />
          <text
            x={margin.left - 6}
            y={margin.top + 4}
            textAnchor="end"
            fill="#64748b"
            fontSize="10"
            fontFamily="monospace"
          >
            +${maxAbs.toFixed(0)}
          </text>

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
            fill="#64748b"
            fontSize="10"
            fontFamily="monospace"
          >
            -${maxAbs.toFixed(0)}
          </text>

          {/* Bars */}
          {data.map((d, i) => {
            const val = parseFloat(d.pnl);
            const isPos = val >= 0;
            const barH = (Math.abs(val) / maxAbs) * (chartHeight / 2);
            const x = margin.left + (i / Math.max(1, data.length - 1)) * (chartWidth - barWidth);
            const y = isPos ? zeroY - barH : zeroY;

            return (
              <rect
                key={i}
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(2, barH)}
                rx={2}
                fill={isPos ? "#10b981" : "#f43f5e"}
                opacity={hovered?.date === d.date ? 1 : 0.85}
                className="cursor-pointer transition-all hover:opacity-100"
                onMouseEnter={() => setHovered(d)}
                onMouseLeave={() => setHovered(null)}
              />
            );
          })}
        </svg>
      </div>
    </div>
  );
}
