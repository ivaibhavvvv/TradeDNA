"use client";

import React from "react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Database,
  Layers,
  RefreshCw,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SyncTelemetry } from "@/lib/types";

interface InitialSyncModalProps {
  telemetry: SyncTelemetry | null;
  isOpen: boolean;
  onDismiss: () => void;
}

export function InitialSyncModal({ telemetry, isOpen, onDismiss }: InitialSyncModalProps) {
  if (!isOpen || !telemetry || !telemetry.has_account) return null;

  const stage = telemetry.sync_stage || "READY";
  const isComplete = stage === "READY";
  const progress = telemetry.historical_sync_progress || (isComplete ? 100 : 45);

  const stagesList = [
    { key: "DISCOVERING_ACCOUNT", label: "Discovering Exness Account", desc: "Verifying server metadata & currency" },
    { key: "DOWNLOADING_HISTORY", label: "Downloading Trading History", desc: "Streaming deals from MT5 terminal" },
    { key: "PROCESSING_EVENTS", label: "Processing Ledger Ingress", desc: "Journaling Layer 1 immutable events" },
    { key: "RECONSTRUCTING", label: "Reconstructing Canonical Positions", desc: "Building double-entry trade timeline" },
    { key: "RECONCILING", label: "Executing Integrity Gate", desc: "Verifying mathematical zero drift" },
    { key: "ANALYZING", label: "Synthesizing Trading DNA", desc: "Generating behavioral intelligence metrics" },
    { key: "READY", label: "Account Ready & Verified", desc: "100.00% integrity grade AAA" },
  ];

  const getStageIndex = (s: string) => {
    switch (s) {
      case "CONNECTING":
        return 0;
      case "DISCOVERING_ACCOUNT":
        return 0;
      case "DOWNLOADING_HISTORY":
        return 1;
      case "PROCESSING_EVENTS":
        return 2;
      case "RECONSTRUCTING":
        return 3;
      case "RECONCILING":
        return 4;
      case "ANALYZING":
        return 5;
      case "READY":
        return 6;
      default:
        return 0;
    }
  };

  const currentIdx = getStageIndex(stage);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl rounded-2xl border border-cyan-800/60 bg-[#0c121e] p-6 shadow-2xl space-y-6 text-white">
        {/* Header */}
        <div className="text-center space-y-1.5">
          <div className="inline-flex items-center justify-center p-3 rounded-full bg-cyan-950 border border-cyan-700/60 text-cyan-400 mb-1">
            {isComplete ? (
              <CheckCircle2 className="h-8 w-8 text-emerald-400" />
            ) : (
              <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
            )}
          </div>
          <h2 className="text-xl font-bold font-mono">
            {isComplete ? "Trading History Verified" : "Synchronizing Exness Account"}
          </h2>
          <p className="text-xs text-slate-400">
            Account: <span className="font-mono text-cyan-300">{telemetry.masked_account_number}</span> • Server: <span className="text-slate-300">{telemetry.server_name}</span>
          </p>
        </div>

        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs font-mono">
            <span className="text-slate-400">Progress</span>
            <span className="text-cyan-400 font-bold">{progress}%</span>
          </div>
          <div className="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-800">
            <div
              className="bg-gradient-to-r from-cyan-500 via-teal-400 to-emerald-400 h-2.5 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Real-Time Metrics Counters Grid */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-center">
            <div className="text-[10px] text-slate-500 uppercase font-mono">Deals / Events</div>
            <div className="text-lg font-bold font-mono text-cyan-300 mt-1">
              {telemetry.events_processed.toLocaleString()}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-center">
            <div className="text-[10px] text-slate-500 uppercase font-mono">Positions</div>
            <div className="text-lg font-bold font-mono text-emerald-300 mt-1">
              {telemetry.positions_discovered.toLocaleString()}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-center">
            <div className="text-[10px] text-slate-500 uppercase font-mono">Data Integrity</div>
            <div className="text-lg font-bold font-mono text-amber-300 mt-1">
              {telemetry.integrity_grade} ({telemetry.integrity_score}%)
            </div>
          </div>
        </div>

        {/* Stages Checklist */}
        <div className="space-y-2 rounded-xl border border-slate-800/80 bg-[#070b13] p-3.5 text-xs max-h-56 overflow-y-auto">
          {stagesList.map((stg, idx) => {
            const isDone = idx < currentIdx || isComplete;
            const isCurrent = idx === currentIdx && !isComplete;

            return (
              <div
                key={stg.key}
                className={`flex items-center justify-between p-2 rounded-lg transition-colors ${
                  isCurrent
                    ? "bg-cyan-950/40 border border-cyan-800/50"
                    : isDone
                    ? "bg-slate-900/30 text-slate-300"
                    : "text-slate-600 opacity-60"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  {isDone ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  ) : isCurrent ? (
                    <RefreshCw className="h-4 w-4 animate-spin text-cyan-400 shrink-0" />
                  ) : (
                    <div className="h-4 w-4 rounded-full border border-slate-700 shrink-0" />
                  )}
                  <div>
                    <div className={`font-semibold ${isCurrent ? "text-cyan-300" : ""}`}>
                      {stg.label}
                    </div>
                    <div className="text-[10px] text-slate-500">{stg.desc}</div>
                  </div>
                </div>
                {isDone && <span className="text-[10px] text-emerald-400 font-mono">DONE</span>}
                {isCurrent && <span className="text-[10px] text-cyan-400 font-mono animate-pulse">ACTIVE</span>}
              </div>
            );
          })}
        </div>

        {/* Action Button */}
        <div className="flex justify-end gap-3 pt-2">
          {isComplete ? (
            <Button
              onClick={onDismiss}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs gap-2 py-2.5"
            >
              <span>Explore Intelligence Dashboard</span>
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              onClick={onDismiss}
              variant="outline"
              className="w-full border-slate-700 text-slate-400 hover:text-white text-xs"
            >
              Continue in Background
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
