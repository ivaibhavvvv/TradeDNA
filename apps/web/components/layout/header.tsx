"use client";

import React from "react";
import { ShieldCheck, ShieldAlert } from "lucide-react";
import { AccountSwitcher } from "./account-switcher";
import { MobileNav } from "./mobile-nav";
import { FreshnessBadge } from "@/components/freshness/FreshnessBadge";
import { ManualSyncButton } from "@/components/freshness/ManualSyncButton";
import { useAccountContext } from "@/components/providers/account-provider";
import { useDashboardOverview } from "@/hooks/use-dashboard-overview";
import { cn } from "@/lib/utils";

interface HeaderProps {
  className?: string;
}

export function Header({ className }: HeaderProps) {
  const { selectedAccount, telemetry, refetchTelemetry } = useAccountContext();
  const { data: overview } = useDashboardOverview();

  const isDegraded = telemetry?.trust_status === "DATA_TRUST_DEGRADED" || overview?.data_integrity?.is_compromised;
  const integrityScore = telemetry?.integrity_score || overview?.data_integrity?.score || "100.00";

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-800/80 bg-[#0a0e17]/90 px-4 md:px-6 backdrop-blur-md",
        className
      )}
    >
      {/* Left side: Mobile Menu + Account Switcher */}
      <div className="flex items-center gap-3">
        <MobileNav />
        <AccountSwitcher />
      </div>

      {/* Right side: Diagnostics, Freshness, Integrity, Manual Sync */}
      <div className="flex items-center gap-2.5">
        {/* Data Integrity Gate Status */}
        {selectedAccount && (
          <div
            className={cn(
              "hidden sm:inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-mono font-medium border transition-colors",
              isDegraded
                ? "border-amber-600/50 bg-amber-950/50 text-amber-300"
                : "border-slate-800 bg-slate-900/60 text-slate-300"
            )}
            title={`Phase 6 Reconciliation Integrity: ${integrityScore}% (Grade ${telemetry?.integrity_grade || "AAA"})`}
          >
            {isDegraded ? (
              <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            )}
            <span>Score {integrityScore}%</span>
          </div>
        )}

        {/* Global Authoritative Data Freshness Badge */}
        <FreshnessBadge telemetry={telemetry} />

        {/* Manual Sync Trigger */}
        <ManualSyncButton
          accountNumber={selectedAccount?.account_number}
          onSyncTriggered={() => refetchTelemetry()}
        />
      </div>
    </header>
  );
}

