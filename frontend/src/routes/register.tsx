import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Panel } from "@/components/ui/panel";
import { RegisterForm, useSession } from "@/features/auth";

export const Route = createFileRoute("/register")({
  // See the comment in login.tsx: a native submit before hydration would carry the password
  // into the URL.
  ssr: false,
  component: RegisterPage,
});

function RegisterPage(): ReactNode {
  const { user, isKnown } = useSession();

  return (
    <div className="mx-auto w-full max-w-sm px-6 py-16 lg:py-24">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent">new account</p>
      <h1 className="mt-3 font-mono text-2xl tracking-tight text-ink">Create an organization</h1>

      <Panel className="mt-7 p-5">
        {user ? (
          <p className="text-sm text-muted">
            You are already signed in as {user.email}.{" "}
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
          <RegisterForm />
        )}
      </Panel>

      <p className="mt-5 text-sm text-muted">
        Already have an account?{" "}
        <Link to="/login" className="text-accent underline underline-offset-2">
          Sign in
        </Link>
        .
      </p>
    </div>
  );
}
