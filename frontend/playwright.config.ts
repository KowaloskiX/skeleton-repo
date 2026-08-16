import { defineConfig, devices } from "@playwright/test";

// Configurable ports: on a developer machine 3000/8000 can be taken by another project.
// vite.config.ts reads the same variables, so the /api proxy points at the right backend.
const WEB_PORT = process.env.WEB_PORT ?? "3000";
const API_PORT = process.env.API_PORT ?? "8000";
const WEB_URL = `http://localhost:${WEB_PORT}`;

/**
 * Smoke E2E over the money path (registration -> dashboard -> sign-out -> sign-in).
 * Requires the database: run `docker compose up -d` first.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: WEB_URL, trace: "on-first-retry" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // No separate migration step: on dev the application creates indexes at startup.
      command: `uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://localhost:${API_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "pnpm dev",
      url: WEB_URL,
      env: { WEB_PORT, API_PORT },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
