const FALLBACK = "Could not reach the API. Check that the backend is running on :8000.";

/**
 * The backend returns `{ code, message }` — we show `message`, because it is the single source
 * of truth about what went wrong and is already written for a human.
 */
export function apiErrorMessage(error: unknown): string {
  if (typeof error !== "object" || error === null) return FALLBACK;
  const message = (error as { message?: unknown }).message;
  return typeof message === "string" && message.length > 0 ? message : FALLBACK;
}
