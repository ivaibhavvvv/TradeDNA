import React from "react";
import { AlertOctagon, RotateCw } from "lucide-react";
import { Button } from "./button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Failed to load financial data",
  message,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-rose-900/40 bg-rose-950/20 p-8 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-950/60 border border-rose-800/60 text-rose-400 mb-3">
        <AlertOctagon className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-semibold text-rose-200">{title}</h3>
      <p className="mt-1 max-w-md text-xs text-rose-300/80 leading-relaxed">
        {message}
      </p>
      {onRetry && (
        <Button
          onClick={onRetry}
          variant="outline"
          size="sm"
          className="mt-4 gap-2 border-rose-800/50 hover:bg-rose-900/30 text-rose-200"
        >
          <RotateCw className="h-3.5 w-3.5" />
          Retry Request
        </Button>
      )}
    </div>
  );
}
