import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

export const API_ORIGIN = "http://localhost:3000";

export const anonymousSession = http.get(`${API_ORIGIN}/api/auth/session`, () =>
  HttpResponse.json({ user: null }),
);

export const okHealth = http.get(`${API_ORIGIN}/api/health`, () =>
  HttpResponse.json({ status: "ok", env: "test" }),
);

export const server = setupServer(anonymousSession, okHealth);
