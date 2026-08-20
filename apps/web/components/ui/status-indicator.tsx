import React from "react";
import { cn } from "@/lib/utils";

export type StatusType =
  | "CONNECTED"
  | "CONNECTING"
  | "SYNCING"
  | "DEGRADED"
  | "STALE"
  | "DISCONNECTED"
  | "REVOKED";

interface StatusIndicatorProps {
  status: StatusType;
  label?: string;
  className?: string;
}

export function StatusIndicator({ status, label, className }: StatusIndicatorProps) {
  const configs: Record<
    StatusType,
    { dotColor: string; textColor: string; defaultLabel: string; pulse?: boolean }
  > = {
    CONNECTED: {
      dotColor: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]",
      textColor: "text-emerald-400",
      defaultLabel: "Connected",
    },
    CONNECTING: {
      dotColor: "bg-cyan-500",
      textColor: "text-cyan-400",
      defaultLabel: "Connecting",
      pulse: true,
    },
    SYNCING: {
      dotColor: "bg-cyan-400",
      textColor: "text-cyan-300",
      defaultLabel: "Syncing",
      pulse: true,
    },
    DEGRADED: {
      dotColor: "bg-amber-500",
      textColor: "text-amber-400",
      defaultLabel: "Degraded",
    },
    STALE: {
      dotColor: "bg-amber-400",
      textColor: "text-amber-300",
      defaultLabel: "Sync Delayed",
    },
    DISCONNECTED: {
      dotColor: "bg-rose-500",
      textColor: "text-rose-400",
      defaultLabel: "Disconnected",
    },
    REVOKED: {
      dotColor: "bg-slate-500",
      textColor: "text-slate-400",
      defaultLabel: "Revoked",
    },
  };

  const config = configs[status] || configs.DISCONNECTED;
  const displayLabel = label || config.defaultLabel;

  return (
    <div className={cn("inline-flex items-center gap-2 text-xs font-medium", className)}>
      <span
        className={cn(
          "h-2 w-2 rounded-full shrink-0",
          config.dotColor,
          config.pulse && "animate-pulse"
        )}
      />
      <span className={config.textColor}>{displayLabel}</span>
    </div>
  );
}
