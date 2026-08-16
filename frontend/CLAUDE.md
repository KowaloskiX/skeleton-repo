# CLAUDE.md — frontend

Local detail for `frontend/` on top of the root ([`../CLAUDE.md`](../CLAUDE.md)). Full rules:
[`../docs/conventions/02-typescript-frontend.md`](../docs/conventions/02-typescript-frontend.md).

## Directory map — where does this go

```
src/
  routes/            # ROUTES ONLY (TanStack file-based routing). Thin: they compose features.
  features/<name>/   # A product vertical. All the logic lives here.
  components/ui/     # Design primitives (shadcn). Stateless, no knowledge of the domain.
  lib/               # Shared technical bits: the API client, `cn`. No product logic here.
  styles/            # Tailwind plus the theme variables.
  router.tsx         # Router and QueryClient construction.
  start.ts           # The Start server: security headers for the HTML document.
tests/               # HARNESS ONLY (MSW, router render, setup). The tests sit next to the code.
e2e/                 # Playwright: a real browser against a real backend.
```

**"Where do I write this" has one answer:** can you name it as a product vertical (auth,
billing, theme)? Yes -> `features/<vertical>/`. No, because it is a button or an input with no
knowledge of the domain -> `components/ui/`. No, because it is technical plumbing (an HTTP
client, class merging) -> `lib/`.

## Inside a feature

```
features/auth/
  index.ts           # The public surface. The rest of the app imports from here ONLY.
  queries.ts         # Reads (TanStack Query): query options and `useX` hooks.
  mutations.ts       # Writes: mutation hooks together with cache invalidation.
  schema.ts          # Zod — form validation at the boundary.
  errors.ts          # Translating API errors into a message for a human.
  login-form.tsx     # The feature's components.
  login-form.test.tsx
```

The rules that hold this together:

1. **The file name is the name of what it exports** (kebab-case). `system-readout.tsx` exports
   `SystemReadout`. A file called `readout.tsx` containing `SystemReadout` is a riddle in
   `Ctrl+P`.
2. **Files are named after their contents, not after a hook kind.** `queries.ts` /
   `mutations.ts`, not `use-session.ts` / `use-auth-mutations.ts` — adding a second query then
   needs neither a new file nor a rename. The `use` prefix stays on the exported functions.
3. **Unit tests sit next to the code** (`login-form.test.tsx`). Moving a feature is then a
   single `git mv`, and a missing test is visible in the directory rather than in a second tree.
4. **Features talk to each other through `index.ts` only** — enforced by dependency-cruiser
   (`feature-isolation`). Importing `@/features/auth/queries` from another feature fails CI.
5. **`components/ui` imports neither `features/` nor `routes/`** — also enforced
   (`ui-kit-knows-nothing-about-features`). A component that needs the domain is not a design
   primitive and belongs in a feature.
6. **Server state is TanStack Query, UI state is Zustand.** Never the other way round and never
   both for the same piece of data. A UI store lives in the feature it belongs to
   (`features/theme/store.ts`), not in a global `stores/`.
7. **`lib/api/generated/` is generated** from `../backend/openapi.json` and never edited. We
   consume it through `lib/api/index.ts` (enforced: `generated-api-client-is-private`).

## What we deliberately do NOT do

- **No global `components/` for product components.** A directory called "all the components in
  the app" grows to hundreds of files and stops saying anything about the system — at which
  point `features/` and `components/` describe the same code under two conflicting divisions.
- **No parallel `lib/` + `utils/` + `helpers/`.** Three names for the same thing mean nobody
  knows where to look. There is `lib/`.
- **No global `hooks/`.** A hook belongs to a feature; if it really is shared by many, it goes
  to `lib/`.
- **No `contexts/` alongside `stores/`.** One mechanism for UI state: Zustand.

## Commands

| Goal | Command (from the repo root) |
|---|---|
| dev | `pnpm dev` (ports: `WEB_PORT`, `API_PORT`) |
| unit tests | `pnpm --filter web test` |
| E2E | `pnpm --filter web test:e2e` |
| module boundaries | `pnpm --filter web boundaries` |
| regenerate the API client | `pnpm --filter web generate:api` |
