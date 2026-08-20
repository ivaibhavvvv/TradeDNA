"use client";

/**
 * TradeDNA Phase 8C - Behavioral Intelligence Feed & Timeline Page.
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Filter,
  History,
  ShieldAlert,
} from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";

export default function BehaviorPage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const [patternType, setPatternType] = useState("all");
  const [severity, setSeverity] = useState("all");

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_BEHAVIOR(actNum, patternType, severity),
    queryFn: () => dashboardApi.getBehavior(actNum, patternType, severity),
    enabled: !!actNum,
  });

  const patternTypes = [
    { value: "all", label: "All 10 Behavioral Models" },
    { value: "REVENGE_TRADING", label: "Possible Revenge Trading" },
    { value: "OVERTRADING_SPIKE", label: "Possible Overtrading Spike" },
    { value: "LOSS_ESCALATION", label: "Loss Escalation / Martingale" },
    { value: "LOSER_HOLDING", label: "Loser Holding" },
    { value: "WINNER_CUTTING", label: "Winner Cutting" },
    { value: "POSITION_SIZE_ESCALATION", label: "Position Size Escalation" },
    { value: "SESSION_DETERIORATION", label: "Session Deterioration" },
    { value: "RAPID_REENTRY", label: "Rapid Re-Entry" },
    { value: "CONCENTRATION_RISK", label: "Concentration Anomaly" },
    { value: "DRAWDOWN_ACCELERATION", label: "Drawdown Acceleration" },
  ];

  const severities = [
    { value: "all", label: "All Severities" },
    { value: "CRITICAL", label: "Critical" },
    { value: "HIGH", label: "High" },
    { value: "MEDIUM", label: "Medium" },
    { value: "LOW", label: "Low" },
    { value: "INFO", label: "Info" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            BEHAVIORAL INTELLIGENCE & PATTERN DETECTIONS
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Empirical anomaly detection across 10 behavioral models with trade citation evidence.
          </p>
        </div>
        <Badge variant="warning">
          {data?.total_detected || 0} Patterns Logged
        </Badge>
      </div>

      {/* Filter Controls Bar */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Select
              value={patternType}
              onChange={(e) => setPatternType(e.target.value)}
              className="text-xs"
            >
              {patternTypes.map((pt) => (
                <option key={pt.value} value={pt.value}>
                  {pt.label}
                </option>
              ))}
            </Select>

            <Select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="text-xs"
            >
              {severities.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Main Content: Pattern Feed + Chronological Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pattern Cards Feed (2-Column on large) */}
        <div className="lg:col-span-2 space-y-4">
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-28 rounded-xl" />
              <Skeleton className="h-28 rounded-xl" />
              <Skeleton className="h-28 rounded-xl" />
            </div>
          ) : isError ? (
            <ErrorState
              title="Failed to Load Behavioral Patterns"
              message={error?.message || "Could not retrieve behavioral detections."}
              onRetry={() => refetch()}
            />
          ) : !data || data.patterns.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-800 bg-[#0d1321] p-10 text-center space-y-2">
              <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto" />
              <div className="text-sm font-semibold text-slate-200">
                Zero Behavioral Anomalies Found
              </div>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                No matching patterns detected in the current cohort for the selected filters.
              </p>
            </div>
          ) : (
            data.patterns.map((p) => (
              <Card key={p.id} className="border-slate-800 bg-[#0d1321] hover:border-slate-700 transition-colors">
                <CardHeader className="pb-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-sm font-bold font-mono text-slate-100">
                        Possible {p.pattern_type.replace(/_/g, " ").toLowerCase()} detected
                      </CardTitle>
                      <Badge
                        variant={
                          p.severity === "CRITICAL" || p.severity === "HIGH"
                            ? "critical"
                            : p.severity === "MEDIUM"
                            ? "warning"
                            : "neutral"
                        }
                      >
                        {p.severity}
                      </Badge>
                    </div>
                    <span className="text-[11px] text-slate-500 font-mono">
                      {new Date(p.detected_at).toLocaleString()}
                    </span>
                  </div>
                  <CardDescription className="text-xs text-slate-400 font-sans">
                    Detection Status: <span className="text-slate-300 font-mono">{p.detection_status}</span> • Confidence: <span className="text-cyan-400 font-mono">{p.evidence_strength}</span>
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-xs">
                  {p.affected_metric && (
                    <div className="text-slate-300">
                      <strong>Affected Metric:</strong> <span className="font-mono text-slate-400">{p.affected_metric}</span>
                    </div>
                  )}

                  {/* Supporting Evidence Payload */}
                  <div className="rounded-lg bg-slate-900/80 p-3 border border-slate-800 text-[11px] font-mono text-slate-300 space-y-1">
                    <div className="text-[10px] text-slate-500 uppercase font-semibold">Supporting Evidence:</div>
                    <div className="break-all whitespace-pre-wrap leading-relaxed text-slate-400">
                      {typeof p.evidence_payload === "object"
                        ? JSON.stringify(p.evidence_payload, null, 2)
                        : String(p.evidence_payload)}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Chronological Behavioral Timeline Sidebar */}
        <div>
          <Card className="border-slate-800 bg-[#0d1321] sticky top-20">
            <CardHeader className="pb-3 border-b border-slate-800">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <History className="h-4 w-4 text-cyan-400" />
                Chronological Timeline
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Recent sequence of detected behavioral shifts
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4">
              {data?.timeline && data.timeline.length > 0 ? (
                <div className="space-y-4 relative before:absolute before:inset-0 before:left-2 before:w-0.5 before:bg-slate-800">
                  {data.timeline.map((item, idx) => (
                    <div key={idx} className="relative flex items-start gap-3 pl-6 text-xs">
                      <div className="absolute left-1 top-1 h-2.5 w-2.5 rounded-full bg-cyan-500 ring-4 ring-[#0d1321]" />
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] text-slate-500">{item.time}</span>
                          <span className="font-semibold text-slate-200 font-mono">{item.event}</span>
                        </div>
                        <p className="text-[11px] text-slate-400">{item.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-slate-500 text-center py-8">
                  No timeline events recorded.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
