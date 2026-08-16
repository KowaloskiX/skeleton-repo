# frontend — TanStack Start

## Running
```bash
pnpm install   # from the repo root
pnpm dev       # web on :3000, /api proxied -> FastAPI :8000
```

Ports are configurable: `WEB_PORT` and `API_PORT` (both read by `vite.config.ts` and
`playwright.config.ts`).

## Build and production preview
```bash
pnpm --filter web build     # dist/client + dist/server
pnpm --filter web preview   # SSR from the build on :3000
```

The target host is chosen in the CI/CD increment (Vercel/Netlify, or a Nitro preset for a
container) — which is why there is no `start` script here yet.

## Conventions
- `src/routeTree.gen.ts` is **generated** by the Start plugin (dev/build) and **committed**;
  CI checks for drift.
- Module boundaries are enforced by dependency-cruiser: `pnpm --filter web boundaries` (or
  `pnpm boundaries` from the root).
- State: server state -> TanStack Query, UI state -> Zustand.
- The generated OpenAPI client lives in `src/lib/api/generated/` — consumed only through
  `src/lib/api/index.ts`.
- Directory layout and the rules for where new code goes: [`CLAUDE.md`](CLAUDE.md).
