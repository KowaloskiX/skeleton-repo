import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

import { useLogout } from "./mutations";
import { useSession } from "./queries";

/**
 * The part of the header that depends on the session.
 *
 * Three states, not two. "Signed out" and "we do not know yet" look identical to a naive
 * implementation, and the difference is visible on every page load: the session lives in a
 * browser cookie, so neither the server nor the first client paint has an answer. Rendering the
 * signed-out variant then means every signed-in user watches "Sign in" flip to "Sign out".
 *
 * While the answer is unknown we render a placeholder of the same height, so the header does
 * not jump either.
 */
export function SessionNav(): ReactNode {
  const { user, isKnown } = useSession();
  const { logout, isPending: isSigningOut } = useLogout();

  if (!isKnown) {
    return <div className="h-8 w-40" aria-hidden />;
  }

  if (!user) {
    return (
      <>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/login">Sign in</Link>
        </Button>
        <Button size="sm" asChild>
          <Link to="/register">Create account</Link>
        </Button>
      </>
    );
  }

  return (
    <>
      <span className="hidden font-mono text-xs text-muted sm:inline">{user.email}</span>
      <Button variant="outline" size="sm" onClick={() => logout()} disabled={isSigningOut}>
        Sign out
      </Button>
    </>
  );
}
