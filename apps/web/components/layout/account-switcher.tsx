"use client";

/**
 * TradeDNA Phase 8 - Exness Account Switcher.
 * Consumes authorized logical accounts from server context and switches active state.
 */

import React, { useState } from "react";
import { Check, ChevronDown, Layers } from "lucide-react";
import { useAccountContext } from "../providers/account-provider";
import { cn } from "@/lib/utils";

interface AccountSwitcherProps {
  className?: string;
}

export function AccountSwitcher({ className }: AccountSwitcherProps) {
  const { accounts, selectedAccount, setSelectedAccount, isLoadingAccounts } =
    useAccountContext();
  const [isOpen, setIsOpen] = useState(false);

  if (isLoadingAccounts) {
    return (
      <div className="h-8 w-44 rounded-md bg-slate-800/60 animate-pulse border border-slate-700/50" />
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-400">
        <Layers className="h-3.5 w-3.5 text-slate-500" />
        <span>No Exness Account Linked</span>
      </div>
    );
  }

  return (
    <div className={cn("relative inline-block text-left", className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center justify-between gap-2 rounded-lg border border-slate-700 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-slate-100 shadow-sm transition-colors hover:bg-slate-800 focus:outline-none focus:ring-1 focus:ring-cyan-500 min-w-[190px]"
      >
        <div className="flex items-center gap-2 truncate">
          <span className="rounded bg-cyan-950 px-1.5 py-0.5 text-[10px] font-bold text-cyan-400 border border-cyan-800/60 font-mono">
            {selectedAccount?.broker || "EXNESS"}
          </span>
          <span className="font-mono text-slate-200">
            #{selectedAccount?.account_number}
          </span>
          <span className="text-[11px] text-slate-400 font-sans">
            ({selectedAccount?.server_name || "Real"})
          </span>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-slate-400 shrink-0" />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute left-0 mt-2 z-50 w-64 rounded-xl border border-slate-700 bg-[#0d1321] p-1.5 shadow-2xl animate-in fade-in zoom-in-95">
            <div className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-800">
              Authorized Exness Accounts
            </div>
            <div className="mt-1 space-y-1">
              {accounts.map((acc) => {
                const isSelected =
                  selectedAccount?.account_number === acc.account_number;
                return (
                  <button
                    key={acc.id}
                    onClick={() => {
                      setSelectedAccount(acc);
                      setIsOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-colors",
                      isSelected
                        ? "bg-slate-800 text-cyan-300 font-semibold"
                        : "text-slate-300 hover:bg-slate-800/60 hover:text-slate-100"
                    )}
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono">#{acc.account_number}</span>
                        <span className="text-[10px] text-slate-400">
                          {acc.server_name}
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono">
                        {acc.trade_mode} • {acc.currency}
                      </div>
                    </div>
                    {isSelected && (
                      <Check className="h-4 w-4 text-cyan-400 shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
