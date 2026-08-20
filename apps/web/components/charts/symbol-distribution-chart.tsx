"use client";

/**
 * TradeDNA Phase 8C - Symbol Ranking & Volume Distribution Chart Component.
 */

import React from "react";
import { InstrumentItem } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface SymbolDistributionChartProps {
  instruments: InstrumentItem[];
  currency?: string;
  className?: string;
}

export function SymbolDistributionChart({
  instruments,
  currency = "USD",
  className,
}: SymbolDistributionChartProps) {
  if (!instruments || instruments.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-800 p-6 text-center text-xs font-mono text-slate-500">
        No symbol distribution records available.
      </div>
    );
  }

  const maxVolume = Math.max(...instruments.map((i) => parseFloat(i.volume_lots)), 1);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="text-xs font-semibold text-slate-300">Symbol Volume & Realized P&L Concentration</div>
      <div className="space-y-2">
        {instruments.map((inst) => {
          const vol = parseFloat(inst.volume_lots);
          const pnl = parseFloat(inst.net_pnl);
          const isProfit = pnl >= 0;
          const barWidthPct = Math.max(5, (vol / maxVolume) * 100);

          return (
            <div
              key={inst.symbol}
              className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1.5 text-xs"
            >
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-slate-200">{inst.symbol}</span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {inst.trade_count} trades ({inst.win_rate} win)
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-slate-400 font-mono">{inst.volume_lots} lots</span>
                  <span
                    className={cn(
                      "font-mono font-bold",
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    )}
                  >
                    {formatCurrency(inst.net_pnl, currency)}
                  </span>
                </div>
              </div>

              {/* Volume relative bar */}
              <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full",
                    isProfit ? "bg-cyan-500" : "bg-rose-500"
                  )}
                  style={{ width: `${barWidthPct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
