import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-500 disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-slate-800 text-slate-100 shadow hover:bg-slate-700 active:bg-slate-900 border border-slate-700",
        primary:
          "bg-cyan-600 text-white shadow hover:bg-cyan-500 active:bg-cyan-700 font-semibold",
        destructive:
          "bg-rose-900/80 text-rose-100 shadow-sm hover:bg-rose-800 border border-rose-700/50",
        outline:
          "border border-slate-700 bg-transparent text-slate-200 shadow-sm hover:bg-slate-800 hover:text-slate-100",
        secondary:
          "bg-slate-800 text-slate-200 shadow-sm hover:bg-slate-700 border border-slate-700/60",
        ghost:
          "text-slate-300 hover:bg-slate-800/80 hover:text-slate-100",
        link:
          "text-cyan-400 underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
