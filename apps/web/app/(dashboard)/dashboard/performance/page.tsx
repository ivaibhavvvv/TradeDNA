"use client";

/**
 * TradeDNA Phase 8C - Financial Performance & Equity Analytics Page.
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Coins,
  ReceiptText,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/ui/metric-card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { EquityCurveChart } from "@/components/charts/equity-curve-chart";
import { PnlBarChart } from "@/components/charts/pnl-bar-chart";
import { DrawdownAreaChart } from "@/components/charts/drawdown-area-chart";
import { WinLossDistributionChart } from "@/components/charts/win-loss-distribution-chart";
import { formatCurrency, formatPercent } from "@/lib/utils";

export default function PerformancePage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;
  const [period, setPeriod] = useState("ALL");

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_PERFORMANCE(actNum, period),
    queryFn: () => dashboardApi.getPerformance(actNum, period),
    enabled: !!actNum,
  });

  const periods = ["7D", "30D", "90D", "6M", "1Y", "ALL"];

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="flex justify-between items-center">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-9 w-60" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to Load Performance Analytics"
        message={error?.message || "Could not retrieve authoritative performance series."}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || !data.has_data || !data.summary) {
    return (
      <EmptyState
        icon={<TrendingUp className="h-8 w-8 text-cyan-400" />}
        title="No Performance History Found"
        description="No canonical closed trades have been recorded for the selected account yet."
      />
    );
  }

  const { summary, equity_curve, daily_pnl, win_loss_distribution } = data;
  const currency = summary.currency || "USD";
  const isNetProfit = parseFloat(summary.net_pnl) >= 0;

  return (
    <div className="space-y-6">
      {/* Header with Time Period Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            FINANCIAL PERFORMANCE & EQUITY CURVES
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Authoritative return metrics, drawdown trajectory, and payoff distribution.
          </p>
        </div>

        {/* Time Period Filter */}
        <div className="flex items-center rounded-lg bg-slate-900 p-1 border border-slate-800 self-start sm:self-auto">
          {periods.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`rounded px-3 py-1 text-xs font-mono font-medium transition-all ${
                period === p
                  ? "bg-slate-800 text-cyan-400 font-bold shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Net Realized P&L"
          value={formatCurrency(summary.net_pnl, currency)}
          subValue={`Gross Profit: +${formatCurrency(summary.gross_profit || "0", currency)}`}
          trend={isNetProfit ? "up" : "down"}
          trendLabel={isNetProfit ? "+Gain" : "-Loss"}
          badge={period}
          badgeVariant={isNetProfit ? "positive" : "negative"}
        />

        <MetricCard
          title="Win Rate"
          value={formatPercent(summary.win_rate, 1)}
          subValue={`${summary.winning_trades} Wins / ${summary.losing_trades} Losses`}
          badge={`Total: ${summary.total_trades}`}
          badgeVariant="neutral"
        />

        <MetricCard
          title="Profit Factor"
          value={summary.profit_factor}
          subValue={`Expectancy: ${formatCurrency(summary.expectancy, currency)}`}
          badge="EDGE"
          badgeVariant={parseFloat(summary.profit_factor) >= 1.5 ? "positive" : "warning"}
        />

        <MetricCard
          title="Max Drawdown"
          value={summary.max_drawdown_pct}
          subValue={`Amount: -${formatCurrency(summary.max_drawdown_amount, currency)}`}
          badge="RISK"
          badgeVariant="negative"
        />
      </div>

      {/* Interactive Equity Progression Area Chart */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-cyan-400" />
            Equity Progression & High-Water Mark ({period})
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Realized equity line with peak high-water mark tracking
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EquityCurveChart
            data={equity_curve}
            currency={currency}
            selectedPeriod={period}
            onPeriodChange={setPeriod}
            height={280}
          />
        </CardContent>
      </Card>

      {/* Daily Realized P&L Bars */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-cyan-400" />
            Daily Realized P&L Distribution
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Closed daily gains and losses in selected period
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PnlBarChart data={daily_pnl} currency={currency} height={220} />
        </CardContent>
      </Card>

      {/* 2-Column: Underwater Drawdown + Win/Loss Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-rose-400" />
              Underwater Drawdown Analysis
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Depth of drawdown relative to peak equity
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DrawdownAreaChart
              data={equity_curve}
              maxDrawdownPct={summary.max_drawdown_pct}
              height={200}
            />
          </CardContent>
        </Card>

        <WinLossDistributionChart
          distribution={win_loss_distribution}
          payoffRatio={summary.payoff_ratio}
          currency={currency}
        />
      </div>
    </div>
  );
}
