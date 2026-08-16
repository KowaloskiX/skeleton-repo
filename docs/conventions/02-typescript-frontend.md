# TypeScript / frontend — conventions

TanStack Start, TS `strict`, Tailwind v4 + shadcn/ui. Lint/format: **Biome**. The API client is
generated from OpenAPI.

## TypeScript

- `strict: true` **plus** `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  `noImplicitReturns`, `noUnusedLocals/Parameters`, `moduleResolution: NodeNext`.
- **No `any`.** When a type is unknown -> `unknown` plus narrowing. `as` (an assertion) only
  exceptionally and with a comment.
- Prefer `type` for composition and `interface` for extensible object contracts — stick to one
  convention per module.
- Derive types rather than writing them by hand: `z.infer<typeof schema>`, types from the
  generated API client.
- Enums -> literal unions (`type Role = "user" | "admin"`) instead of `enum`. Categorical values
  (status, kind, source…) **always** as literal unions, never a bare `string`. Define the type
  once and import it.

## Module boundaries — enforced in CI

A feature does not reach into another feature's internals; shared things go through the public
surface. This rule is **enforced**, not merely described:

- **dependency-cruiser** with rules: `features/*` do not import each other by internal paths;
  imports go through the public `index.ts` only; no cycles.
- It is the counterpart of the backend's `import-linter` (see
  `05-architecture-enforcement.md`).

## Validation: Zod

- Validate everything that comes from outside: forms, URL parameters, data from `localStorage`,
  responses from outside the generated client.
- A Zod schema is one source: the type (`z.infer`) and the validation come from one place.
- Forms: React Hook Form + `zodResolver`. Business rules live in the schema, not scattered
  through JSX.

## State split — a hard rule

| Kind of state | Tool | Examples |
|---|---|---|
| **Server state** (data from the API) | **TanStack Query** | lists, entities, mutations, cache, refetch |
| **Client/UI state** (ephemeral) | **Zustand** | open sidebar, dark mode, modal state, wizard steps |
| **URL state** | the router (search params/loaders) | filters, pagination, active tab |
| **Local component state** | `useState` | an input, hover, a local toggle |

Do not keep server data in Zustand. Do not replicate URL state in Zustand. If state can be
derived, derive it rather than store it.

## The API client (OpenAPI)

- `frontend/src/lib/api/generated/` is **generated** (`@hey-api/openapi-ts`) — **do not edit by
  hand**, do not commit finger-made changes. Consume it only through `lib/api/index.ts`
  (enforced by dependency-cruiser).
- Regenerate after every API change; CI watches for drift.
- API calls always go through the generated TanStack Query hooks, never a raw `fetch`.

## Components

- **Feature-first:** `src/features/<area>/`. Inside: `index.ts` (the only public surface),
  `queries.ts`, `mutations.ts`, `schema.ts`, components and tests next to the code. Shared,
  "dumb" primitives -> `src/components/ui/`. Full map and rationale:
  [`frontend/CLAUDE.md`](../../frontend/CLAUDE.md).
- **The file name is the name of what it exports** (kebab-case), and files are named after
  their contents rather than a hook kind (`queries.ts`, not `use-session.ts`).
- **No global (product) `components/`, `hooks/`, `utils/` or `contexts/`.** They duplicate the
  feature split and after a year describe the same code under two conflicting layouts. A UI
  store lives in the feature it belongs to.
- Presentational components (no data logic) stay separate from containers (fetching/mutations).
  A presentational component receives props; it does not call the API.
- Small and focused; when props exceed ~5 or a component exceeds ~150 lines, split it.
- Custom hooks for reusable logic (`useX`). Minimize effects (`useEffect`) — most "effects" are
  derived data or events.
- Accessibility: semantic elements, `aria-*`, keyboard and focus handling (shadcn/Radix helps,
  but verify).

## Styling (Tailwind v4 + shadcn/ui)

- Tokens (colours, spacing, typography) live in the `@theme` layer — do not hardcode values in
  ad hoc classes.
- Component variants through `cva`/the shadcn pattern; class merging through `cn()`
  (clsx + tailwind-merge).
- Dark mode from day one; do not assume a single theme.

## What we do not do

- `any`, `@ts-ignore` without a comment, `as` used to silence types.
- Editing the generated API client by hand.
- Server data in Zustand, or `useEffect` for fetching (that is what TanStack Query is for).
- `localStorage`/`sessionStorage` for sensitive data (tokens) — auth goes through an `HttpOnly`
  cookie.
- Business logic on the frontend — it lives on the backend.
