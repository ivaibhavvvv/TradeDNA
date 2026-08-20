"use client";

import React from "react";
import { AlertCircle, AlertTriangle, Clock, WifiOff } from "lucide-react";
import { SyncTelemetry } from "@/lib/types";

interface StaleDataBannerProps {
  telemetry: SyncTelemetry | null;
}

export function StaleDataBanner({ telemetry }: StaleDataBannerProps) {
  if (!telemetry || !telemetry.has_account) return null;

  const state = telemetry.freshness_state;
  if (state !== "STALE" && state !== "DEGRADED" && state !== "OFFLINE" && state !== "REVOKED") {
    return null;
  }

  const isStale = state === "STALE";
  const isOffline = state === "OFFLINE";
  const isRevoked = state === "REVOKED";

  return (
    <div
      className={`rounded-lg border p-3 text-xs shadow-md ${
        isRevoked
          ? "border-rose-800/70 bg-rose-950/40 text-rose-200"
          : isStale
          ? "border-rose-900/60 bg-rose-950/30 text-rose-200"
          : isOffline
          ? "border-slate-800 bg-slate-900/70 text-slate-300"
          : "border-amber-800/60 bg-amber-950/30 text-amber-200"
      }`}
    >
      <div className="flex items-start gap-2.5">
        {isRevoked || isStale ? (
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
        ) : isOffline ? (
          <WifiOff className="h-4 w-4 shrink-0 text-slate-400 mt-0.5" />
        ) : (
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
        )}

        <div className="space-y-1 flex-1">
          <div className="flex items-center justify-between flex-wrap gap-1">
            <span className="font-semibold">
              {isRevoked
                ? "CONNECTOR REVOKED — INGRESS HALTED"
                : isStale
                ? "DATA STALE — RECENT SYNCHRONIZATION UNAVAILABLE"
                : isOffline
                ? "CONNECTOR OFFLINE"
                : "SYNCHRONIZATION DELAYED"}
            </span>

            <span className="font-mono text-[11px] opacity-90 flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Last Verified:{" "}
              {telemetry.last_successful_sync_at
                ? new Date(telemetry.last_successful_sync_at).toLocaleTimeString()
                : "Never"}
            </span>
          </div>

          <p className="text-[11px] opacity-80">
            {isRevoked
              ? "This MT5 terminal device has been revoked. Generate a new pairing key in the Connection Center to resume ingress."
              : isStale
              ? "TradeDNA has not received MT5 connector heartbeats for more than 10 minutes. Existing verified historical records remain visible."
              : isOffline
              ? "Waiting for MT5 terminal heartbeat. Ensure MetaTrader 5 is running with TradeDNAConnector attached to a chart."
              : "Ingress is experiencing a minor sync delay. Financial records remain 100% reconciled to the last verified snapshot."}
          </p>
        </div>
      </div>
    </div>
  );
}
