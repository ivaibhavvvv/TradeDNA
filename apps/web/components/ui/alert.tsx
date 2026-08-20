import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "info" | "success" | "warning" | "destructive";
  title?: string;
}

export function Alert({
  variant = "info",
  title,
  children,
  className,
  ...props
}: AlertProps) {
  const icons = {
    info: <Info className="h-4 w-4 text-cyan-400 shrink-0" />,
    success: <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />,
    warning: <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />,
    destructive: <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />,
  };

  const borders = {
    info: "border-cyan-900/60 bg-cyan-950/30 text-cyan-200",
    success: "border-emerald-900/60 bg-emerald-950/30 text-emerald-200",
    warning: "border-amber-900/60 bg-amber-950/30 text-amber-200",
    destructive: "border-rose-900/60 bg-rose-950/30 text-rose-200",
  };

  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-lg border p-3.5 text-xs shadow-sm",
        borders[variant],
        className
      )}
      {...props}
    >
      {icons[variant]}
      <div className="space-y-0.5">
        {title && <h5 className="font-semibold leading-tight">{title}</h5>}
        <div className="text-slate-300 [&_p]:leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
