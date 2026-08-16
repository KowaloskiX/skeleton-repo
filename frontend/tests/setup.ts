import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { configureApiClient } from "@/lib/api";

import { API_ORIGIN, server } from "./msw-server";

// In Node, fetch does not accept relative URLs — in a browser the baseUrl is unnecessary.
configureApiClient({ baseUrl: API_ORIGIN });

// jsdom does not implement scrollTo, and the router calls it when restoring scroll position.
window.scrollTo = () => {};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());
