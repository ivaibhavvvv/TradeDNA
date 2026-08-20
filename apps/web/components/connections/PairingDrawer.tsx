"use client";

import React, { useState, useEffect } from "react";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Layers,
  RefreshCw,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Wifi,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { connectionsApi } from "@/lib/api-client";
import { PairingTokenResponse } from "@/lib/types";

export type PairingStage =
  | "GENERATING"
  | "READY"
  | "WAITING_FOR_MT5"
  | "HANDSHAKE_RECEIVED"
  | "VERIFYING_ACCOUNT"
  | "CONNECTED"
  | "INITIAL_SYNC"
  | "EXPIRED"
  | "INVALID"
  | "REJECTED"
  | "ALREADY_USED"
  | "DEVICE_REVOKED"
  | "NETWORK_ERROR";

interface PairingDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function PairingDrawer({ isOpen, onClose, onSuccess }: PairingDrawerProps) {
  const [stage, setStage] = useState<PairingStage>("GENERATING");
  const [pairingData, setPairingData] = useState<PairingTokenResponse | null>(null);
  const [countdown, setCountdown] = useState<number>(300);
  const [copied, setCopied] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Generate pairing token when drawer opens
  useEffect(() => {
    if (!isOpen) {
      setStage("GENERATING");
      setPairingData(null);
      setErrorMessage(null);
      return;
    }

    let isMounted = true;
    const initiatePairing = async () => {
      setStage("GENERATING");
      setErrorMessage(null);
      try {
        const tokenResp = await connectionsApi.generatePairingToken();
        if (isMounted) {
          setPairingData(tokenResp);
          setCountdown(tokenResp.expires_in_seconds || 300);
          setStage("READY");
        }
      } catch (err: any) {
        if (isMounted) {
          setStage("NETWORK_ERROR");
          setErrorMessage(err?.message || "Failed to generate pairing token.");
        }
      }
    };

    initiatePairing();

    return () => {
      isMounted = false;
    };
  }, [isOpen]);

  // Expiration countdown
  useEffect(() => {
    if (!isOpen || stage !== "READY" && stage !== "WAITING_FOR_MT5") return;

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setStage("EXPIRED");
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen, stage]);

