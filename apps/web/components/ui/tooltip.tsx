"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  className?: string;
}

export function Tooltip({ content, children, className }: TooltipProps) {
  const [isVisible, setIsVisible] = React.useState(false);

  return (
    <div
      className="relative inline-flex items-center"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div
          role="tooltip"
          className={cn(
            "absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs text-slate-200 shadow-lg whitespace-nowrap pointer-events-none animate-in fade-in duration-100",
            className
          )}
        >
          {content}
        </div>
      )}
    </div>
  );
}
