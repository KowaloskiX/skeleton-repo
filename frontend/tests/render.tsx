import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";

/**
 * Mounts a component inside an in-memory router — the auth forms call `useNavigate`, so
 * without a router they would blow up on a successful mutation.
 *
 * Returns `navigatedTo()` so a test can check the redirect without mocking the router.
 */
export async function renderInRouter(ui: ReactNode) {
  const rootRoute = createRootRoute();
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => ui,
  });
  const appRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/app",
    component: () => <div>dashboard</div>,
  });

  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, appRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  // Without `load()` the RouterProvider mounts only after a microtask, and the first `getBy*`
  // in a test would hit an empty DOM.
  await router.load();

  const result = render(
    <QueryClientProvider client={queryClient}>
      {/* The test router has a different route type than the app one — deliberately, it is
          an isolated tree. */}
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  );

  return { ...result, navigatedTo: () => router.state.location.pathname };
}
