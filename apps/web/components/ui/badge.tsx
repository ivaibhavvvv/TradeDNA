import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-slate-400 select-none",
  {
    variants: {
      variant: {
        default:
          "border border-slate-700 bg-slate-800/80 text-slate-200",
        primary:
          "border border-cyan-500/40 bg-cyan-950/60 text-cyan-300",
        positive:
          "border border-emerald-500/40 bg-emerald-950/60 text-emerald-300 font-mono",
        negative:
          "border border-rose-500/40 bg-rose-950/60 text-rose-300 font-mono",
        warning:
          "border border-amber-500/40 bg-amber-950/60 text-amber-300",
        critical:
          "border border-rose-600 bg-rose-950 text-rose-200 font-semibold animate-pulse",
        neutral:
          "border border-slate-700 bg-slate-800/60 text-slate-300",
        connected:
          "border border-emerald-500/50 bg-emerald-950/70 text-emerald-400",
        disconnected:
          "border border-rose-500/50 bg-rose-950/70 text-rose-400",
        syncing:
          "border border-cyan-500/50 bg-cyan-950/70 text-cyan-300",
        stale:
          "border border-amber-500/50 bg-amber-950/70 text-amber-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
