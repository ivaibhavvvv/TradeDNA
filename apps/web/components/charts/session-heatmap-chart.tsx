"use client";

/**
 * TradeDNA Phase 8C - 24-Hour & Session Heatmap Chart Component.
 */

import React, { useState } from "react";
import { HourlyPoint, SessionItem } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface SessionHeatmapChartProps {
  sessions: SessionItem[];
  hourly: HourlyPoint[];
  currency?: string;
  className?: string;
}

export function SessionHeatmapChart({
  sessions,
  hourly,
  currency = "USD",
  className,
}: SessionHeatmapChartProps) {
  const [hoveredHour, setHoveredHour] = useState<HourlyPoint | null>(null);

  const hours = Array.from({ length: 24 }).map((_, h) => {
    const found = hourly.find((x) => x.hour === h);
    return found || { hour: h, trade_count: 0, net_pnl: "0.00" };
  });

  const maxTrades = Math.max(...hours.map((h) => h.trade_count), 1);

  return (
    <div className={cn("space-y-4", className)}>
      {/* 24-Hour Heatmap Bar Matrix */}
      <div className="space-y-2">
        <div className="flex justify-between items-center text-xs">
          <span className="font-semibold text-slate-300">24-Hour Trading Volume Activity (UTC)</span>
          {hoveredHour && (
            <span className="font-mono text-cyan-400 font-bold">
              {hoveredHour.hour.toString().padStart(2, "0")}:00 UTC • {hoveredHour.trade_count} trades ({formatCurrency(hoveredHour.net_pnl, currency)})
            </span>
          )}
        </div>

        <div className="grid grid-cols-12 sm:grid-cols-24 gap-1 p-2 rounded-xl border border-slate-800 bg-[#0a0f1d]">
          {hours.map((h) => {
            const intensity = h.trade_count / maxTrades;
            let bg = "bg-slate-900 border-slate-800";
            if (h.trade_count > 0) {
              if (intensity > 0.6) bg = "bg-cyan-500 border-cyan-400 text-black";
              else if (intensity > 0.3) bg = "bg-cyan-700/80 border-cyan-600 text-white";
              else bg = "bg-cyan-950/80 border-cyan-900 text-cyan-300";
            }

            return (
              <div
                key={h.hour}
                onMouseEnter={() => setHoveredHour(h)}
                onMouseLeave={() => setHoveredHour(null)}
                className={cn(
                  "flex flex-col items-center justify-center rounded p-1 text-[10px] font-mono cursor-pointer border transition-all hover:scale-105 h-12",
                  bg
                )}
              >
                <span className="font-bold">{h.hour}</span>
                <span className="text-[9px] opacity-80">{h.trade_count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Session Comparison Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {sessions.map((s) => {
          const isProfit = parseFloat(s.net_pnl) >= 0;
          return (
            <div
              key={s.session_name}
              className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 space-y-2 text-xs"
            >
              <div className="flex justify-between items-center">
                <span className="font-bold text-slate-200 font-mono">
                  {s.session_name.replace(/_/g, " ")}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {s.trade_count} Trades
                </span>
              </div>

              <div className="flex justify-between items-baseline">
                <span className="text-slate-400">Net Realized:</span>
                <span
                  className={cn(
                    "font-bold font-mono text-sm",
                    isProfit ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  {formatCurrency(s.net_pnl, currency)}
                </span>
              </div>

              <div className="flex justify-between text-[11px] text-slate-400 border-t border-slate-800/60 pt-2 font-mono">
                <span>Win Rate: {s.win_rate}</span>
                <span>PF: {s.profit_factor}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
