import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: ComponentProps<"input">): ReactNode {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm text-ink",
        "placeholder:text-muted/70 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
