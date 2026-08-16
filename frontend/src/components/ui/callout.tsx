import type { ReactNode } from "react";

type CalloutProps = {
  children: ReactNode;
};

/** A form error message. `role="alert"` makes a screen reader announce it immediately. */
export function ErrorCallout({ children }: CalloutProps): ReactNode {
  return (
    <p
      role="alert"
      className="rounded-[var(--radius-control)] border border-danger/40 bg-danger/8 px-3 py-2 text-sm text-danger"
    >
      {children}
    </p>
  );
}
