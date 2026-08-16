import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { createRouter, Link, useRouter } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { RoutePending } from "@/components/ui/route-pending";
import { StatusScreen } from "@/components/ui/status-screen";

import {
  apiErrorMessage,
  authSessionQueryKey,
  configureApiClient,
  isStaleCsrfToken,
  isUnattendedFailure,
  isUnauthorized,
} from "@/lib/api";

import { routeTree } from "./routeTree.gen";

/** TanStack Start requires a `getRouter` export returning a NEW instance on every call. */
export function getRouter() {
  configureApiClient();

  // Assigned after the router is built — the cache needs the router and the router needs the
  // cache. Instead of a cycle: one reference, reassigned once.
  let resyncSession = (): void => {};

  const onError = (error: unknown): void => {
    // 401 = the session died. 403 csrf_invalid = a CSRF token bound to a session that no
    // longer exists; the backend replaces the cookie on the next session read, so the reaction
    // is the same. Without this the application is stuck holding a token it cannot use.
    if (isUnauthorized(error) || isStaleCsrfToken(error)) {
      resyncSession();
      return;
    }
    // Everything the components handle themselves stays quiet — see `isUnattendedFailure`.
    if (isUnattendedFailure(error)) {
      toast.error("Something went wrong", { description: apiErrorMessage(error) });
    }
  };

  const queryClient = new QueryClient({
    // Session expiry can surface from a read as well as from a write — hence both caches.
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // A 401 on /api/auth/session is the normal "signed out" state, not a failure.
        retry: false,
      },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreload: "intent",
    defaultNotFoundComponent: NotFound,
    defaultPendingComponent: RoutePending,
    // Wait before showing anything: a transition that resolves in 80 ms would otherwise flash a
    // loading bar, which reads as jank rather than as feedback.
    defaultPendingMs: 300,
    // …and once shown, keep it up briefly, so it does not blink out mid-animation.
    defaultPendingMinMs: 400,
    // An error boundary for the whole application. Without it an exception during render gives
    // a blank page: React unmounts the entire tree and nothing is left, not even navigation.
    defaultErrorComponent: ErrorScreen,
  });

  resyncSession = (): void => {
    // On the server there is nothing to refresh — SSR returns the document and the route guard
    // does its job on the client.
    if (typeof window === "undefined") return;
    void (async () => {
      // Reading the session is also the moment the backend issues a fresh CSRF cookie.
      await queryClient.invalidateQueries({ queryKey: authSessionQueryKey() });
      // `invalidate` runs the route through `beforeLoad` again, so the guard redirects to the
      // login page by itself. Deliberately no `navigate({to: "/login"})`: public routes should
      // stay where they are.
      await router.invalidate();
    })();
  };

  return router;
}

function NotFound(): ReactNode {
  return (
    <StatusScreen
      code="404"
      title="No such page"
      description="The address is out of date or contains a typo."
      // A `Link` rather than a button with `navigate`: it is an ordinary anchor that works
      // before hydration and can be opened in a new tab.
      action={
        <Link to="/" className="font-mono text-xs uppercase tracking-[0.18em] text-accent">
          Back to the home page
        </Link>
      }
    />
  );
}

function ErrorScreen({ error }: { error: Error }): ReactNode {
  const router = useRouter();
  return (
    <StatusScreen
      code="error"
      title="Something went wrong"
      // `error.message` can be technical, but without it a user report reads "it does not
      // work" and cannot be tied to anything in the logs.
      description={error.message}
      action={
        <Button variant="ghost" size="sm" onClick={() => void router.invalidate()}>
          Try again
        </Button>
      }
    />
  );
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof getRouter>;
  }
}
