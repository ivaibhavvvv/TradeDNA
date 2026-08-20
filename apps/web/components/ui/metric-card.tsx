import React from "react";
import { ArrowDownRight, ArrowUpRight, HelpCircle } from "lucide-react";
import { Tooltip } from "./tooltip";
import { Badge } from "./badge";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  tooltip?: string;
  badge?: string;
  badgeVariant?: "positive" | "negative" | "warning" | "primary" | "neutral";
  className?: string;
}

export function MetricCard({
  title,
  value,
  subValue,
  trend,
  trendLabel,
  tooltip,
  badge,
  badgeVariant = "neutral",
  className,
}: MetricCardProps) {
  return (
    <div
      className={cn(
        "flex flex-col justify-between rounded-xl border border-slate-800/80 bg-[#0d1321] p-4.5 text-slate-100 shadow-sm transition-all hover:border-slate-700/80",
        className
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {title}
          </span>
          {tooltip && (
            <Tooltip content={tooltip}>
              <HelpCircle className="h-3.5 w-3.5 text-slate-500 hover:text-slate-300 cursor-help" />
            </Tooltip>
          )}
        </div>
        {badge && <Badge variant={badgeVariant}>{badge}</Badge>}
      </div>

      <div className="mt-2.5 flex items-baseline justify-between gap-2">
        <div className="text-xl font-bold tracking-tight font-mono text-slate-100">
          {value}
        </div>
        {trend && (
          <div
            className={cn(
              "flex items-center text-xs font-semibold font-mono",
              trend === "up" && "text-emerald-400",
              trend === "down" && "text-rose-400",
              trend === "neutral" && "text-slate-400"
            )}
          >
            {trend === "up" && <ArrowUpRight className="h-3.5 w-3.5 mr-0.5" />}
            {trend === "down" && <ArrowDownRight className="h-3.5 w-3.5 mr-0.5" />}
            {trendLabel}
          </div>
        )}
      </div>

      {subValue && (
        <div className="mt-1.5 text-xs text-slate-400 leading-none">
          {subValue}
        </div>
      )}
    </div>
  );
}
