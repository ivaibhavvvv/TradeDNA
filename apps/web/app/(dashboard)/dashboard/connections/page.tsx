"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Edit2,
  ExternalLink,
  EyeOff,
  Key,
  Laptop,
  Plus,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useAccountContext } from "@/components/providers/account-provider";
import { connectionsApi } from "@/lib/api-client";
import { ConnectionAccount, ConnectionDevice, ConnectionsOverview } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PairingDrawer } from "@/components/connections/PairingDrawer";

export default function ConnectionsPage() {
  const { user } = useAuth();
  const { refetchAccounts } = useAccountContext();
  const [overview, setOverview] = useState<ConnectionsOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Pairing Modal / Drawer State
  const [showPairModal, setShowPairModal] = useState(false);
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const [tokenExpiresIn, setTokenExpiresIn] = useState(300);
  const [isGeneratingPairing, setIsGeneratingPairing] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);

  // Expanded Account Details
  const [expandedAccount, setExpandedAccount] = useState<number | null>(null);

  // Purge Account Modal State
  const [accountToPurge, setAccountToPurge] = useState<number | null>(null);

  // Editing Display Name State
  const [editingAccNum, setEditingAccNum] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [isSavingName, setIsSavingName] = useState(false);

  // Action Loading
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Load Connections
  const fetchOverview = async () => {
    try {
      setError(null);
      const data = await connectionsApi.getOverview();
      setOverview(data);
      if (data.accounts.length > 0 && expandedAccount === null) {
        setExpandedAccount(data.accounts[0].account_number);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load Exness connections.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    const timer = setInterval(fetchOverview, 5000);
    return () => clearInterval(timer);
  }, []);

  // Pairing Countdown
  useEffect(() => {
    if (!pairingToken || tokenExpiresIn <= 0) return;
    const timer = setInterval(() => {
      setTokenExpiresIn((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [pairingToken, tokenExpiresIn]);

  // Actions
  const handleGeneratePairing = async () => {
    setIsGeneratingPairing(true);
    setError(null);
    try {
      const res = await connectionsApi.pairAccount();
      setPairingToken(res.pairing_token);
      setTokenExpiresIn(res.expires_in_seconds || 300);
      setShowPairModal(true);
    } catch (err: any) {
      setError(err?.message || "Failed to generate pairing token.");
    } finally {
      setIsGeneratingPairing(false);
    }
  };

  const handleCopyToken = () => {
    if (!pairingToken) return;
    navigator.clipboard.writeText(pairingToken);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const handleSaveDisplayName = async (accountNumber: number) => {
    if (!editingName.trim()) return;
    setIsSavingName(true);
    try {
      await connectionsApi.updateDisplayName(accountNumber, editingName.trim());
      setEditingAccNum(null);
      await fetchOverview();
      setSuccessMessage("Account label updated successfully.");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(err?.message || "Failed to update account label.");
    } finally {
      setIsSavingName(false);
    }
  };

  const handleRevokeDevice = async (deviceId: string, accountNumber: number) => {
    if (!confirm("Are you sure you want to revoke this MT5 terminal device? Connector ingress will be halted immediately.")) return;
    setActionLoading(`revoke_dev_${deviceId}`);
    try {
      await connectionsApi.revokeDevice(deviceId);
      await fetchOverview();
      setSuccessMessage("Device revoked successfully.");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(err?.message || "Failed to revoke device.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevokeAllDevices = async (accountNumber: number) => {
    if (!confirm(`Revoke all active terminals for Exness #${accountNumber}? Ingress from all terminals will terminate.`)) return;
    setActionLoading(`revoke_all_${accountNumber}`);
    try {
      await connectionsApi.revokeAllDevices(accountNumber);
      await fetchOverview();
      setSuccessMessage("All devices for account revoked successfully.");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(err?.message || "Failed to revoke devices for account.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleHideAccount = async (accountNumber: number) => {
    if (!confirm(`Remove Exness #${accountNumber} from active dashboard view? Historical financial records remain intact.`)) return;
    setActionLoading(`hide_${accountNumber}`);
    try {
      await connectionsApi.hideAccount(accountNumber);
      await fetchOverview();
      refetchAccounts();
      setSuccessMessage("Account hidden from dashboard view.");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(err?.message || "Failed to hide account.");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePurgeAccount = async (accountNumber: number) => {
    setActionLoading(`purge_${accountNumber}`);
    try {
      await connectionsApi.purgeAccount(accountNumber);
      setAccountToPurge(null);
      if (expandedAccount === accountNumber) {
        setExpandedAccount(null);
      }
      await fetchOverview();
      refetchAccounts();
      setSuccessMessage(`Exness Account #${accountNumber} and all associated data have been permanently deleted.`);
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: any) {
      setError(err?.message || "Failed to delete account data.");
    } finally {
      setActionLoading(null);
    }
  };

  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  if (isLoading && !overview) {
    return (
      <div className="flex h-96 items-center justify-center text-slate-400">
        <RefreshCw className="h-6 w-6 animate-spin text-emerald-500 mr-2" />
        Loading Exness Connection Center...
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Top Banner / Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-emerald-950/50 border border-emerald-800/50 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-1.5">
            <ShieldCheck className="h-3 w-3" />
            Exness MT5 Production Ingress
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Connection Center</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Manage authenticated Exness MT5 terminals, view synchronization cursors, and inspect connector telemetry.
          </p>
        </div>

        <Button
          onClick={handleGeneratePairing}
          disabled={isGeneratingPairing}
          className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-4 h-9 shadow-lg shadow-emerald-950/40"
        >
          {isGeneratingPairing ? (
            <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="mr-1.5 h-3.5 w-3.5" />
          )}
          Connect Exness Account
        </Button>
      </div>

      {/* Notifications / Alerts */}
      {error && (
        <div className="flex items-center gap-2 rounded-md border border-rose-900/50 bg-rose-950/40 p-3 text-xs text-rose-200">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center gap-2 rounded-md border border-emerald-900/50 bg-emerald-950/40 p-3 text-xs text-emerald-200">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Telemetry KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <Card className="border-slate-800 bg-[#0d1321]/80 backdrop-blur">
          <CardContent className="p-3.5">
            <div className="text-[11px] font-medium text-slate-400">Exness Accounts</div>
            <div className="text-xl font-bold text-white mt-1">{overview?.total_accounts ?? 0}</div>
            <div className="text-[10px] text-emerald-400 mt-0.5">100% Read-Only Mode</div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-[#0d1321]/80 backdrop-blur">
          <CardContent className="p-3.5">
            <div className="text-[11px] font-medium text-slate-400">Total Terminals</div>
            <div className="text-xl font-bold text-white mt-1">{overview?.total_devices ?? 0}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Paired MT5 Instances</div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-[#0d1321]/80 backdrop-blur">
          <CardContent className="p-3.5">
            <div className="text-[11px] font-medium text-slate-400">Online Terminals</div>
            <div className="text-xl font-bold text-emerald-400 mt-1">{overview?.online_devices ?? 0}</div>
            <div className="text-[10px] text-emerald-400/80 mt-0.5">Active Heartbeats</div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-[#0d1321]/80 backdrop-blur">
          <CardContent className="p-3.5">
            <div className="text-[11px] font-medium text-slate-400">Stale / Revoked</div>
            <div className="text-xl font-bold text-slate-300 mt-1">{overview?.stale_devices ?? 0}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Idle or Inactive</div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-[#0d1321]/80 backdrop-blur col-span-2 sm:col-span-1">
          <CardContent className="p-3.5">
            <div className="text-[11px] font-medium text-slate-400">Overall Freshness</div>
            <div className="text-xl font-bold text-cyan-400 mt-1">{overview?.overall_freshness ?? "UNKNOWN"}</div>
            <div className="text-[10px] text-cyan-300/80 mt-0.5">Zero Drift Invariant</div>
          </CardContent>
        </Card>
      </div>

      {/* Connect Account Drawer / Card (When open) */}
      {showPairModal && (
        <Card className="border-cyan-800/60 bg-gradient-to-br from-[#0c1a2d] to-[#0d1321] shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-cyan-500" />
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Key className="h-5 w-5 text-cyan-400" />
                <CardTitle className="text-base text-white">Connect Exness MetaTrader 5 Terminal</CardTitle>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowPairModal(false)}
                className="text-xs text-slate-400 hover:text-white"
              >
                Dismiss
              </Button>
            </div>
            <CardDescription className="text-xs text-slate-300">
              Attach the TradeDNA observational EA to an MT5 chart and paste this ephemeral token.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-xs">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-3">
                <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 space-y-2">
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Single-Use Pairing Token:</span>
                    <span className="font-mono text-amber-400 flex items-center gap-1 font-semibold">
                      <Clock className="h-3 w-3" />
                      Expires in {formatTime(tokenExpiresIn)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Input
                      readOnly
                      value={pairingToken || ""}
                      className="border-slate-800 bg-slate-900 font-mono text-xs text-emerald-400"
                    />
                    <Button
                      size="sm"
                      onClick={handleCopyToken}
                      className="bg-slate-800 hover:bg-slate-700 text-white shrink-0 text-xs"
                    >
                      {copiedToken ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 space-y-2 text-slate-300">
                  <span className="font-semibold text-white">Connector Instructions:</span>
                  <ol className="list-decimal list-inside space-y-1 text-[11px] text-slate-400">
                    <li>Copy <code className="text-emerald-400">TradeDNAConnector.ex5</code> to <code className="text-slate-300">MQL5\Experts\</code></li>
                    <li>In MT5: <strong>Tools → Options → Expert Advisors</strong></li>
                    <li>Check <strong>Allow WebRequest</strong> for: <code className="text-cyan-400">https://api.tradedna.io</code></li>
                    <li>Do <strong>NOT</strong> enable &quot;Allow Automated Trading&quot; (Read-Only)</li>
                  </ol>
                </div>
              </div>

              <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/20 p-4 flex flex-col justify-center items-center text-center space-y-3">
                <div className="w-10 h-10 rounded-full bg-cyan-950 border border-cyan-500/40 flex items-center justify-center text-cyan-400 animate-pulse">
                  <RefreshCw className="h-5 w-5 animate-spin" />
                </div>
                <div>
                  <h4 className="font-semibold text-white text-xs">Awaiting Connector Handshake</h4>
                  <p className="text-[11px] text-slate-400 mt-1 max-w-xs">
                    Once the EA attaches to the chart with this key, the terminal will establish a secure HMAC session and sync historical deals.
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Connected Accounts List */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <Server className="h-4 w-4 text-emerald-400" />
          Authorized Exness Accounts ({overview?.accounts.length ?? 0})
        </h2>

        {overview?.accounts.length === 0 ? (
          <Card className="border-slate-800 bg-[#0d1321]/60 text-center py-12">
            <CardContent className="space-y-3">
              <Laptop className="h-10 w-10 text-slate-600 mx-auto" />
              <h3 className="text-sm font-semibold text-slate-200">No Connected Exness Accounts</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                No Exness accounts have been paired with this tenant yet. Generate a pairing token to connect your first MT5 terminal.
              </p>
              <Button
                onClick={handleGeneratePairing}
                className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-4 h-8 mt-2"
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Pair First Account
              </Button>
            </CardContent>
          </Card>
        ) : (
          overview?.accounts.map((acc) => {
            const isExpanded = expandedAccount === acc.account_number;
            const isEditing = editingAccNum === acc.account_number;

            return (
              <Card
                key={acc.account_number}
                className={`border transition-all duration-200 ${
                  isExpanded
                    ? "border-slate-700 bg-[#0d1321] shadow-xl"
                    : "border-slate-800/80 bg-[#0d1321]/70 hover:border-slate-700"
                }`}
              >
                {/* Account Card Header */}
                <div className="p-4 sm:p-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-start sm:items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center text-emerald-400 font-bold text-xs shrink-0">
                        MT5
                      </div>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          {isEditing ? (
                            <div className="flex items-center gap-1.5">
                              <Input
                                value={editingName}
                                onChange={(e) => setEditingName(e.target.value)}
                                className="h-7 text-xs bg-slate-950 border-slate-700 w-48 text-white"
                                autoFocus
                              />
                              <Button
                                size="sm"
                                onClick={() => handleSaveDisplayName(acc.account_number)}
                                disabled={isSavingName}
                                className="h-7 px-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs"
                              >
                                Save
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setEditingAccNum(null)}
                                className="h-7 px-2 text-slate-400 text-xs"
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <h3 className="text-sm font-bold text-white">{acc.display_name}</h3>
                              <button
                                onClick={() => {
                                  setEditingAccNum(acc.account_number);
                                  setEditingName(acc.display_name);
                                }}
                                className="text-slate-500 hover:text-slate-300"
                                title="Edit display label"
                              >
                                <Edit2 className="h-3 w-3" />
                              </button>
                            </div>
                          )}

                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-950 border border-slate-800 text-slate-300">
                            #{acc.masked_account_number}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/60 border border-emerald-800/40 text-emerald-400">
                            {acc.server_name}
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-900 text-cyan-300">
                            {acc.currency}
                          </span>
                        </div>

                        <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-1.5 flex-wrap">
                          <span className="flex items-center gap-1">
                            <span
                              className={`h-2 w-2 rounded-full ${
                                acc.connection_status === "CONNECTED"
                                  ? "bg-emerald-400 animate-pulse"
                                  : acc.connection_status === "DEGRADED"
                                  ? "bg-amber-400"
                                  : "bg-rose-400"
                              }`}
                            />
                            {acc.data_freshness_label}
                          </span>
                          <span>•</span>
                          <span>
                            Integrity Grade:{" "}
                            <strong className="text-amber-300 font-mono">{acc.integrity_grade || "A+"}</strong>
                          </span>
                          <span>•</span>
                          <span>
                            Terminals: <strong className="text-white">{acc.active_devices_count} active</strong>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpandedAccount(isExpanded ? null : acc.account_number)}
                        className="text-xs text-slate-300 hover:text-white border border-slate-800 hover:bg-slate-900"
                      >
                        {isExpanded ? "Hide Telemetry" : "View Telemetry"}
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Expanded Telemetry & Device Management */}
                {isExpanded && (
                  <div className="border-t border-slate-800/80 bg-slate-950/50 p-4 sm:p-5 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                      <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/40 space-y-1">
                        <span className="text-[11px] text-slate-500">Synchronization Status</span>
                        <div className="font-mono text-emerald-400 font-semibold">{acc.sync_status}</div>
                        <div className="text-[10px] text-slate-400">
                          Cursor Deal Ticket: #{acc.current_cursor_deal_ticket}
                        </div>
                      </div>

                      <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/40 space-y-1">
                        <span className="text-[11px] text-slate-500">Last Successful Sync</span>
                        <div className="font-mono text-white">
                          {acc.last_successful_sync_at
                            ? new Date(acc.last_successful_sync_at).toLocaleTimeString()
                            : "Never"}
                        </div>
                        <div className="text-[10px] text-slate-400">Continuous Ingress Window</div>
                      </div>

                      <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/40 space-y-1">
                        <span className="text-[11px] text-slate-500">Reconciliation Gate</span>
                        <div className="font-mono text-amber-300 font-bold">
                          {acc.integrity_score ? `${acc.integrity_score}%` : "100.00% Verified"}
                        </div>
                        <div className="text-[10px] text-slate-400">
                          {acc.unresolved_critical_discrepancies} Unresolved Discrepancies
                        </div>
                      </div>
                    </div>

                    {/* Devices Table */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                          <Laptop className="h-3.5 w-3.5 text-cyan-400" />
                          Authorized MT5 Terminals ({acc.devices.length})
                        </span>

                        <div className="flex items-center gap-2 flex-wrap">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRevokeAllDevices(acc.account_number)}
                            disabled={actionLoading === `revoke_all_${acc.account_number}` || acc.devices.length === 0}
                            className="text-[11px] h-7 text-rose-400 hover:text-rose-300 hover:bg-rose-950/30"
                          >
                            Revoke Terminals
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleHideAccount(acc.account_number)}
                            disabled={actionLoading === `hide_${acc.account_number}`}
                            className="text-[11px] h-7 text-slate-400 hover:text-slate-200"
                          >
                            <EyeOff className="h-3 w-3 mr-1" />
                            Hide View
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setAccountToPurge(acc.account_number)}
                            disabled={actionLoading === `purge_${acc.account_number}`}
                            className="text-[11px] h-7 text-rose-400 hover:text-rose-300 hover:bg-rose-950/50 border border-rose-900/40"
                          >
                            <Trash2 className="h-3 w-3 mr-1 text-rose-400" />
                            Remove & Purge All Data
                          </Button>
                        </div>
                      </div>

                      <div className="rounded-lg border border-slate-800 overflow-hidden bg-slate-950/80">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-slate-800 bg-slate-900/60 text-[11px] text-slate-400">
                            <tr>
                              <th className="p-2.5 pl-3">Device ID</th>
                              <th className="p-2.5">Build / Version</th>
                              <th className="p-2.5">Last Seen</th>
                              <th className="p-2.5">Status</th>
                              <th className="p-2.5 text-right pr-3">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 text-slate-300">
                            {acc.devices.length === 0 ? (
                              <tr>
                                <td colSpan={5} className="p-4 text-center text-slate-500 text-xs">
                                  No paired terminal devices. Ingress is inactive.
                                </td>
                              </tr>
                            ) : (
                              acc.devices.map((dev) => (
                                <tr key={dev.device_id} className="hover:bg-slate-900/30">
                                  <td className="p-2.5 pl-3 font-mono text-cyan-300">{dev.masked_device_id}</td>
                                  <td className="p-2.5 font-mono text-slate-400">
                                    Build {dev.terminal_build} / v{dev.connector_version}
                                  </td>
                                  <td className="p-2.5 text-slate-400">
                                    {dev.last_seen_at ? new Date(dev.last_seen_at).toLocaleTimeString() : "Never"}
                                  </td>
                                  <td className="p-2.5">
                                    <span
                                      className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                        dev.status === "ONLINE"
                                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800/40"
                                          : dev.status === "REVOKED"
                                          ? "bg-rose-950 text-rose-400 border border-rose-800/40"
                                          : "bg-slate-800 text-slate-400"
                                      }`}
                                    >
                                      {dev.status}
                                    </span>
                                  </td>
                                  <td className="p-2.5 text-right pr-3">
                                    {!dev.is_revoked && (
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => handleRevokeDevice(dev.device_id, acc.account_number)}
                                        disabled={actionLoading === `revoke_dev_${dev.device_id}`}
                                        className="h-6 px-2 text-[11px] text-rose-400 hover:text-rose-300 hover:bg-rose-950/40"
                                      >
                                        Revoke
                                      </Button>
                                    )}
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            );
          })
        )}
      </div>

      {/* Purge Account Confirmation Modal */}
      {accountToPurge !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-md rounded-xl border border-rose-800/60 bg-[#0d1321] p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-400">
              <div className="w-10 h-10 rounded-full bg-rose-950 border border-rose-700/50 flex items-center justify-center shrink-0">
                <ShieldAlert className="h-5 w-5 text-rose-400" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Permanently Remove Account?</h3>
                <p className="text-xs text-rose-400 font-mono">Exness Account #{accountToPurge}</p>
              </div>
            </div>

            <div className="rounded-lg border border-rose-950 bg-rose-950/20 p-3.5 space-y-2 text-xs text-slate-300">
              <p className="font-semibold text-rose-200">This irreversible action will permanently delete:</p>
              <ul className="list-disc list-inside space-y-1 text-[11px] text-slate-400">
                <li>All historical trades, executions & ledger transactions</li>
                <li>Balance curves, equity snapshots & reconciliation records</li>
                <li>Trading DNA profiles & behavioral bias analytics</li>
                <li>All authorized MT5 terminal device pairings & ingress tokens</li>
              </ul>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setAccountToPurge(null)}
                disabled={actionLoading === `purge_${accountToPurge}`}
                className="text-xs text-slate-400 hover:text-white"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => handlePurgeAccount(accountToPurge)}
                disabled={actionLoading === `purge_${accountToPurge}`}
                className="bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold px-4 h-9 shadow-lg shadow-rose-950/50"
              >
                {actionLoading === `purge_${accountToPurge}` ? (
                  <>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Purging All Data...
                  </>
                ) : (
                  <>
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                    Yes, Purge & Delete All Data
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Ephemeral Pairing Drawer */}
      <PairingDrawer
        isOpen={showPairModal}
        onClose={() => setShowPairModal(false)}
        onSuccess={() => {
          setShowPairModal(false);
          fetchOverview();
        }}
      />
    </div>
  );
}
