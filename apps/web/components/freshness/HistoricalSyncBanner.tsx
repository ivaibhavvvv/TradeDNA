"use client";

import React from "react";
import { Activity, RefreshCw } from "lucide-react";
import { SyncTelemetry } from "@/lib/types";

interface HistoricalSyncBannerProps {
  telemetry: SyncTelemetry | null;
}

export function HistoricalSyncBanner({ telemetry }: HistoricalSyncBannerProps) {
  if (!telemetry || !telemetry.has_account) return null;
  if (telemetry.freshness_state !== "SYNCING" && telemetry.freshness_state !== "RECOVERING") {
    return null;
  }

  const progress = telemetry.historical_sync_progress;
  const isRecovering = telemetry.freshness_state === "RECOVERING";

  return (
    <div className="rounded-lg border border-cyan-800/60 bg-gradient-to-r from-cyan-950/40 via-[#0d1726] to-cyan-950/30 p-3.5 shadow-lg text-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 text-cyan-300 font-semibold">
          <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
          <span>
            {isRecovering
              ? "Ingress Recovery in Progress (Draining Spool)..."
              : "Historical Synchronization in Progress..."}
          </span>
        </div>
        <div className="flex items-center gap-3 text-slate-300 font-mono text-[11px]">
          <span>Cursor Deal: #{telemetry.current_cursor_deal_ticket}</span>
          <span>•</span>
          <span className="text-cyan-400 font-bold">{progress}% Complete</span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
        <div
          className="bg-gradient-to-r from-cyan-500 to-emerald-400 h-2 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="flex justify-between items-center text-[10px] text-slate-400 mt-1.5">
        <span>Processing Exness MT5 ledger stream without blocking live analytics</span>
        <span>Double-Entry Reconciling</span>
      </div>
    </div>
  );
}
