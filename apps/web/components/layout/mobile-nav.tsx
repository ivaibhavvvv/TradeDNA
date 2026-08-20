"use client";

/**
 * TradeDNA Phase 8 - Mobile Navigation Drawer.
 */

import React, { useState } from "react";
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
  Menu,
  ReceiptText,
  ShieldAlert,
  TrendingUp,
  X,
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

export function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <div className="md:hidden">
      <button
        onClick={() => setIsOpen(true)}
        className="rounded-lg p-2 text-slate-300 hover:bg-slate-800 focus:outline-none"
        aria-label="Open Navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setIsOpen(false)}
          />

          {/* Drawer Container */}
          <div className="relative flex flex-col justify-between w-72 max-w-full bg-[#0a0e17] border-r border-slate-800 p-5 z-50 text-slate-200">
            <div>
              {/* Header */}
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded bg-cyan-600 font-mono font-bold text-white text-xs">
                    DNA
                  </div>
                  <span className="text-sm font-bold tracking-tight font-mono text-white">
                    TRADEDNA
                  </span>
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="rounded p-1 text-slate-400 hover:bg-slate-800"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Navigation Items */}
              <nav className="mt-4 space-y-1">
                {MAIN_NAV_ITEMS.map((item) => {
                  const isActive = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
                        isActive
                          ? "bg-slate-800 text-cyan-400 font-semibold"
                          : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                      )}
                    >
                      <span>{ICON_MAP[item.iconName]}</span>
                      <span>{item.title}</span>
                    </Link>
                  );
                })}
              </nav>
            </div>

            {/* Bottom Section */}
            <div className="pt-4 border-t border-slate-800 space-y-3">
              <div className="space-y-1">
                {BOTTOM_NAV_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsOpen(false)}
                    className="flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium text-slate-400 hover:bg-slate-900"
                  >
                    <span>{ICON_MAP[item.iconName]}</span>
                    <span>{item.title}</span>
                  </Link>
                ))}
              </div>

              <div className="flex items-center justify-between rounded-lg bg-slate-900 p-2.5 border border-slate-800">
                <span className="text-xs text-slate-300 truncate">
                  {user?.email}
                </span>
                <button
                  onClick={logout}
                  className="p-1 text-slate-400 hover:text-rose-400"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
