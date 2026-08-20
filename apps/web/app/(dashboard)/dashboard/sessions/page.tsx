"use client";

/**
 * TradeDNA Phase 8C - Trading Sessions & Temporal Heatmaps Page.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock, Globe, TrendingUp } from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SessionHeatmapChart } from "@/components/charts/session-heatmap-chart";

export default function SessionsPage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_SESSIONS(actNum),
    queryFn: () => dashboardApi.getSessions(actNum),
    enabled: !!actNum,
  });

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to Load Session Analytics"
        message={error?.message || "Could not retrieve market session distributions."}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || data.sessions.length === 0) {
    return (
      <EmptyState
        icon={<Clock className="h-8 w-8 text-cyan-400" />}
        title="No Session Analytics Available"
        description="Trade executions will be mapped to Asian, London, and New York market sessions once trades are closed."
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
            TRADING SESSIONS & TEMPORAL HEATMAPS
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Performance sliced across Asian, London, New York, and Overlap market sessions.
          </p>
        </div>
        <Badge variant="neutral">4 Market Sessions Mapped</Badge>
      </div>

      {/* 24-Hour & Session Heatmap Visualization */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <Globe className="h-4 w-4 text-cyan-400" />
            Temporal Edge & Hourly Trade Heatmap
          </CardTitle>
          <CardDescription className="text-xs text-slate-400">
            Realized returns, volume distribution, and win rates by market timing
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SessionHeatmapChart
            sessions={data.sessions}
            hourly={data.hourly_distribution}
            currency={currency}
          />
        </CardContent>
      </Card>
    </div>
  );
}
