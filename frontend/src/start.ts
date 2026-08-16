import { createMiddleware, createStart } from "@tanstack/react-start";

/**
 * Security headers for the **HTML document**.
 *
 * The backend sets its own set (`app/core/http_security.py`), but that only covers responses
 * from `/api`. A browser enforces the CSP carried by the response that delivered the document
 * — and that comes from the TanStack Start server, not from FastAPI. Without this file the
 * page had no CSP at all, even though the API did.
 */

/**
 * The production policy. `'unsafe-inline'` in `script-src` is forced by Start: SSR injects
 * hydration data as an inline `<script>`. A nonce would require a custom server entry and a
 * rewritten renderer — deliberately deferred and recorded as debt.
 *
 * `connect-src 'self'` is enough because the API is served from the same origin under `/api`.
 */
const PRODUCTION_CSP = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  "connect-src 'self'",
  "object-src 'none'",
].join("; ");

/**
 * In dev the policy is loosened with `ws:` — without it Vite's HMR cannot open its websocket
 * and a module reload ends in a silent console error.
 */
const DEVELOPMENT_CSP = `${PRODUCTION_CSP.replace(
  "connect-src 'self'",
  "connect-src 'self' ws: wss:",
)}`;

const SECURITY_HEADERS: Record<string, string> = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
  "X-Frame-Options": "DENY",
};

const securityHeaders = createMiddleware({ type: "request" }).server(async ({ next }) => {
  const result = await next();

  for (const [header, value] of Object.entries(SECURITY_HEADERS)) {
    if (!result.response.headers.has(header)) {
      result.response.headers.set(header, value);
    }
  }
  if (!result.response.headers.has("Content-Security-Policy")) {
    result.response.headers.set(
      "Content-Security-Policy",
      import.meta.env.PROD ? PRODUCTION_CSP : DEVELOPMENT_CSP,
    );
  }

  return result;
});

export const startInstance = createStart(() => ({
  requestMiddleware: [securityHeaders],
}));
