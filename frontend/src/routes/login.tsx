import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Panel } from "@/components/ui/panel";
import { LoginForm, useSession } from "@/features/auth";

export const Route = createFileRoute("/login")({
  // Deliberately no SSR: if the form existed before hydration, clicking "Sign in" would do a
  // NATIVE submit and push the password into the query string and the browser history.
  ssr: false,
  component: LoginPage,
});

function LoginPage(): ReactNode {
  const { user, isKnown } = useSession();

  return (
    <div className="mx-auto w-full max-w-sm px-6 py-16 lg:py-24">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent">sign in</p>
      <h1 className="mt-3 font-mono text-2xl tracking-tight text-ink">Back to your organization</h1>

      <Panel className="mt-7 p-5">
        {user ? (
          <p className="text-sm text-muted">
            You are signed in as {user.email}.{" "}
            <Link to="/app" className="text-accent underline underline-offset-2">
              Go to the dashboard
            </Link>
            .
          </p>
        ) : !isKnown ? (
          // Neither the form nor the "you are signed in" note until the session is known —
          // otherwise a signed-in user sees the login form flash before the redirect.
          <div className="h-64" aria-hidden />
        ) : (
          <LoginForm />
        )}
      </Panel>

      <p className="mt-5 text-sm text-muted">
        No account yet?{" "}
        <Link to="/register" className="text-accent underline underline-offset-2">
          Create an organization
        </Link>
        .
      </p>
    </div>
  );
}
