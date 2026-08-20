"use client";

/**
 * TradeDNA Phase 8 - Connection State Badge.
 * Represents Logical Account State and Physical Connector Device Status.
 */

import React from "react";
import { StatusIndicator, StatusType } from "../ui/status-indicator";
import { SyncHealth } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ConnectionBadgeProps {
  syncHealth?: SyncHealth;
  className?: string;
}

export function ConnectionBadge({ syncHealth, className }: ConnectionBadgeProps) {
  if (!syncHealth) {
    return <StatusIndicator status="DISCONNECTED" label="No Connection" className={className} />;
  }

  let status: StatusType = "DISCONNECTED";

  if (syncHealth.sync_status === "SYNCING") {
    status = "SYNCING";
  } else if (syncHealth.is_connected && syncHealth.sync_status === "CURRENT") {
    status = "CONNECTED";
  } else if (syncHealth.sync_status === "DEGRADED") {
    status = "DEGRADED";
  } else if (syncHealth.sync_status === "NO_ACCOUNT") {
    status = "DISCONNECTED";
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900/80 px-2.5 py-1 text-xs shadow-sm",
        className
      )}
    >
      <StatusIndicator status={status} />
    </div>
  );
}
