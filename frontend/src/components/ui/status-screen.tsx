import type { ReactNode } from "react";

/**
 * A placeholder screen for states with nothing to render: 404 and an unhandled error.
 *
 * Stateless and with no knowledge of the domain — which is why it lives in `components/ui`.
 * Error text from the error boundary also lands here, so we deliberately render it as
 * **text**: the message comes from the backend, and injecting it as HTML would be a shortcut
 * to XSS.
 */
export function StatusScreen({
  code,
  title,
  description,
  action,
}: {
  code: string;
  title: string;
  description?: string;
  /** A ready element, not a description of an action — 404 needs a `<Link>`, an error a button. */
  action?: ReactNode;
}): ReactNode {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col items-start px-6 py-24">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent">{code}</p>
      <h1 className="mt-3 font-mono text-2xl tracking-tight text-ink">{title}</h1>
      {description && (
        <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">{description}</p>
      )}
      {action && <div className="mt-8">{action}</div>}
    </div>
  );
}
