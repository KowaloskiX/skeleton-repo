import { createFileRoute, redirect } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { StatusScreen } from "@/components/ui/status-screen";
import { sessionQueryOptions, useSession } from "@/features/auth";

export const Route = createFileRoute("/app")({
  // No SSR: the session lives in a browser cookie, so the guard has to run on the client.
  // Otherwise the server would render the dashboard without knowing who is asking.
  ssr: false,
  beforeLoad: async ({ context }) => {
    const session = await context.queryClient.ensureQueryData(sessionQueryOptions());
    if (!session.user) throw redirect({ to: "/login" });
  },
  component: AppPage,
  // Its own boundary, so a failure inside the dashboard does not take down the header and the
  // navigation with it — the user can still sign out or go back to the landing page.
  errorComponent: DashboardError,
});

function DashboardError({ error, reset }: { error: Error; reset: () => void }): ReactNode {
  return (
    <StatusScreen
      code="dashboard"
      title="Could not load the dashboard"
      description={error.message}
      action={
        <Button variant="ghost" size="sm" onClick={reset}>
          Try again
        </Button>
      }
    />
  );
}

function AppPage(): ReactNode {
  const { user } = useSession();
  if (!user) return null;

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-16 lg:py-20">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent">dashboard</p>
      <h1 className="mt-3 font-mono text-2xl tracking-tight text-ink">{user.email}</h1>
      <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
        A route protected by a guard in <code className="font-mono text-xs">beforeLoad</code>. Sign
        out in the header — the session dies on the server, not just in the browser.
      </p>

      <Panel className="mt-8">
        <PanelHeader>
          <span>organizations</span>
          <span>{user.organizations.length}</span>
        </PanelHeader>
        <ul className="divide-y divide-line">
          {user.organizations.map((organization) => (
            <li
              key={organization.id}
              className="flex items-baseline justify-between gap-4 px-4 py-3"
            >
              <span className="text-sm text-ink">{organization.name}</span>
              <span className="font-mono text-xs text-muted">
                {organization.slug} · {organization.role}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
