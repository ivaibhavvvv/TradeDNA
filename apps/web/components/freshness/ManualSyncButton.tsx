"use client";

import React, { useState } from "react";
import { Check, RefreshCw, AlertCircle } from "lucide-react";
import { dashboardApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";

interface ManualSyncButtonProps {
  accountNumber?: number | null;
  onSyncTriggered?: () => void;
  className?: string;
}

export function ManualSyncButton({
  accountNumber,
  onSyncTriggered,
  className = "",
}: ManualSyncButtonProps) {
  const [syncState, setSyncState] = useState<"IDLE" | "REQUESTING" | "SYNCING" | "COMPLETED" | "FAILED">("IDLE");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleManualSync = async () => {
    if (!accountNumber || syncState === "REQUESTING" || syncState === "SYNCING") return;

    setSyncState("REQUESTING");
    setErrorMessage(null);
    try {
      await dashboardApi.triggerSync(accountNumber);
      setSyncState("SYNCING");
      if (onSyncTriggered) onSyncTriggered();

      // Transition to completed after 2.5s simulation of sync trigger
      setTimeout(() => {
        setSyncState("COMPLETED");
        setTimeout(() => setSyncState("IDLE"), 3000);
      }, 2500);
    } catch (err: any) {
      setSyncState("FAILED");
      setErrorMessage(err?.message || "Sync trigger failed.");
      setTimeout(() => setSyncState("IDLE"), 4000);
    }
  };

  if (!accountNumber) return null;

  return (
    <div className="relative inline-flex items-center">
      <Button
        size="sm"
        variant="ghost"
        onClick={handleManualSync}
        disabled={syncState === "REQUESTING" || syncState === "SYNCING"}
        className={`h-8 px-2.5 text-xs text-slate-300 hover:text-white border border-slate-800 hover:bg-slate-900 ${className}`}
        title="Trigger manual connector synchronization check"
        aria-label="Manual Sync Trigger"
      >
        {syncState === "REQUESTING" || syncState === "SYNCING" ? (
          <>
            <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5 text-cyan-400" />
            <span>Syncing...</span>
          </>
        ) : syncState === "COMPLETED" ? (
          <>
            <Check className="h-3.5 w-3.5 mr-1.5 text-emerald-400" />
            <span className="text-emerald-400">Synced</span>
          </>
        ) : syncState === "FAILED" ? (
          <>
            <AlertCircle className="h-3.5 w-3.5 mr-1.5 text-rose-400" />
            <span className="text-rose-400">Failed</span>
          </>
        ) : (
          <>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5 text-slate-400" />
            <span>Sync Now</span>
          </>
        )}
      </Button>

      {errorMessage && (
        <span className="absolute right-0 top-full mt-1 text-[10px] text-rose-400 bg-rose-950/80 px-2 py-0.5 rounded border border-rose-900 z-50 whitespace-nowrap">
          {errorMessage}
        </span>
      )}
    </div>
  );
}
