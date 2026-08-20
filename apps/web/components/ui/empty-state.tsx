import React from "react";
import { FolderOpen } from "lucide-react";
import { Button } from "./button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-[#0a0f1d]/50 p-10 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-900 border border-slate-800 text-slate-400 mb-4">
        {icon || <FolderOpen className="h-6 w-6 text-slate-500" />}
      </div>
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      <p className="mt-1.5 max-w-sm text-xs text-slate-400 leading-relaxed">
        {description}
      </p>
      {actionLabel && onAction && (
        <Button
          onClick={onAction}
          variant="primary"
          size="sm"
          className="mt-5"
        >
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
