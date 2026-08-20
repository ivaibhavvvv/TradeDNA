"use client";

/**
 * TradeDNA Phase 8C - Win / Loss Distribution & Payoff Chart Component.
 */

import React from "react";
import { WinLossDistribution } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface WinLossDistributionChartProps {
  distribution: WinLossDistribution;
  payoffRatio?: string;
  currency?: string;
  className?: string;
}

export function WinLossDistributionChart({
  distribution,
  payoffRatio = "1.00",
  currency = "USD",
  className,
}: WinLossDistributionChartProps) {
  const { win_count, loss_count, avg_win, avg_loss } = distribution;
  const total = win_count + loss_count || 1;
  const winPct = (win_count / total) * 100;
  const lossPct = (loss_count / total) * 100;

  return (
    <div className={cn("rounded-xl border border-slate-800 bg-[#0d1321] p-4.5 space-y-4 text-xs", className)}>
      <div className="flex justify-between items-center">
        <span className="font-semibold text-slate-200 uppercase tracking-wider text-[11px]">
          Win / Loss Payoff Distribution
        </span>
        <span className="font-mono text-cyan-400 font-bold">
          Payoff Ratio: {payoffRatio}
        </span>
      </div>

      {/* Distribution Ratio Bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-[11px] font-mono">
          <span className="text-emerald-400 font-bold">Wins: {win_count} ({winPct.toFixed(1)}%)</span>
          <span className="text-rose-400 font-bold">Losses: {loss_count} ({lossPct.toFixed(1)}%)</span>
        </div>
        <div className="flex h-3 w-full rounded-full overflow-hidden bg-slate-800">
          <div className="bg-emerald-500 transition-all duration-300" style={{ width: `${winPct}%` }} />
          <div className="bg-rose-500 transition-all duration-300" style={{ width: `${lossPct}%` }} />
        </div>
      </div>

      {/* Average Win vs Average Loss comparison cards */}
      <div className="grid grid-cols-2 gap-3 pt-1">
        <div className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 p-3 space-y-1">
          <span className="text-[10px] text-emerald-400/80 uppercase font-semibold">Average Win</span>
          <div className="font-mono font-bold text-base text-emerald-400">
            +{formatCurrency(avg_win, currency)}
          </div>
        </div>

        <div className="rounded-lg border border-rose-900/50 bg-rose-950/20 p-3 space-y-1">
          <span className="text-[10px] text-rose-400/80 uppercase font-semibold">Average Loss</span>
          <div className="font-mono font-bold text-base text-rose-400">
            -{formatCurrency(avg_loss, currency)}
          </div>
        </div>
      </div>
    </div>
  );
}
