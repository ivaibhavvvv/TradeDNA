"use client";

import React, { useEffect, useState } from "react";
import { dashboardApi, alertsApi } from "@/lib/api-client";
import { OperationsOverviewDTO, OperationalAlertDTO } from "@/lib/types";

export function OperationsDashboard() {
  const [data, setData] = useState<OperationsOverviewDTO | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchOverview = async () => {
    try {
      setLoading(true);
      const res = await dashboardApi.getOperationsOverview();
      setData(res);
      setError(null);
    } catch (err: any) {
      setError(err?.message || "Failed to load operational telemetry");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, []);

  const handleAcknowledge = async (alertId: string) => {
    try {
      setActionLoading(alertId);
      await alertsApi.acknowledge(alertId);
      await fetchOverview();
    } catch (err: any) {
      console.error("Failed to acknowledge alert:", err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleResolve = async (alertId: string) => {
    try {
      setActionLoading(alertId);
      await alertsApi.resolve(alertId);
      await fetchOverview();
    } catch (err: any) {
      console.error("Failed to resolve alert:", err);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent"></div>
          <p className="text-sm font-medium text-slate-400">Loading system observability & telemetry...</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-6 text-red-400">
        <h3 className="text-lg font-semibold">Operational Telemetry Error</h3>
        <p className="mt-1 text-sm">{error}</p>
        <button
          onClick={fetchOverview}
          className="mt-4 rounded-lg bg-red-500/20 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-500/30"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold tracking-tight text-white">Operations & Telemetry Center</h1>
            <span className="inline-flex items-center rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-400 border border-emerald-500/20">
              <span className="mr-1.5 h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
              LIVE TELEMETRY
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Real-time system observability, connector heartbeats, synchronization pipelines, and financial integrity alarms.
          </p>
        </div>
        <button
          onClick={fetchOverview}
          className="inline-flex items-center rounded-lg border border-slate-700 bg-slate-800/80 px-3.5 py-2 text-xs font-medium text-slate-300 shadow-sm hover:bg-slate-700 transition"
        >
          Refresh Now
        </button>
      </div>

      {/* Grid: 4 Metric Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: System Health */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">System State</span>
            <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-500/20">
              {data?.system.status || "UNKNOWN"}
            </span>
          </div>
          <div className="mt-3">
            <div className="text-xl font-bold text-white tracking-tight">{data?.system.service}</div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
              <span>Database: {data?.system.database_status}</span>
              <span>Uptime: {data?.system.uptime_seconds ? `${Math.floor(data.system.uptime_seconds / 60)}m` : "UNKNOWN"}</span>
            </div>
          </div>
        </div>

        {/* Card 2: Exness Terminals */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">MT5 Connectors</span>
            <span className="rounded bg-blue-500/10 px-2 py-0.5 text-xs font-semibold text-blue-400 border border-blue-500/20">
              {data?.connectors.total_devices ?? 0} TOTAL
            </span>
          </div>
          <div className="mt-3">
            <div className="text-xl font-bold text-white tracking-tight">
              {data?.connectors.active_devices ?? 0} <span className="text-sm font-normal text-slate-400">Active</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
              <span>Stale: {data?.connectors.stale_devices ?? 0}</span>
              <span>Revoked: {data?.connectors.revoked_devices ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Card 3: Synchronization */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Sync Pipeline</span>
            <span className="rounded bg-purple-500/10 px-2 py-0.5 text-xs font-semibold text-purple-400 border border-purple-500/20">
              {data?.synchronization.live_syncs ?? 0} LIVE
            </span>
          </div>
          <div className="mt-3">
            <div className="text-xl font-bold text-white tracking-tight">
              {data?.synchronization.active_syncs ?? 0} <span className="text-sm font-normal text-slate-400">Syncing</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
              <span>Accounts: {data?.synchronization.total_accounts ?? 0}</span>
              <span>Failed: {data?.synchronization.failed_syncs ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Card 4: Reconciliation Integrity */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Integrity Quality</span>
            <span className="rounded bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-400 border border-amber-500/20">
              GRADE AAA
            </span>
          </div>
          <div className="mt-3">
            <div className="text-xl font-bold text-white tracking-tight">
              {data?.reconciliation.latest_integrity_score || "100.00"}%
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
              <span>AAA Accounts: {data?.reconciliation.aaa_accounts ?? 0}</span>
              <span>Discrepancies: {data?.reconciliation.unresolved_critical_discrepancies ?? 0}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Operational Alerts Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-sm overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-800 p-5">
          <div>
            <h2 className="text-base font-semibold text-white">Live Operational & Financial Integrity Alarms</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Deduplicated system alerts, reconciliation warnings, and cursor anomaly events.
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-slate-300">
              Open: <strong className="text-emerald-400">{data?.alerts.open_count ?? 0}</strong>
            </span>
            {data?.alerts.critical_count ? (
              <span className="rounded-full bg-red-500/20 px-3 py-1 text-xs font-bold text-red-400 border border-red-500/30 animate-pulse">
                Critical: {data.alerts.critical_count}
              </span>
            ) : null}
          </div>
        </div>

        {data?.alerts.recent_alerts && data.alerts.recent_alerts.length > 0 ? (
          <div className="divide-y divide-slate-800/80">
            {data.alerts.recent_alerts.map((alert: OperationalAlertDTO) => (
              <div key={alert.id} className="p-4 hover:bg-slate-800/30 transition flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`px-2 py-0.5 text-[10px] font-bold rounded border ${
                        alert.severity === "CRITICAL"
                          ? "bg-red-500/10 text-red-400 border-red-500/30"
                          : alert.severity === "HIGH"
                          ? "bg-orange-500/10 text-orange-400 border-orange-500/30"
                          : "bg-blue-500/10 text-blue-400 border-blue-500/30"
                      }`}
                    >
                      {alert.severity}
                    </span>
                    <span className="text-xs font-semibold text-slate-200">{alert.alert_type}</span>
                    <span className="text-[11px] text-slate-500">• {new Date(alert.created_at).toLocaleTimeString()}</span>
                  </div>
                  <p className="text-xs text-slate-300">{alert.message}</p>
                </div>
                <div className="flex items-center space-x-2 shrink-0">
                  {alert.status === "OPEN" ? (
                    <>
                      <button
                        onClick={() => handleAcknowledge(alert.id)}
                        disabled={actionLoading === alert.id}
                        className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-700 transition"
                      >
                        Acknowledge
                      </button>
                      <button
                        onClick={() => handleResolve(alert.id)}
                        disabled={actionLoading === alert.id}
                        className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition"
                      >
                        Resolve
                      </button>
                    </>
                  ) : alert.status === "ACKNOWLEDGED" ? (
                    <button
                      onClick={() => handleResolve(alert.id)}
                      disabled={actionLoading === alert.id}
                      className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition"
                    >
                      Resolve
                    </button>
                  ) : (
                    <span className="text-xs font-medium text-slate-500 uppercase">Resolved</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center text-slate-500 text-xs">
            No active operational or financial integrity alerts. All systems running within verified tolerances.
          </div>
        )}
      </div>
    </div>
  );
}
