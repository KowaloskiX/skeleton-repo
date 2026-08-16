import { client } from "./generated/client.gen";

// Two names, because the backend only adds the `__Host-` prefix over HTTPS (over http a
// browser would reject such a cookie). Order matters: the prefixed one is the safer variant,
// so it wins when both exist.
const CSRF_COOKIE_NAMES = ["__Host-csrf_token", "csrf_token"] as const;
const CSRF_HEADER = "X-CSRF-Token";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Escapes regex metacharacters — the cookie name is configurable on the backend. */
function escapeForRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapeForRegExp(name)}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function readCsrfToken(): string | null {
  for (const name of CSRF_COOKIE_NAMES) {
    const token = readCookie(name);
    if (token) return token;
  }
  return null;
}

/**
 * Configures the generated client. Called once, when the router is created.
 *
 * URLs are relative (`baseUrl: false` in openapi-ts.config.ts), so the API is on the same
 * origin as the frontend and the session cookie is first-party.
 */
export function configureApiClient(options?: { baseUrl?: string }): void {
  // We pass baseUrl only in tests: Node requires an absolute URL, a browser does not.
  client.setConfig({ credentials: "same-origin", ...options });

  // TanStack Start calls `getRouter()` on EVERY SSR request while `client` is a module
  // singleton — without clearing, the interceptor list would grow linearly with the number of
  // requests served and every API call would run through all of them.
  client.interceptors.request.clear();
  client.interceptors.error.clear();

  client.interceptors.request.use((request) => {
    if (!UNSAFE_METHODS.has(request.method)) return request;
    // Double-submit cookie: the backend issues a signed token from GET /api/auth/session.
    const token = readCsrfToken();
    if (token) request.headers.set(CSRF_HEADER, token);
    return request;
  });

  // The generated client throws the response BODY alone, so the HTTP status is lost. Without
  // it there is no way to tell "the session expired" (401) from an ordinary validation error —
  // and that is the difference between redirecting to sign-in and showing a form message.
  client.interceptors.error.use((error, response) => ({
    ...(typeof error === "object" && error !== null ? error : {}),
    // `response` can be undefined when the request never reached the server (offline, DNS).
    status: response?.status,
  }));
}

/** Shape of an API error after passing through the interceptor above. */
export type ApiFailure = {
  code?: string;
  message?: string;
  status?: number;
};

function asFailure(error: unknown): ApiFailure | null {
  return typeof error === "object" && error !== null ? (error as ApiFailure) : null;
}

/**
 * Does this error mean "you are not (or no longer) signed in"?
 *
 * `GET /api/auth/session` deliberately returns 200 with `user: null` for anonymous visitors,
 * so every 401 is a session that expired or was revoked — not a normal application state.
 */
export function isUnauthorized(error: unknown): boolean {
  return asFailure(error)?.status === 401;
}

/**
 * Is this a failure the user cannot act on, and nothing else will show?
 *
 * Deliberately narrow. A 4xx belongs to whoever made the request: the login form shows its own
 * 401, a form shows its own 422. What has no owner is a read that failed and everything from
 * 5xx upwards, including a request that never left the machine (offline, DNS) — those would
 * otherwise fail in complete silence.
 */
export function isUnattendedFailure(error: unknown): boolean {
  const status = asFailure(error)?.status;
  return status === undefined || status >= 500;
}

/**
 * Does this error mean "the CSRF token is stale"?
 *
 * The token is bound to the session, so the session expiring — or signing in from another tab
 * — invalidates it too. It shows up as a 403 on a mutation, and is fixed by a single session
 * read, because the backend then replaces the cookie with a current one.
 */
export function isStaleCsrfToken(error: unknown): boolean {
  const failure = asFailure(error);
  return failure?.status === 403 && failure.code === "csrf_invalid";
}
