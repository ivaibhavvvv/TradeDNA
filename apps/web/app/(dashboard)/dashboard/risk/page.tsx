"use client";

/**
 * TradeDNA Phase 8C - Risk & Capital Exposure Page.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Gauge,
  Layers,
  PieChart,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
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
import { DrawdownAreaChart } from "@/components/charts/drawdown-area-chart";
import { formatCurrency } from "@/lib/utils";

export default function RiskPage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_RISK(actNum),
    queryFn: () => dashboardApi.getRisk(actNum),
    enabled: !!actNum,
  });

  const { data: perfData } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_PERFORMANCE(actNum, "ALL"),
    queryFn: () => dashboardApi.getPerformance(actNum, "ALL"),
    enabled: !!actNum,
  });

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to Load Risk Metrics"
        message={error?.message || "Could not retrieve authoritative risk profile."}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || !data.has_data) {
    return (
      <EmptyState
        icon={<ShieldAlert className="h-8 w-8 text-amber-400" />}
        title="No Risk Analytics Available"
        description="Connect an active Exness account to inspect real-time margin exposure and concentration."
      />
    );
  }

  const currency = data.currency || "USD";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            RISK & CAPITAL EXPOSURE
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Margin utilization, drawdown velocity, and Herfindahl-Hirschman symbol concentration.
          </p>
        </div>
        <Badge variant="warning">{data.risk_appetite_grade} RISK APPETITE</Badge>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Max Historical Drawdown"
          value={data.max_drawdown_pct}
          subValue={`Amount: -${formatCurrency(data.max_drawdown_amount, currency)}`}
          tooltip="Maximum peak-to-trough decline across all canonical closed trades"
          badge="MAX DD"
          badgeVariant="negative"
        />

        <MetricCard
          title="Symbol Concentration (HHI)"
          value={data.hhi_concentration}
          subValue={`Top Symbol Volume: ${data.top_symbol_volume_pct}`}
          tooltip="Herfindahl-Hirschman Index: <1500 Diversified, 1500-2500 Moderate, >2500 Concentrated"
          badge="DIVERSIFICATION"
          badgeVariant={parseFloat(data.hhi_concentration) > 2500 ? "warning" : "positive"}
        />

        <MetricCard
          title="Position Sizing Consistency"
          value={data.position_size_consistency}
          subValue="Calculated against 30D baseline"
          tooltip="Standard deviation of lot sizing relative to historical mean"
          badge="DISCIPLINE"
          badgeVariant="primary"
        />

        <MetricCard
          title="Capital Protection Grade"
          value={data.risk_appetite_grade}
          subValue="Synthesized from Phase 7 risk engine"
          tooltip="Empirical risk appetite rating derived from leverage, drawdown, and holding duration"
          badge="SYNTHESIZED"
          badgeVariant="neutral"
        />
      </div>

      {/* Underwater Drawdown Analysis */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-rose-400" />
            Drawdown Velocity & Historical Recovery Trajectory
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Realized peak-to-trough equity curves distinguishing current and maximum drawdown
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DrawdownAreaChart
            data={perfData?.equity_curve || []}
            maxDrawdownPct={data.max_drawdown_pct}
            height={220}
          />
        </CardContent>
      </Card>

      {/* Symbol Exposure & Volume Breakdown */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <PieChart className="h-4 w-4 text-cyan-400" />
            Symbol Capital Allocation & Exposure Ranking
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Distribution of traded lots and realized net returns by symbol
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.symbol_exposure && data.symbol_exposure.length > 0 ? (
            data.symbol_exposure.map((sym) => {
              const pnl = parseFloat(sym.net_pnl);
              return (
                <div
                  key={sym.symbol}
                  className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs font-mono"
                >
                  <div className="space-y-0.5">
                    <span className="font-bold text-slate-200">{sym.symbol}</span>
                    <div className="text-[10px] text-slate-400 font-sans">
                      {sym.trade_count} trades executed
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-slate-300 font-bold">{sym.volume_lots} lots</div>
                    <div className={`text-[10px] ${pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {formatCurrency(sym.net_pnl, currency)}
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="text-xs text-slate-500 text-center py-6">
              No symbol exposure records found.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
