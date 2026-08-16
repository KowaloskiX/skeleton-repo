import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] font-medium transition-colors disabled:pointer-events-none disabled:opacity-55",
  {
    variants: {
      variant: {
        solid: "bg-accent text-accent-ink hover:opacity-90",
        outline: "border border-line bg-surface text-ink hover:bg-surface-sunken",
        ghost: "text-muted hover:bg-surface-sunken hover:text-ink",
      },
      size: {
        md: "h-10 px-4 text-sm",
        sm: "h-8 px-3 text-xs",
      },
    },
    defaultVariants: { variant: "solid", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof button> & {
    /** Renders the child instead of a <button> — for links that look like buttons. */
    asChild?: boolean;
  };

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ButtonProps): ReactNode {
  const Component = asChild ? Slot : "button";
  return <Component className={cn(button({ variant, size }), className)} {...props} />;
}
