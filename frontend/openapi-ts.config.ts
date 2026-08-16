import { defineConfig } from "@hey-api/openapi-ts";

/**
 * Klient TS jest GENEROWANY ze schematu FastAPI — nie edytuj `src/lib/api/generated/`.
 * Regeneracja: `pnpm --filter web generate:api` (najpierw `uv run dump-openapi` w backendzie).
 */
export default defineConfig({
  input: "../backend/openapi.json",
  // postProcess: [] — bez formatowania/lintowania generatora; Biome i tak pomija ten katalog.
  output: { path: "./src/lib/api/generated", postProcess: [] },
  plugins: [
    // baseUrl: false = adresy relatywne, czyli ten sam origin co front (cookie first-party).
    { name: "@hey-api/client-fetch", baseUrl: false },
    { name: "@tanstack/react-query", queryOptions: true },
  ],
});
