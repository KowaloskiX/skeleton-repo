import viteReact from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * A config separate from `vite.config.ts` — the TanStack Start plugin takes over the
 * application build and is not needed for component tests.
 */
export default defineConfig({
  plugins: [viteReact()],
  resolve: {
    alias: {
      "@": new URL("./src", import.meta.url).pathname,
      // The test harness (MSW, router render) lives in tests/; the tests themselves sit next
      // to the code.
      "@tests": new URL("./tests", import.meta.url).pathname,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["src/**/*.test.tsx", "src/**/*.test.ts"],
  },
});