  // Polling for incoming MT5 EA connection
  useEffect(() => {
    if (!isOpen || (stage !== "READY" && stage !== "WAITING_FOR_MT5")) return;

    const pollInterval = setInterval(async () => {
      try {
        const overview = await connectionsApi.getOverview();
        if (overview.online_devices > 0 || overview.total_accounts > 0) {
          setStage("HANDSHAKE_RECEIVED");
          setTimeout(() => {
            setStage("VERIFYING_ACCOUNT");
            setTimeout(() => {
              setStage("CONNECTED");
              setTimeout(() => {
                setStage("INITIAL_SYNC");
                onSuccess();
              }, 1500);
            }, 1200);
          }, 1000);
        }
      } catch (err) {
        // Polling error silently ignored
      }
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [isOpen, stage, onSuccess]);

  const copyToken = () => {
    if (pairingData?.pairing_token) {
      navigator.clipboard.writeText(pairingData.pairing_token);
      setCopied(true);
      setStage("WAITING_FOR_MT5");
      setTimeout(() => setCopied(false), 2500);
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative h-full w-full max-w-xl bg-[#0b0f19] border-l border-slate-800 p-6 shadow-2xl flex flex-col justify-between overflow-y-auto">
        {/* Header */}
        <div>
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-cyan-950/60 border border-cyan-700/50 text-cyan-400">
                <Terminal className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white font-mono">Connect Exness Account</h2>
                <p className="text-xs text-slate-400">Pair your Exness MT5 terminal with TradeDNA EA</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Security Banner: 100% Read-Only */}
          <div className="mt-4 rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-3 text-xs text-emerald-300 flex items-start gap-2.5">
            <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" />
            <div>
              <span className="font-semibold text-emerald-200">100% Read-Only Connection:</span> TradeDNA never asks for your Exness login, trading password, or investor password. The connector operates purely as an observation sensor.
            </div>
          </div>

          {/* Main Stage Switcher */}
          <div className="mt-6 space-y-6">
            {stage === "GENERATING" && (
              <div className="flex flex-col items-center justify-center py-12 space-y-3">
                <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
                <p className="text-sm font-medium text-slate-300">Generating secure ephemeral pairing token...</p>
              </div>
            )}

            {(stage === "READY" || stage === "WAITING_FOR_MT5") && pairingData && (
              <div className="space-y-5">
                {/* Ephemeral Pairing Token Box */}
                <div className="rounded-xl border border-cyan-800/50 bg-[#070b13] p-4 space-y-3 shadow-inner">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-cyan-300 font-semibold tracking-wider flex items-center gap-1.5">
                      <Shield className="h-3.5 w-3.5 text-cyan-400" /> EPHEMERAL PAIRING TOKEN
                    </span>
                    <span className="flex items-center gap-1 text-xs font-mono text-amber-400 bg-amber-950/60 border border-amber-800/60 px-2 py-0.5 rounded">
                      <Clock className="h-3 w-3" /> {formatTime(countdown)}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={pairingData.pairing_token}
                      className="w-full bg-slate-900/90 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-cyan-300 focus:outline-none select-all"
                    />
                    <Button
                      onClick={copyToken}
                      size="sm"
                      className="gap-1.5 shrink-0 bg-cyan-600 hover:bg-cyan-500 text-white text-xs"
                    >
                      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? "Copied" : "Copy Token"}
                    </Button>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    This token expires in 5 minutes and can only be used once to provision high-entropy HMAC device credentials.
                  </p>
                </div>

                {/* Step-by-Step Instructions */}
                <div className="space-y-3 text-xs">
                  <h3 className="font-semibold text-slate-200 font-mono flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5 text-cyan-400" /> SETUP INSTRUCTIONS
                  </h3>

                  <div className="space-y-2.5">
                    <div className="flex gap-3 items-start p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-950 text-cyan-400 border border-cyan-700 text-[11px] font-bold">1</span>
                      <div>
                        <strong className="text-white">Enable WebRequest in MT5:</strong>
                        <p className="text-slate-400 mt-0.5 text-[11px]">
                          Go to MT5 <span className="text-slate-300">Tools → Options → Expert Advisors</span>, check <span className="text-slate-300">Allow WebRequest</span>, and add URL: <code className="bg-slate-950 px-1 py-0.5 rounded text-cyan-300">https://api.tradedna.io</code>
                        </p>
                      </div>
                    </div>

                    <div className="flex gap-3 items-start p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-950 text-cyan-400 border border-cyan-700 text-[11px] font-bold">2</span>
                      <div>
                        <strong className="text-white">Attach TradeDNAConnector EA:</strong>
                        <p className="text-slate-400 mt-0.5 text-[11px]">
                          Copy <code className="text-slate-300">TradeDNAConnector.ex5</code> to <code className="text-slate-400">MQL5\Experts</code> and drag it onto any active chart.
                        </p>
                      </div>
                    </div>

                    <div className="flex gap-3 items-start p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-950 text-cyan-400 border border-cyan-700 text-[11px] font-bold">3</span>
                      <div>
                        <strong className="text-white">Paste Pairing Token:</strong>
                        <p className="text-slate-400 mt-0.5 text-[11px]">
                          In the EA Inputs tab, paste the token into <code className="text-cyan-300">InpPairingToken</code> and click OK.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Waiting indicator */}
                <div className="p-3 rounded-lg border border-slate-800 bg-[#090d15] flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 text-slate-300">
                    <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                    <span>Waiting for MT5 terminal connection...</span>
                  </div>
                  <Badge variant="syncing" className="text-[10px] text-cyan-400 border-cyan-800">
                    Listening
                  </Badge>
                </div>
              </div>
            )}

            {stage === "HANDSHAKE_RECEIVED" && (
              <div className="flex flex-col items-center justify-center py-10 space-y-3">
                <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">Handshake Received!</h3>
                <p className="text-xs text-slate-400">Establishing cryptographic session with Exness MT5 terminal...</p>
              </div>
            )}

            {stage === "VERIFYING_ACCOUNT" && (
              <div className="flex flex-col items-center justify-center py-10 space-y-3">
                <ShieldCheck className="h-8 w-8 text-emerald-400 animate-pulse" />
                <h3 className="text-sm font-semibold text-white">Verifying Account Identity</h3>
                <p className="text-xs text-slate-400">Confirming broker server and provisioning device HMAC keys...</p>
              </div>
            )}

            {(stage === "CONNECTED" || stage === "INITIAL_SYNC") && (
              <div className="rounded-xl border border-emerald-800/60 bg-emerald-950/30 p-6 text-center space-y-4">
                <CheckCircle2 className="h-12 w-12 text-emerald-400 mx-auto" />
                <div>
                  <h3 className="text-base font-bold text-white font-mono">Exness Account Connected</h3>
                  <p className="text-xs text-slate-300 mt-1">
                    Terminal verified. Initializing historical ledger synchronization...
                  </p>
                </div>
              </div>
            )}

            {stage === "EXPIRED" && (
              <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 p-6 text-center space-y-4">
                <AlertCircle className="h-10 w-10 text-amber-400 mx-auto" />
                <div>
                  <h3 className="text-sm font-bold text-white">Pairing Token Expired</h3>
                  <p className="text-xs text-slate-400 mt-1">
                    The 5-minute security window elapsed before MT5 connected.
                  </p>
                </div>
                <Button
                  onClick={async () => {
                    setStage("GENERATING");
                    const tokenResp = await connectionsApi.generatePairingToken();
                    setPairingData(tokenResp);
                    setCountdown(tokenResp.expires_in_seconds || 300);
                    setStage("READY");
                  }}
                  className="bg-cyan-600 hover:bg-cyan-500 text-white text-xs"
                >
                  Generate New Token
                </Button>
              </div>
            )}

            {stage === "NETWORK_ERROR" && (
              <div className="rounded-xl border border-rose-800/60 bg-rose-950/30 p-6 text-center space-y-4">
                <AlertCircle className="h-10 w-10 text-rose-400 mx-auto" />
                <div>
                  <h3 className="text-sm font-bold text-white">Pairing Error</h3>
                  <p className="text-xs text-slate-400 mt-1">{errorMessage || "Could not complete handshake."}</p>
                </div>
                <Button
                  onClick={() => onClose()}
                  variant="outline"
                  className="border-slate-700 text-slate-300 text-xs"
                >
                  Close
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 pt-4 flex items-center justify-between text-[11px] text-slate-500">
          <span>TradeDNA MQL5 Protocol v1.0.0</span>
          <span>Zero-Drift Financial Sensor</span>
        </div>
      </div>
    </div>
  );
}
