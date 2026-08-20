"use client";

/**
 * TradeDNA Phase 8 - Data Freshness Indicator.
 * Displays relative provenance calculation time and warns if sync is delayed.
 */

import React, { useEffect, useState } from "react";
import { Clock, RefreshCw } from "lucide-react";
import { Provenance } from "@/lib/types";
import { cn } from "@/lib/utils";

interface DataFreshnessBadgeProps {
  provenance: Provenance | null;
  className?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export function DataFreshnessBadge({
  provenance,
  className,
  onRefresh,
  isRefreshing,
}: DataFreshnessBadgeProps) {
  const [secondsAgo, setSecondsAgo] = useState<number>(0);

  useEffect(() => {
    if (!provenance?.calculated_at) return;

    const calcTime = new Date(provenance.calculated_at).getTime();

    const updateDelta = () => {
      const now = Date.now();
      const diffSec = Math.max(0, Math.floor((now - calcTime) / 1000));
      setSecondsAgo(diffSec);
    };

    updateDelta();
    const interval = setInterval(updateDelta, 2000);
    return () => clearInterval(interval);
  }, [provenance?.calculated_at]);

  if (!provenance) {
    return (
      <div className={cn("inline-flex items-center gap-1.5 text-xs text-slate-500", className)}>
        <Clock className="h-3.5 w-3.5" />
        <span>Awaiting Sync</span>
      </div>
    );
  }

  let label = "Updated just now";
  let statusColor = "text-slate-400 border-slate-800 bg-slate-900/60";

  if (secondsAgo >= 600) {
    label = "Data Stale (>10m)";
    statusColor = "text-rose-400 border-rose-900/60 bg-rose-950/40";
  } else if (secondsAgo >= 120) {
    const mins = Math.floor(secondsAgo / 60);
    label = `Sync Delayed (${mins}m ago)`;
    statusColor = "text-amber-400 border-amber-900/60 bg-amber-950/40";
  } else if (secondsAgo >= 5) {
    label = `Updated ${secondsAgo}s ago`;
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-mono transition-colors",
        statusColor,
        className
      )}
    >
      <Clock className="h-3 w-3 shrink-0 text-slate-400" />
      <span>{label}</span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="ml-1 text-slate-400 hover:text-cyan-400 transition-colors disabled:opacity-50"
          title="Trigger sync request"
        >
          <RefreshCw className={cn("h-3 w-3", isRefreshing && "animate-spin text-cyan-400")} />
        </button>
      )}
    </div>
  );
}
