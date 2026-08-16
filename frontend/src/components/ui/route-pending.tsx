import type { ReactNode } from "react";

/**
 * Shown while a route resolves (a guard querying the session, a loader fetching data).
 *
 * A bar rather than a spinner in the middle: navigation replaces the content below the header,
 * and a centred spinner makes the whole page jump. This keeps the layout still and only says
 * "something is happening".
 *
 * The router waits before showing it (`defaultPendingMs`), so a fast transition never flashes.
 */
export function RoutePending(): ReactNode {
  return (
    <div className="px-6 py-16 lg:py-24" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="mx-auto h-1 w-full max-w-5xl overflow-hidden rounded-full bg-line">
        <div className="route-pending-bar h-full w-1/3 rounded-full bg-accent" />
      </div>
    </div>
  );
}
