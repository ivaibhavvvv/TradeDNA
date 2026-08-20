"use client";

/**
 * TradeDNA Phase 8C - Trading DNA & Style Fingerprint Signature Page.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  Dna,
  HelpCircle,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  Target,
  Zap,
} from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SpiderRadarChart } from "@/components/charts/spider-radar-chart";

export default function TradingDNAPage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_TRADING_DNA(actNum),
    queryFn: () => dashboardApi.getTradingDNA(actNum),
    enabled: !!actNum,
  });

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-96 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to Load Trading DNA Profile"
        message={error?.message || "Could not synthesize trading DNA."}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || !data.has_dna || !data.dna) {
    return (
      <EmptyState
        icon={<Dna className="h-8 w-8 text-purple-400" />}
        title="Trading DNA Fingerprint Generating"
        description="Trading DNA requires a minimum cohort of 10 closed canonical trades to perform statistical validation and dimensional scoring."
      />
    );
  }

  const { dna } = data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            TRADING DNA & STYLE PROFILING
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Quantitative behavioral fingerprinting across 5 dimensions with empirical confidence scoring.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="primary" className="text-purple-300 border-purple-800 bg-purple-950/40 text-xs px-3 py-1 font-mono">
            {dna.primary_style}
          </Badge>
          <Badge variant="warning" className="text-xs px-3 py-1 font-mono">
            {dna.risk_appetite}
          </Badge>
        </div>
      </div>

      {/* Main Grid: 5-Axis Spider Radar + Dimensional Scores */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Radar Chart Card */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-purple-400" />
              5-Axis Dimensional Spider Radar
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Normalized scores (0-100) benchmarked against mathematical risk parameters
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center justify-center p-6">
            <SpiderRadarChart dimensions={dna.radar_dimensions} size={300} />
          </CardContent>
        </Card>

        {/* Profile Synthesis Details */}
        <div className="space-y-6">
          {/* Dimensional Score Breakdown Bars */}
          <Card className="border-slate-800 bg-[#0d1321]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Target className="h-4 w-4 text-cyan-400" />
                Dimensional Score Synthesis
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Authoritative composite scores synthesized by Phase 7 engine
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-300">Consistency Score</span>
                  <span className="font-mono font-bold text-cyan-400">{dna.consistency_score}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div className="h-full bg-cyan-500 rounded-full" style={{ width: `${dna.consistency_score}%` }} />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-300">Discipline Score</span>
                  <span className="font-mono font-bold text-emerald-400">{dna.discipline_score}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${dna.discipline_score}%` }} />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-300">Execution Quality Score</span>
                  <span className="font-mono font-bold text-purple-400">{dna.execution_quality_score}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div className="h-full bg-purple-500 rounded-full" style={{ width: `${dna.execution_quality_score}%` }} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Top Strengths & Weaknesses Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Strengths */}
            <Card className="border-slate-800 bg-[#0d1321]">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" />
                  Key Strengths
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {dna.top_strengths && dna.top_strengths.length > 0 ? (
                  dna.top_strengths.map((str, i) => (
                    <div key={i} className="flex items-start gap-2 text-slate-300">
                      <span className="text-emerald-400 font-bold">✓</span>
                      <span>{str}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-slate-500">None flagged in baseline.</div>
                )}
              </CardContent>
            </Card>

            {/* Weaknesses */}
            <Card className="border-slate-800 bg-[#0d1321]">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-semibold uppercase tracking-wider text-rose-400 flex items-center gap-1.5">
                  <ShieldAlert className="h-4 w-4" />
                  Growth Opportunities
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {dna.top_weaknesses && dna.top_weaknesses.length > 0 ? (
                  dna.top_weaknesses.map((w, i) => (
                    <div key={i} className="flex items-start gap-2 text-slate-300">
                      <span className="text-rose-400 font-bold">!</span>
                      <span>{w}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-slate-500">None flagged in baseline.</div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
