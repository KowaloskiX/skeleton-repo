import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: ComponentProps<"div">): ReactNode {
  return (
    <div
      className={cn("rounded-[var(--radius-panel)] border border-line bg-surface", className)}
      {...props}
    />
  );
}

export function PanelHeader({ className, ...props }: ComponentProps<"div">): ReactNode {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-3 border-b border-line px-4 py-2.5",
        "font-mono text-[11px] uppercase tracking-[0.14em] text-muted",
        className,
      )}
      {...props}
    />
  );
}
