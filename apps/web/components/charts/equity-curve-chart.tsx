"use client";

/**
 * TradeDNA Phase 8C - Interactive Equity Curve Chart Component.
 * Responsive SVG area chart with High-Water Mark line, Drawdown zone,
 * interactive cursor crosshair, and period selectors.
 */

import React, { useState } from "react";
import { EquityPoint } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface EquityCurveChartProps {
  data: EquityPoint[];
  currency?: string;
  selectedPeriod?: string;
  onPeriodChange?: (period: string) => void;
  className?: string;
  height?: number;
}

export function EquityCurveChart({
  data,
  currency = "USD",
  selectedPeriod = "ALL",
  onPeriodChange,
  className,
  height = 280,
}: EquityCurveChartProps) {
  const [hoveredPoint, setHoveredPoint] = useState<EquityPoint | null>(null);
  const [hoverX, setHoverX] = useState<number | null>(null);

  const periods = ["7D", "30D", "90D", "6M", "1Y", "ALL"];

  if (!data || data.length === 0) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center",
          className
        )}
        style={{ height }}
      >
        <span className="text-xs font-mono text-slate-500">
          Awaiting closed canonical trades to plot equity trajectory.
        </span>
      </div>
    );
  }

  // Calculate scales
  const values = data.map((d) => parseFloat(d.equity));
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const padding = (maxVal - minVal) * 0.1 || 100;
  const yMin = Math.max(0, minVal - padding);
  const yMax = maxVal + padding;
  const yRange = yMax - yMin || 1;

  const width = 800;
  const svgHeight = height;
  const margin = { top: 20, right: 30, bottom: 30, left: 60 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = svgHeight - margin.top - margin.bottom;

  // Build SVG path points
  const points = data.map((d, i) => {
    const x = margin.left + (i / Math.max(1, data.length - 1)) * chartWidth;
    const y = margin.top + chartHeight - ((parseFloat(d.equity) - yMin) / yRange) * chartHeight;
    return { x, y, data: d };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${margin.top + chartHeight} L ${points[0].x.toFixed(1)} ${margin.top + chartHeight} Z`;

  // High-water mark line
  let peak = -Infinity;
  const hwmPoints = data.map((d, i) => {
    const val = parseFloat(d.equity);
    if (val > peak) peak = val;
    const x = margin.left + (i / Math.max(1, data.length - 1)) * chartWidth;
    const y = margin.top + chartHeight - ((peak - yMin) / yRange) * chartHeight;
    return { x, y };
  });
  const hwmPath = hwmPoints.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, (clientX - (margin.left * rect.width) / width) / ((chartWidth * rect.width) / width)));
    const index = Math.round(ratio * (data.length - 1));
    if (data[index]) {
      setHoveredPoint(data[index]);
      setHoverX(points[index]?.x ?? null);
    }
  };

  const handleMouseLeave = () => {
    setHoveredPoint(null);
    setHoverX(null);
  };

  return (
    <div className={cn("flex flex-col space-y-3", className)}>
      {/* Header with period filter */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-cyan-400" />
            <span className="text-xs font-semibold text-slate-300">Equity Trajectory</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-slate-600" />
            <span className="text-xs text-slate-400">High-Water Mark</span>
          </div>
        </div>

        {onPeriodChange && (
          <div className="flex items-center rounded-lg bg-slate-900/90 p-0.5 border border-slate-800">
            {periods.map((p) => (
              <button
                key={p}
                onClick={() => onPeriodChange(p)}
                className={cn(
                  "rounded px-2.5 py-1 text-[11px] font-mono font-medium transition-all",
                  selectedPeriod === p
                    ? "bg-slate-800 text-cyan-400 font-bold shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                {p}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* SVG Canvas Area */}
      <div className="relative rounded-xl border border-slate-800/80 bg-[#0a0f1d] p-2">
        {hoveredPoint && (
          <div className="absolute top-4 left-4 z-10 rounded-lg border border-slate-700 bg-slate-950/90 p-2.5 shadow-xl backdrop-blur-sm pointer-events-none text-xs">
            <div className="text-[10px] text-slate-400 font-mono">
              {new Date(hoveredPoint.timestamp).toLocaleString()}
            </div>
            <div className="text-sm font-bold font-mono text-cyan-400 mt-0.5">
              Equity: {formatCurrency(hoveredPoint.equity, currency)}
            </div>
            <div className="text-[11px] text-slate-300 font-mono">
              Drawdown: {formatCurrency(hoveredPoint.drawdown, currency)} ({hoveredPoint.drawdown_pct})
            </div>
          </div>
        )}

        <svg
          viewBox={`0 0 ${width} ${svgHeight}`}
          className="w-full overflow-visible select-none"
          style={{ height }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.00" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
            const y = margin.top + chartHeight * (1 - pct);
            const val = yMin + yRange * pct;
            return (
              <g key={i}>
                <line
                  x1={margin.left}
                  y1={y}
                  x2={width - margin.right}
                  y2={y}
                  stroke="#1e293b"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                />
                <text
                  x={margin.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fill="#64748b"
                  fontSize="10"
                  fontFamily="monospace"
                >
                  ${(val / 1000).toFixed(1)}k
                </text>
              </g>
            );
          })}

          {/* Area under equity */}
          <path d={areaPath} fill="url(#equityGrad)" />

          {/* High water mark dashed line */}
          <path
            d={hwmPath}
            fill="none"
            stroke="#475569"
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />

          {/* Equity Line */}
          <path
            d={linePath}
            fill="none"
            stroke="#06b6d4"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Hover Crosshair line */}
          {hoverX !== null && (
            <line
              x1={hoverX}
              y1={margin.top}
              x2={hoverX}
              y2={margin.top + chartHeight}
              stroke="#22d3ee"
              strokeWidth="1.5"
              strokeDasharray="3 3"
            />
          )}
        </svg>
      </div>
    </div>
  );
}
