"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface TabsProps {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

interface TabItem {
  value: string;
  label: string;
  badge?: string;
}

export function Tabs({ value, onValueChange, children, className }: TabsProps) {
  return (
    <div className={cn("space-y-4", className)}>
      {children}
    </div>
  );
}

export function TabsList({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "inline-flex h-9 items-center justify-center rounded-lg bg-slate-900/90 p-1 text-slate-400 border border-slate-800",
        className
      )}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  activeValue,
  onClick,
  children,
  className,
}: {
  value: string;
  activeValue: string;
  onClick: (val: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const isActive = value === activeValue;
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-xs font-medium transition-all focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
        isActive
          ? "bg-slate-800 text-slate-100 shadow font-semibold"
          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50",
        className
      )}
    >
      {children}
    </button>
  );
}
