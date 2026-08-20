"use client";

/**
 * TradeDNA Phase 8 - Desktop Sidebar Navigation.
 * Provides access to the 11 primary financial intelligence modules.
 */

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  CalendarDays,
  Coins,
  Clock,
  Dna,
  Layers,
  LayoutDashboard,
  Lock,
  LogOut,
  ReceiptText,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import { BOTTOM_NAV_ITEMS, MAIN_NAV_ITEMS } from "@/lib/constants";
import { useAuth } from "../providers/auth-provider";
import { cn } from "@/lib/utils";

const ICON_MAP: Record<string, React.ReactNode> = {
  LayoutDashboard: <LayoutDashboard className="h-4 w-4" />,
  TrendingUp: <TrendingUp className="h-4 w-4" />,
  ReceiptText: <ReceiptText className="h-4 w-4" />,
  ShieldAlert: <ShieldAlert className="h-4 w-4" />,
  Activity: <Activity className="h-4 w-4" />,
  Dna: <Dna className="h-4 w-4" />,
  Coins: <Coins className="h-4 w-4" />,
  Clock: <Clock className="h-4 w-4" />,
  CalendarDays: <CalendarDays className="h-4 w-4" />,
  Layers: <Layers className="h-4 w-4" />,
  Lock: <Lock className="h-4 w-4" />,
};

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col justify-between w-64 shrink-0 border-r border-slate-800/80 bg-[#0a0e17] text-slate-200 select-none min-h-screen",
        className
      )}
    >
      {/* Brand Header */}
      <div>
        <div className="flex items-center gap-2.5 px-6 py-5 border-b border-slate-800/80">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 font-mono font-bold text-black text-xs shadow-md">
            DNA
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-tight text-white font-mono">
              TRADEDNA
            </span>
            <span className="text-[10px] font-medium tracking-widest text-cyan-400 uppercase">
              Exness Intelligence
            </span>
          </div>
        </div>

        {/* Main Navigation Modules */}
        <div className="px-3 py-4 space-y-1">
          <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Intelligence Modules
          </div>
          <nav className="space-y-0.5" aria-label="Main Navigation">
            {MAIN_NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href || (item.href !== "/dashboard/overview" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-slate-800/90 text-cyan-400 font-semibold shadow-sm border border-slate-700/50"
                      : "text-slate-400 hover:bg-slate-900/80 hover:text-slate-200"
                  )}
                >
                  <span className={cn(isActive ? "text-cyan-400" : "text-slate-500")}>
                    {ICON_MAP[item.iconName]}
                  </span>
                  <span>{item.title}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Bottom Section: Account, Security, User */}
      <div className="px-3 py-4 border-t border-slate-800/80 space-y-3">
        <div className="space-y-0.5">
          <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Workspace Settings
          </div>
          {BOTTOM_NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
                  isActive
                    ? "bg-slate-800/90 text-cyan-400 font-semibold border border-slate-700/50"
                    : "text-slate-400 hover:bg-slate-900/80 hover:text-slate-200"
                )}
              >
                <span className={cn(isActive ? "text-cyan-400" : "text-slate-500")}>
                  {ICON_MAP[item.iconName]}
                </span>
                <span>{item.title}</span>
              </Link>
            );
          })}
        </div>

        {/* User Card & Logout */}
        <div className="flex items-center justify-between rounded-lg bg-slate-900/80 p-2.5 border border-slate-800">
          <div className="flex flex-col truncate pr-2">
            <span className="text-xs font-medium text-slate-200 truncate">
              {user?.full_name || user?.email || "Trader"}
            </span>
            <span className="text-[10px] text-slate-500 font-mono truncate">
              {user?.tenant_name || "Workspace"}
            </span>
          </div>
          <button
            onClick={logout}
            title="Log Out"
            className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-rose-400 transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
