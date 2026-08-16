---
description: Strict maintainability review of a diff — abstraction quality, files that sprawl, conditionals grafted into unrelated flows. Use for a deep code quality review or a harsh pre-merge audit.
argument-hint: [scope, e.g. "against main" or a path]
disable-model-invocation: true
---

# Code review

$ARGUMENTS — if no scope is given, review `git diff main...HEAD`.

Be **ambitious about structure**. Do not stop at local cleanups: look for the restructuring that
makes whole branches, helpers and conditionals disappear. Prefer deleting complexity over
rearranging it. The best outcome is a change that looks inevitable in hindsight.

## What to flag

1. **A file crossing ~500 lines**, or growing towards it. Extract before it sprawls; this
   codebase has none that large and that is worth keeping.
2. **Ad-hoc conditionals grafted into unrelated flows.** A new `if` in a function that did not
   care about that concern is a design problem, not a nit. Push the logic into the layer that
   owns it.
3. **Logic in the wrong layer.** A route doing business logic, a service touching
   `Request`/`Response`, a query outside `repositories/`. The import contracts catch the import,
   not the smell — you have to catch the smell.
4. **Unnecessary optionality.** `X | None` that no caller can produce, a fallback papering over
   an unclear invariant. Make the boundary explicit instead.
5. **Suppressions and casts.** `any`, `type: ignore`, `noqa` — each has to be a real false
   positive with a written reason, or it is a bug waiting.
6. **Claims without evidence.** A comment saying something is faster or safer, with no
   measurement behind it. Either measure it or drop the claim.
7. **Tests that cannot fail.** A test asserting on a mock, or one whose subject could be deleted
   while it stays green. Check the important ones by mutation: break the code, confirm red.

## What not to flag

- Formatting — Biome and Ruff own that.
- Anything a contract already enforces and that currently passes.
- Personal style preferences that the file does not already follow.

## Output

Findings ordered by severity, each with `file:line`, the concrete failure it enables, and the
smallest change that fixes it. If a restructuring would remove a whole class of the findings,
lead with that instead of listing them one by one.
