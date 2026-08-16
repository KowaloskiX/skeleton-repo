import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Ports come from the environment, because 3000/8000 are often taken by another project on
// the same machine. The same pair drives Playwright (see playwright.config.ts).
const WEB_PORT = Number(process.env.WEB_PORT ?? 3000);
const API_PORT = Number(process.env.API_PORT ?? 8000);
const API_PROXY = { "/api": { target: `http://localhost:${API_PORT}`, changeOrigin: true } };

export default defineConfig({
  // The alias has to live here, not only in tsconfig: tsc understands it, the SSR dev server
  // does not.
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // Backend on the same origin: /api -> FastAPI (first-party cookie).
  // `preview` needs its own proxy — it does not inherit from `server`, and without it a
  // preview of the production build gets a 404 on every API call.
  server: { port: WEB_PORT, proxy: API_PROXY },
  preview: { port: WEB_PORT, proxy: API_PROXY },
  plugins: [
    tailwindcss(),
    tanstackStart(),
    // The React plugin must come AFTER the Start plugin.
    viteReact(),
  ],
});
