"use client";

/**
 * TradeDNA Phase 8C - Overview Command Center Page.
 * Renders all 13 interactive intelligence sections with real-time charts and data provenance.
 */

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Brain,
  CheckCircle2,
  Clock,
  Coins,
  Dna,
  Layers,
  RotateCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { useDashboardOverview } from "@/hooks/use-dashboard-overview";
import { useSyncTrigger } from "@/hooks/use-sync-trigger";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { MetricCard } from "@/components/ui/metric-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { EquityCurveChart } from "@/components/charts/equity-curve-chart";
import { SpiderRadarChart } from "@/components/charts/spider-radar-chart";
import { HistoricalSyncBanner } from "@/components/freshness/HistoricalSyncBanner";
import { StaleDataBanner } from "@/components/freshness/StaleDataBanner";
import { DataProvenance } from "@/components/freshness/DataProvenance";
import { formatCurrency, formatPercent } from "@/lib/utils";

export default function OverviewPage() {
  const router = useRouter();
  const { data: overview, isLoading, isError, error, refetch } = useDashboardOverview();
  const { mutate: triggerSync, isPending: isSyncing } = useSyncTrigger();
  const { selectedAccount, telemetry } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const [period, setPeriod] = useState("ALL");

  // Fetch performance analytics for equity curve
  const { data: perfData } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_PERFORMANCE(actNum, period),
    queryFn: () => dashboardApi.getPerformance(actNum, period),
    enabled: !!overview?.has_account,
  });

  // Fetch symbol analytics for top instruments
  const { data: instrumentsData } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_INSTRUMENTS(actNum),
    queryFn: () => dashboardApi.getInstruments(actNum),
    enabled: !!overview?.has_account,
  });

  // Fetch sessions analytics
  const { data: sessionsData } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_SESSIONS(actNum),
    queryFn: () => dashboardApi.getSessions(actNum),
    enabled: !!overview?.has_account,
  });

  // 1. Loading State
  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="flex justify-between items-center">
          <div className="space-y-2">
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-4 w-96" />
          </div>
          <Skeleton className="h-9 w-32" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
        <Skeleton className="h-72 rounded-xl" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      </div>
    );
  }

  // 2. Error State
  if (isError) {
    return (
      <ErrorState
        title="Failed to Load Dashboard Overview"
        message={error?.message || "An unexpected error occurred while fetching your Exness intelligence data."}
        onRetry={() => refetch()}
      />
    );
  }

  // 3. Empty State (No Exness account linked)
  if (!overview || !overview.has_account) {
    return (
      <EmptyState
        icon={<Layers className="h-8 w-8 text-cyan-400" />}
        title="No Exness MT5 Account Connected"
        description="Pair your live Exness MT5 terminal with the TradeDNA read-only connector to unlock automated financial reconciliation, behavioral pattern detection, and trading DNA synthesis."
        actionLabel="Connect Exness Account"
        onAction={() => router.push("/dashboard/connections")}
      />
    );
  }

  const {
    account_summary,
    connected_devices,
    performance_summary,
    risk_summary,
    daily_trading_brief,
    trading_dna,
    behavioral_intelligence,
    data_integrity,
    sync_health,
    provenance,
  } = overview;

  const isDegraded = data_integrity?.is_compromised;
  const currency = account_summary?.currency || "USD";

  return (
    <div className="space-y-6">
      {/* 1. Header & Diagnostics */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            OVERVIEW COMMAND CENTER
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Personalized Exness Trading Intelligence • Server: {account_summary?.server_name}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerSync()}
            disabled={isSyncing}
            className="gap-2 text-xs border-slate-700"
          >
            <RotateCw className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin text-cyan-400" : ""}`} />
            {isSyncing ? "Requesting Sync..." : "Refresh Sync"}
          </Button>
        </div>
      </div>

      {/* 2. Real-Time Sync & Freshness Banners */}
      <HistoricalSyncBanner telemetry={telemetry} />
      <StaleDataBanner telemetry={telemetry} />

      {/* 3. Account Verified & Zero-Drift Confirmation (when Ready) */}
      {telemetry?.sync_stage === "READY" && !isDegraded && telemetry?.is_connected && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-3.5 py-2 text-xs text-emerald-300 shadow-sm">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span className="font-semibold text-emerald-200">Account Verified & Ledger Reconciled:</span>
            <span className="text-slate-300 text-[11px]">
              Continuous Exness MT5 observation active with mathematical zero financial drift ($0.00000000).
            </span>
          </div>
          <Badge variant="connected" className="text-[10px] font-mono border-emerald-700/60 text-emerald-300">
            AAA Verified
          </Badge>
        </div>
      )}

      {/* 4. Data Integrity Warning Banner (if degraded) */}
      {isDegraded && (
        <Alert variant="warning" title="Data Integrity Gate: Degradation Observed">
          Reconciliation score is currently at{" "}
          <span className="font-mono font-bold text-amber-300">{data_integrity?.score}%</span> (Grade {data_integrity?.grade}).
          Discrepancies have been flagged between MT5 observations and canonical ledger entries. Financial figures may reflect unverified observations.
        </Alert>
      )}

      {/* 3. Account Summary & Key Financial KPIs (4-Column Grid) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Account Equity"
          value={formatCurrency(account_summary?.equity || "0", currency)}
          subValue={`Balance: ${formatCurrency(account_summary?.balance || "0", currency)}`}
          tooltip="Total account equity inclusive of floating profits and losses"
          badge={account_summary?.trade_mode || "REAL"}
          badgeVariant="primary"
        />

        <MetricCard
          title="Net Realized P&L"
          value={formatCurrency(performance_summary?.net_pnl || "0", currency)}
          subValue={`Today: ${formatCurrency(daily_trading_brief?.today_net_pnl || "0", currency)}`}
          trend={Number(performance_summary?.net_pnl || 0) >= 0 ? "up" : "down"}
          trendLabel={Number(performance_summary?.net_pnl || 0) >= 0 ? "+Profit" : "-Loss"}
          tooltip="Canonical realized P&L after commission and swap deductions"
          badge="CANONICAL"
          badgeVariant={Number(performance_summary?.net_pnl || 0) >= 0 ? "positive" : "negative"}
        />

        <MetricCard
          title="Win Rate & Edge"
          value={formatPercent(performance_summary?.win_rate || "0", 1)}
          subValue={`Profit Factor: ${performance_summary?.profit_factor || "0.00"}`}
          tooltip="Win rate across verified closed trades and overall profit factor"
          badge={`${performance_summary?.total_trades || 0} Trades`}
          badgeVariant="neutral"
        />

        <MetricCard
          title="Margin & Exposure"
          value={risk_summary?.margin_utilization_pct || "0.00%"}
          subValue={`Free Margin: ${formatCurrency(account_summary?.margin_free || "0", currency)}`}
          tooltip="Current margin utilization percentage relative to total balance"
          badge={risk_summary?.risk_appetite_grade || "MODERATE"}
          badgeVariant="warning"
        />
      </div>

      {/* 4. Interactive Equity Progression Chart */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-cyan-400" />
            Equity Trajectory & Drawdown Context
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Authoritative balance progression and high-water mark line
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EquityCurveChart
            data={perfData?.equity_curve || []}
            currency={currency}
            selectedPeriod={period}
            onPeriodChange={setPeriod}
            height={260}
          />
        </CardContent>
      </Card>

      {/* 5. Daily Trading Brief & Trading DNA (2-Column Grid) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily Brief Card */}
        <Card className="lg:col-span-2 border-slate-800 bg-[#0d1321]">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div className="space-y-0.5">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Brain className="h-4 w-4 text-cyan-400" />
                Daily Trading Brief
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Deterministic synthesis of today&apos;s activity (UTC {daily_trading_brief?.date_utc})
              </CardDescription>
            </div>
            <Badge variant="primary">Today</Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg bg-slate-900/90 p-3.5 border border-slate-800 text-xs text-slate-200 leading-relaxed font-sans">
              {daily_trading_brief?.brief_summary || "No trading activity recorded for today."}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800/80">
                <span className="text-[10px] font-semibold uppercase text-slate-500">Today P&L</span>
                <div className={`text-sm font-bold font-mono mt-1 ${Number(daily_trading_brief?.today_net_pnl || 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatCurrency(daily_trading_brief?.today_net_pnl || "0", currency)}
                </div>
              </div>
              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800/80">
                <span className="text-[10px] font-semibold uppercase text-slate-500">Trades Closed</span>
                <div className="text-sm font-bold font-mono text-slate-200 mt-1">
                  {daily_trading_brief?.today_trade_count || 0}
                </div>
              </div>
              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800/80">
                <span className="text-[10px] font-semibold uppercase text-slate-500">Top Instrument</span>
                <div className="text-sm font-bold font-mono text-cyan-300 mt-1 truncate">
                  {daily_trading_brief?.strongest_instrument || "None"}
                </div>
              </div>
              <div className="rounded-lg bg-slate-900/60 p-3 border border-slate-800/80">
                <span className="text-[10px] font-semibold uppercase text-slate-500">Top Session</span>
                <div className="text-sm font-bold font-mono text-cyan-300 mt-1 truncate">
                  {daily_trading_brief?.strongest_session || "None"}
                </div>
              </div>
            </div>

            {daily_trading_brief?.lot_size_comparison_note && (
              <div className="flex items-center gap-2 text-xs text-slate-400 border-t border-slate-800/60 pt-3">
                <Activity className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                <span>{daily_trading_brief.lot_size_comparison_note}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Trading DNA 5-Axis Radar Card */}
        <Card className="border-slate-800 bg-[#0d1321] flex flex-col justify-between">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Dna className="h-4 w-4 text-purple-400" />
                Trading DNA
              </CardTitle>
              <Badge variant="default" className="text-purple-300 border-purple-800/50 bg-purple-950/40">
                {trading_dna?.primary_style || "ANALYZING"}
              </Badge>
            </div>
            <CardDescription className="text-xs text-slate-400">
              5-Axis quantitative behavioral fingerprint
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center">
            {trading_dna ? (
              <SpiderRadarChart dimensions={trading_dna.radar_dimensions} size={250} />
            ) : (
              <div className="text-xs text-slate-500 text-center py-8">
                Trading DNA profile will synthesize after 10 closed trades.
              </div>
            )}
            <Link
              href="/dashboard/trading-dna"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 pt-3"
            >
              Explore Full Profile <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* 6. Top Instruments & Session Performance (2-Column Grid) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Instruments Card */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Coins className="h-4 w-4 text-cyan-400" />
                Top Traded Instruments
              </CardTitle>
              <Badge variant="neutral">
                {instrumentsData?.instruments?.length || 0} Symbols
              </Badge>
            </div>
            <CardDescription className="text-xs text-slate-400">
              Ranked by net realized profit and total traded volume
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {instrumentsData?.instruments && instrumentsData.instruments.length > 0 ? (
              instrumentsData.instruments.slice(0, 4).map((inst) => {
                const isProfit = parseFloat(inst.net_pnl) >= 0;
                return (
                  <div
                    key={inst.symbol}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-xs font-mono"
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-200">{inst.symbol}</span>
                        <span className="text-[10px] text-slate-400">({inst.trade_count} trades)</span>
                      </div>
                      <div className="text-[10px] text-slate-500">
                        Win: {inst.win_rate} • PF: {inst.profit_factor}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-bold ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                        {formatCurrency(inst.net_pnl, currency)}
                      </div>
                      <div className="text-[10px] text-slate-500">{inst.volume_lots} lots</div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">
                No symbol records found.
              </div>
            )}
            <Link
              href="/dashboard/instruments"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 pt-2"
            >
              View All Instruments <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>

        {/* Session Breakdown Card */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Clock className="h-4 w-4 text-cyan-400" />
                Session Edge & Timing
              </CardTitle>
              <Badge variant="neutral">4 Market Sessions</Badge>
            </div>
            <CardDescription className="text-xs text-slate-400">
              Asian, London, London/NY Overlap, and New York performance
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {sessionsData?.sessions && sessionsData.sessions.length > 0 ? (
              sessionsData.sessions.map((sess) => {
                const isProfit = parseFloat(sess.net_pnl) >= 0;
                return (
                  <div
                    key={sess.session_name}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-xs font-mono"
                  >
                    <div>
                      <span className="font-bold text-slate-200">
                        {sess.session_name.replace(/_/g, " ")}
                      </span>
                      <div className="text-[10px] text-slate-400">
                        {sess.trade_count} trades • {sess.win_rate} win rate
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-bold ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                        {formatCurrency(sess.net_pnl, currency)}
                      </div>
                      <div className="text-[10px] text-slate-500">PF: {sess.profit_factor}</div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">
                No session records found.
              </div>
            )}
            <Link
              href="/dashboard/sessions"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 pt-2"
            >
              View 24h Heatmap <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* 7. Behavioral Intelligence Alerts & Physical Connector Devices (2-Column Grid) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Behavioral Pattern Feed */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Activity className="h-4 w-4 text-amber-400" />
                Behavioral Pattern Feed
              </CardTitle>
              <Badge variant="warning">
                {behavioral_intelligence?.detected_patterns_count || 0} Alerts
              </Badge>
            </div>
            <CardDescription className="text-xs text-slate-400">
              Empirical anomaly detection across 10 behavioral models
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {behavioral_intelligence?.top_patterns?.length > 0 ? (
              behavioral_intelligence.top_patterns.map((p, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-xs"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-200 font-mono">
                        {p.pattern_type.replace(/_/g, " ")}
                      </span>
                      <Badge
                        variant={
                          p.severity === "CRITICAL" || p.severity === "HIGH"
                            ? "critical"
                            : "warning"
                        }
                      >
                        {p.severity}
                      </Badge>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      Status: {p.detection_status} • Evidence: {p.evidence_strength}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {new Date(p.detected_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center p-6 text-center text-xs text-slate-500">
                <CheckCircle2 className="h-6 w-6 text-emerald-500 mb-2" />
                <span>Zero behavioral anomalies detected in current cohort.</span>
              </div>
            )}

            <Link
              href="/dashboard/behavior"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 pt-1"
            >
              View Full Behavioral Feed <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>

        {/* Physical Connector Devices & Ingress Health */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Server className="h-4 w-4 text-blue-400" />
                Connected Physical Devices
              </CardTitle>
              <Badge variant="connected">
                {connected_devices?.length || 0} Device(s)
              </Badge>
            </div>
            <CardDescription className="text-xs text-slate-400">
              Physical MT5 terminal EAs feeding Layer 1 ingress
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {connected_devices?.length > 0 ? (
              connected_devices.map((d) => (
                <div
                  key={d.device_id}
                  className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-xs"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-slate-200 font-medium">
                        Terminal Build {d.terminal_build}
                      </span>
                      <span className="text-[10px] text-cyan-400 font-mono">
                        v{d.connector_version}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono">
                      ID: {d.device_id.slice(0, 8)}...
                    </span>
                  </div>
                  <div className="text-right space-y-0.5">
                    <Badge variant={d.is_active ? "connected" : "disconnected"}>
                      {d.is_active ? "Active EA" : "Inactive"}
                    </Badge>
                    <div className="text-[10px] text-slate-500">
                      {d.last_seen_at ? `Seen ${new Date(d.last_seen_at).toLocaleTimeString()}` : "Never"}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">
                No physical devices connected. Download TradeDNA MT5 Connector EA.
              </div>
            )}

            {/* Provenance Metadata footer */}
            <div className="border-t border-slate-800/60 pt-2.5 text-[11px] text-slate-500 flex justify-between font-mono">
              <span>Reconstruction Run:</span>
              <span className="text-slate-400 truncate max-w-[180px]">
                {provenance?.reconstruction_run_id ? provenance.reconstruction_run_id.slice(0, 12) : "None"}...
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Global Data Provenance Component */}
      <DataProvenance telemetry={telemetry} moduleName="Command Center" />
    </div>
  );
}
