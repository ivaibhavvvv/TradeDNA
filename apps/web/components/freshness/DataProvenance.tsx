"use client";

import React from "react";
import { Database, ShieldCheck, Clock, Layers } from "lucide-react";
import { SyncTelemetry } from "@/lib/types";

interface DataProvenanceProps {
  telemetry: SyncTelemetry | null;
  moduleName?: string;
}

export function DataProvenance({ telemetry, moduleName }: DataProvenanceProps) {
  if (!telemetry || !telemetry.has_account) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-800/80 bg-slate-950/40 px-3 py-1.5 text-[11px] text-slate-400">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="flex items-center gap-1 text-slate-300 font-medium">
          <Database className="h-3 w-3 text-cyan-400" />
          {moduleName ? `${moduleName} Provenance` : "Data Provenance"}:
        </span>
        <span>
          Calculated:{" "}
          <strong className="font-mono text-slate-200">
            {telemetry.calculated_at ? new Date(telemetry.calculated_at).toLocaleTimeString() : "Live"}
          </strong>
        </span>
        <span>•</span>
        <span>
          Source Snapshot:{" "}
          <strong className="font-mono text-slate-200">
            {telemetry.source_snapshot_at ? new Date(telemetry.source_snapshot_at).toLocaleTimeString() : "Live Ingress"}
          </strong>
        </span>
        {telemetry.reconstruction_run_id && (
          <>
            <span>•</span>
            <span className="hidden sm:inline">
              Recon Run:{" "}
              <strong className="font-mono text-slate-300">
                {telemetry.reconstruction_run_id.slice(0, 8)}...
              </strong>
            </span>
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 text-emerald-400 font-medium">
          <ShieldCheck className="h-3.5 w-3.5" />
          Integrity Grade {telemetry.integrity_grade} ({telemetry.integrity_score}%)
        </span>
      </div>
    </div>
  );
}
