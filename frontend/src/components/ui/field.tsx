import * as LabelPrimitive from "@radix-ui/react-label";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type FieldProps = {
  /** Must match the control's `id` — otherwise the label is not associated with it. */
  htmlFor: string;
  label: string;
  hint?: string;
  error?: string | undefined;
  children: ReactNode;
};

export function Field({ htmlFor, label, hint, error, children }: FieldProps): ReactNode {
  return (
    <div className="space-y-1.5">
      <LabelPrimitive.Root
        htmlFor={htmlFor}
        className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted"
      >
        {label}
      </LabelPrimitive.Root>
      {children}
      <p id={`${htmlFor}-message`} className={cn("text-xs", error ? "text-danger" : "text-muted")}>
        {error ?? hint ?? ""}
      </p>
    </div>
  );
}
