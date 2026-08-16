import { useRouterState } from "@tanstack/react-router";
import { type ReactNode, useEffect, useRef } from "react";

/**
 * Moves focus to the main region after every navigation.
 *
 * In a single-page application the browser does none of what it does on a full page load: the
 * URL changes, the document does not, so a screen reader announces nothing and `Tab` continues
 * from wherever the clicked link was. Focusing the main region fixes both — the new content is
 * announced and the tab order restarts there.
 *
 * The `<main>` element it targets carries `tabIndex={-1}`: focusable programmatically, but not
 * a stop in the tab order.
 */
export function RouteFocus({ targetId }: { targetId: string }): ReactNode {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const previousPathname = useRef<string | null>(null);

  useEffect(() => {
    const previous = previousPathname.current;
    previousPathname.current = pathname;

    // `null` is the first render: on a fresh page load the browser has already placed focus,
    // and stealing it would scroll a deep-linked page back to the top. An unchanged pathname
    // means a re-render rather than a navigation.
    if (previous === null || previous === pathname) return;

    document.getElementById(targetId)?.focus({ preventScroll: true });
  }, [pathname, targetId]);

  return null;
}
