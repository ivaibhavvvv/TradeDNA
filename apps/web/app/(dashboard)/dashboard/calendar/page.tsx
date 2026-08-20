"use client";

/**
 * TradeDNA Phase 8C - Trading Performance Calendar Page.
 */

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
} from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { CalendarDayItem } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

export default function CalendarPage() {
  const router = useRouter();
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDay, setSelectedDay] = useState<CalendarDayItem | null>(null);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_CALENDAR(actNum, year, month + 1),
    queryFn: () => dashboardApi.getCalendar(actNum, year, month + 1),
    enabled: !!actNum,
  });

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  const firstDayIndex = new Date(year, month, 1).getDay();
  const totalDaysInMonth = new Date(year, month + 1, 0).getDate();

  const handlePrevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
  };

  const daysMap = new Map<string, CalendarDayItem>();
  if (data?.days) {
    for (const d of data.days) {
      daysMap.set(d.date, d);
    }
  }

  const currency = data?.currency || "USD";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            DAILY TRADING CALENDAR
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Calendar view of daily realized P&L, trade frequency, and win rate heatmaps.
          </p>
        </div>

        {/* Month Navigation */}
        <div className="flex items-center gap-3 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 self-start sm:self-auto">
          <button
            onClick={handlePrevMonth}
            className="p-1 text-slate-400 hover:text-slate-200 transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-xs font-mono font-bold text-slate-200 min-w-[120px] text-center">
            {monthNames[month]} {year}
          </span>
          <button
            onClick={handleNextMonth}
            className="p-1 text-slate-400 hover:text-slate-200 transition-colors"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Calendar Grid Card */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardContent className="p-4 md:p-6">
          {isLoading ? (
            <div className="grid grid-cols-7 gap-2">
              {Array.from({ length: 35 }).map((_, i) => (
                <Skeleton key={i} className="h-20 rounded-lg" />
              ))}
            </div>
          ) : isError ? (
            <ErrorState
              title="Failed to Load Calendar"
              message={error?.message || "Could not retrieve daily P&L data."}
              onRetry={() => refetch()}
            />
          ) : (
            <div className="space-y-2">
              {/* Day of Week Headers */}
              <div className="grid grid-cols-7 gap-2 text-center text-xs font-semibold text-slate-400 pb-2 border-b border-slate-800">
                <span>Sun</span>
                <span>Mon</span>
                <span>Tue</span>
                <span>Wed</span>
                <span>Thu</span>
                <span>Fri</span>
                <span>Sat</span>
              </div>

              {/* Day Cells */}
              <div className="grid grid-cols-7 gap-2">
                {/* Empty cells before 1st of month */}
                {Array.from({ length: firstDayIndex }).map((_, i) => (
                  <div key={`empty-${i}`} className="h-20 rounded-lg bg-slate-950/20 border border-slate-900/40 opacity-30" />
                ))}

                {/* Days of Month */}
                {Array.from({ length: totalDaysInMonth }).map((_, i) => {
                  const dayNum = i + 1;
                  const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
                  const dayData = daysMap.get(dateStr);
                  const pnl = dayData ? parseFloat(dayData.pnl) : 0;
                  const hasTrades = !!dayData && dayData.trades_count > 0;
                  const isProfit = pnl >= 0;

                  let cellBg = "bg-slate-900/40 border-slate-800/60";
                  if (hasTrades) {
                    if (isProfit && pnl > 0) {
                      cellBg = "bg-emerald-950/40 border-emerald-800/60 hover:bg-emerald-900/40";
                    } else if (!isProfit) {
                      cellBg = "bg-rose-950/40 border-rose-800/60 hover:bg-rose-900/40";
                    } else {
                      cellBg = "bg-slate-800/60 border-slate-700 hover:bg-slate-800";
                    }
                  }

                  return (
                    <div
                      key={dateStr}
                      onClick={() => dayData && setSelectedDay(dayData)}
                      className={cn(
                        "flex flex-col justify-between p-2 rounded-lg border text-xs transition-all h-20",
                        hasTrades ? "cursor-pointer hover:scale-[1.02]" : "opacity-70",
                        cellBg
                      )}
                    >
                      <div className="flex justify-between items-center">
                        <span className="font-mono text-[11px] text-slate-400 font-bold">
                          {dayNum}
                        </span>
                        {hasTrades && (
                          <span className="text-[9px] font-mono text-slate-400">
                            {dayData.trades_count}t
                          </span>
                        )}
                      </div>

                      {hasTrades ? (
                        <div>
                          <div
                            className={cn(
                              "font-mono font-bold text-xs truncate",
                              isProfit ? "text-emerald-400" : "text-rose-400"
                            )}
                          >
                            {formatCurrency(dayData.pnl, currency)}
                          </div>
                          <div className="text-[9px] text-slate-400 font-mono">
                            Win: {dayData.win_rate}
                          </div>
                        </div>
                      ) : (
                        <span className="text-[10px] text-slate-600 font-mono">—</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Selected Day Dialog */}
      <Dialog
        open={!!selectedDay}
        onOpenChange={(open) => {
          if (!open) setSelectedDay(null);
        }}
        title={`Trading Activity: ${selectedDay?.date || ""}`}
        description="Daily canonical summary"
      >
        {selectedDay && (
          <div className="space-y-4 font-mono text-xs">
            <div className="grid grid-cols-2 gap-3 rounded-lg bg-slate-900 p-3.5 border border-slate-800">
              <div>
                <span className="text-[10px] text-slate-500 font-sans">Net Realized P&L:</span>
                <div
                  className={cn(
                    "text-base font-bold mt-0.5",
                    parseFloat(selectedDay.pnl) >= 0 ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  {formatCurrency(selectedDay.pnl, currency)}
                </div>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 font-sans">Trades Executed:</span>
                <div className="text-base font-bold text-slate-200 mt-0.5">
                  {selectedDay.trades_count} closed trades
                </div>
              </div>
            </div>
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400 font-sans">Win Rate:</span>
              <span className="text-cyan-400 font-bold">{selectedDay.win_rate}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSelectedDay(null);
                router.push(`/dashboard/trades?search=${selectedDay.date}`);
              }}
              className="w-full text-xs"
            >
              View In Trades Ledger →
            </Button>
          </div>
        )}
      </Dialog>
    </div>
  );
}
