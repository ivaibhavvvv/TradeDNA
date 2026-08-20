"use client";

/**
 * TradeDNA Phase 8C - Instrument Slicing & Symbol Performance Page.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Coins, Filter, Search, TrendingUp } from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SymbolDistributionChart } from "@/components/charts/symbol-distribution-chart";
import { formatCurrency, formatPercent } from "@/lib/utils";

export default function InstrumentsPage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_INSTRUMENTS(actNum),
    queryFn: () => dashboardApi.getInstruments(actNum),
    enabled: !!actNum,
  });

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to Load Instrument Analytics"
        message={error?.message || "Could not retrieve symbol performance breakdowns."}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || data.instruments.length === 0) {
    return (
      <EmptyState
        icon={<Coins className="h-8 w-8 text-cyan-400" />}
        title="No Instrument Records"
        description="No symbols traded yet in the active account."
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
            INSTRUMENT INTELLIGENCE & SYMBOL SLICES
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Performance, win rates, and volume concentration sliced by Exness symbols.
          </p>
        </div>
        <Badge variant="neutral">{data.instruments.length} Traded Symbols</Badge>
      </div>

      {/* Symbol Volume & P&L Distribution Visualization */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <Coins className="h-4 w-4 text-cyan-400" />
            Symbol Capital Allocation & Returns
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Realized returns and traded lots across symbol universe
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SymbolDistributionChart instruments={data.instruments} currency={currency} />
        </CardContent>
      </Card>

      {/* Detailed Symbol Rankings Table */}
      <Card className="border-slate-800 bg-[#0d1321] overflow-hidden">
        <CardHeader className="pb-3 border-b border-slate-800">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200">
            Symbol Performance Matrix
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Comparative performance and trade metrics per instrument
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-slate-800 bg-slate-900/60">
                <TableHead>Symbol</TableHead>
                <TableHead>Trades Count</TableHead>
                <TableHead>Win Rate</TableHead>
                <TableHead>Volume Lots</TableHead>
                <TableHead>Profit Factor</TableHead>
                <TableHead>Expectancy</TableHead>
                <TableHead>Avg Hold Duration</TableHead>
                <TableHead className="text-right">Net Realized P&L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.instruments.map((inst) => {
                const pnl = parseFloat(inst.net_pnl);
                const isProfit = pnl >= 0;
                const avgMin = inst.avg_holding_sec ? Math.floor(inst.avg_holding_sec / 60) : 0;

                return (
                  <TableRow key={inst.symbol} className="font-mono text-xs">
                    <TableCell className="font-bold text-slate-100">{inst.symbol}</TableCell>
                    <TableCell className="text-slate-300">{inst.trade_count} trades</TableCell>
                    <TableCell>
                      <Badge variant={parseFloat(inst.win_rate) >= 0.5 ? "positive" : "negative"}>
                        {inst.win_rate}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-slate-300">{inst.volume_lots} lots</TableCell>
                    <TableCell className="text-slate-300">{inst.profit_factor}</TableCell>
                    <TableCell className="text-slate-300">{formatCurrency(inst.expectancy, currency)}</TableCell>
                    <TableCell className="text-slate-400">{avgMin > 0 ? `${avgMin}m` : "<1m"}</TableCell>
                    <TableCell className="text-right">
                      <span className={`font-bold ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                        {formatCurrency(inst.net_pnl, currency)}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
