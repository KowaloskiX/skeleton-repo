import { useQuery } from "@tanstack/react-query";

import { authSessionOptions, type CurrentUserResponse } from "@/lib/api";

/**
 * One source of session state. Route loaders use the same key (`ensureQueryData`).
 *
 * Disabled during SSR on purpose: the session lives in a browser cookie and the generated
 * client uses relative URLs, so on the server the request could only fail. Left enabled, the
 * failure resolved the query to "no data", the server rendered the signed-out header, and the
 * user watched it flip after hydration.
 */
export function sessionQueryOptions() {
  return { ...authSessionOptions(), enabled: typeof window !== "undefined" };
}

export function useSession(): {
  user: CurrentUserResponse | null;
  /** `false` until the answer arrives — signed out and "not known yet" are different states. */
  isKnown: boolean;
} {
  const query = useQuery(sessionQueryOptions());
  return { user: query.data?.user ?? null, isKnown: query.data !== undefined };
}
