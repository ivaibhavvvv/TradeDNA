"use client";

import React, { useState } from "react";
import { KeyRound, Layers, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { useDashboardOverview } from "@/hooks/use-dashboard-overview";
import { useSyncTrigger } from "@/hooks/use-sync-trigger";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { fetchApi } from "@/lib/api-client";

export default function AccountPage() {
  const { selectedAccount } = useAccountContext();
  const { data: overview, refetch } = useDashboardOverview();
  const { mutate: triggerSync, isPending: isSyncing } = useSyncTrigger();

  const [pairingOpen, setPairingOpen] = useState(false);
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const [pairingExpiry, setPairingExpiry] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const handleGeneratePairingToken = async () => {
    setIsGenerating(true);
    try {
      const res = await fetchApi<{ pairing_token: string; expires_at: string }>("/exness/connection/pair", {
        method: "POST",
      });
      setPairingToken(res.pairing_token);
      setPairingExpiry(res.expires_at);
    } catch (err: any) {
      alert("Failed to generate pairing token: " + err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            EXNESS MT5 CONNECTION & DEVICES
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Manage your read-only Exness MT5 EA connector, pairing tokens, and sync diagnostics.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setPairingOpen(true);
              handleGeneratePairingToken();
            }}
            className="gap-2 text-xs"
          >
            <KeyRound className="h-3.5 w-3.5" />
            Pair New MT5 Terminal
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              triggerSync();
              refetch();
            }}
            disabled={isSyncing}
            className="gap-2 text-xs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin text-cyan-400" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Logical Account Details */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <Layers className="h-4 w-4 text-cyan-400" />
              Logical Exness Trading Account
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Authoritative broker account identifier
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between py-1.5 border-b border-slate-800">
              <span className="text-slate-400 font-sans">Account Number:</span>
              <span className="text-slate-200 font-bold">#{overview?.account_summary?.account_number || "None"}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800">
              <span className="text-slate-400 font-sans">Broker:</span>
              <span className="text-cyan-400 font-bold">{overview?.account_summary?.broker || "EXNESS"}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800">
              <span className="text-slate-400 font-sans">Server Name:</span>
              <span className="text-slate-200">{overview?.account_summary?.server_name || "N/A"}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800">
              <span className="text-slate-400 font-sans">Currency & Mode:</span>
              <span className="text-slate-200">{overview?.account_summary?.currency} • {overview?.account_summary?.trade_mode}</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-400 font-sans">Synchronization State:</span>
              <Badge variant={overview?.sync_health?.is_connected ? "connected" : "disconnected"}>
                {overview?.sync_health?.sync_status || "DISCONNECTED"}
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* Connected Connector Devices */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <Server className="h-4 w-4 text-blue-400" />
              Connected Physical Devices
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Physical MT5 EAs streaming Layer 1 financial observations
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {overview?.connected_devices && overview.connected_devices.length > 0 ? (
              overview.connected_devices.map((d) => (
                <div key={d.device_id} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 flex justify-between items-center">
                  <div>
                    <div className="font-mono text-slate-200 font-medium">Terminal Build {d.terminal_build}</div>
                    <div className="text-[10px] text-slate-500 font-mono">v{d.connector_version} • ID: {d.device_id.slice(0, 8)}</div>
                  </div>
                  <Badge variant={d.is_active ? "connected" : "disconnected"}>
                    {d.is_active ? "Streaming" : "Revoked"}
                  </Badge>
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">
                No active devices. Use the Pair New MT5 Terminal button above.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Pairing Modal */}
      <Dialog
        open={pairingOpen}
        onOpenChange={setPairingOpen}
        title="Pair Exness MT5 Terminal"
        description="Single-use pairing token valid for 5 minutes."
      >
        <div className="space-y-4">
          <div className="rounded-lg bg-slate-900 p-4 border border-slate-800 space-y-2">
            <div className="text-xs text-slate-400">Paste this token into the TradeDNA MT5 Expert Advisor parameters:</div>
            <div className="rounded bg-black/60 p-3 text-center font-mono text-base font-bold text-cyan-400 tracking-wider select-all border border-cyan-900/50">
              {pairingToken || (isGenerating ? "Generating..." : "Click to Generate")}
            </div>
            {pairingExpiry && (
              <div className="text-[11px] text-slate-500 text-center">
                Expires at: {new Date(pairingExpiry).toLocaleTimeString()}
              </div>
            )}
          </div>
          <Button
            variant="default"
            size="sm"
            onClick={() => setPairingOpen(false)}
            className="w-full"
          >
            Done
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
