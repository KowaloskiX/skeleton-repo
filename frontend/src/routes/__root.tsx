import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  HeadContent,
  Link,
  Outlet,
  Scripts,
} from "@tanstack/react-router";
import type { ReactNode } from "react";
import { RouteFocus } from "@/components/ui/route-announcer";
import { Toaster } from "@/components/ui/toaster";
import { SessionNav } from "@/features/auth";
import { THEME_INIT_SCRIPT, ThemeToggle } from "@/features/theme";
import appCss from "@/styles/app.css?url";

const MAIN_REGION_ID = "main-content";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Skeleton — a product skeleton" },
      {
        name: "description",
        content:
          "A monorepo with working sign-in: FastAPI + TanStack Start, MongoDB with transactions, architecture boundaries enforced in CI.",
      },
    ],
    // Runs before the first paint, so a dark-mode user never sees a light flash. Declared
    // through the router's head API rather than injected into the shell: a raw <script> in
    // the shell markup broke hydration (React attached no handlers at all).
    scripts: [{ children: THEME_INIT_SCRIPT }],
    links: [
      { rel: "stylesheet", href: appCss },
      // An SVG favicon scales to every size and needs no PNG generation step. Without it every
      // page load ends with a 404 in the console.
      { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
    ],
  }),
  shellComponent: RootDocument,
  component: RootLayout,
});

function RootDocument({ children }: { children: ReactNode }): ReactNode {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootLayout(): ReactNode {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <RouteFocus targetId={MAIN_REGION_ID} />
      <div className="flex min-h-dvh flex-col">
        {/* Visible only when focused: a keyboard user should not have to tab through the whole
            header on every page to reach the content. */}
        <a
          href={`#${MAIN_REGION_ID}`}
          className="sr-only rounded-[var(--radius-control)] bg-accent px-3 py-2 text-sm text-accent-ink focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50"
        >
          Skip to content
        </a>
        <SiteHeader />
        {/* `tabIndex={-1}` so RouteFocus can focus it; it stays out of the tab order. */}
        <main id={MAIN_REGION_ID} tabIndex={-1} className="flex-1 focus:outline-none">
          <Outlet />
        </main>
        <SiteFooter />
      </div>
      <Toaster />
    </QueryClientProvider>
  );
}

function SiteHeader(): ReactNode {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3.5">
        <Link to="/" className="font-mono text-sm tracking-tight text-ink">
          <span className="text-accent">■</span> skeleton
        </Link>

        <nav className="flex items-center gap-1.5">
          <ThemeToggle />
          <SessionNav />
        </nav>
      </div>
    </header>
  );
}

function SiteFooter(): ReactNode {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto max-w-5xl px-6 py-4 font-mono text-[11px] text-muted">
        fastapi · tanstack start · mongodb + redis · boundaries enforced in CI
      </div>
    </footer>
  );
}
