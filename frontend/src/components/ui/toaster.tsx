import type { ReactNode } from "react";
import { Toaster as Sonner } from "sonner";

/**
 * The toast region. Mounted once, in the root layout.
 *
 * Toasts exist here for one purpose: failures nobody else displays. A form shows its own field
 * errors and its own 401; a background read that fails has no such place, and without a toast it
 * fails in complete silence. The policy that decides which errors reach this region lives in
 * `router.tsx`, next to the query caches.
 *
 * Sonner rather than a hand-rolled component: a correct toast needs a live region, a queue,
 * timers that pause on hover and reduced-motion handling. That is more moving parts than it
 * looks, and getting the accessibility wrong makes it worse than nothing.
 */
export function Toaster(): ReactNode {
  return (
    <Sonner
      position="bottom-right"
      // The theme follows the class on <html>, which the init script sets before the first paint.
      theme="system"
      toastOptions={{
        classNames: {
          toast: "border border-line bg-surface text-ink",
          description: "text-muted",
        },
      }}
    />
  );
}
