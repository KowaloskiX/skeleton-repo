---
description: Remove AI-generated slop from recent changes — redundant comments, defensive code that does not match the area, casts that dodge the type system. Use after a large generated change or before opening a PR.
argument-hint: [scope, e.g. "the last commit" or a path]
---

# Deslop

$ARGUMENTS — if no scope is given, review the working tree plus the last commit.

Remove what a careful author of *this* codebase would not have written:

- **Comments that restate the code.** A comment here earns its place by explaining *why*, a
  measurement, or a trap. `# increment the counter` does not.
- **Defensive code that does not match the area.** A `try/except` around a call that cannot
  fail, or a null check on a value the type system already guarantees. Trusted, validated call
  paths do not need belt and braces.
- **Casts and suppressions that dodge the type system**: `as any`, `# type: ignore` without a
  justification, `@ts-expect-error`, `# noqa` on something that should simply be fixed. This
  repository has exactly one suppression, and it carries a paragraph explaining why.
- **Style inconsistent with the file.** Match the surrounding density of comments, naming and
  idiom rather than importing a different house style.
- **Dead code and commented-out blocks.** Git remembers them.

Do not remove:

- comments recording a measurement, a defect or a deliberate trade-off — those are the ones
  worth keeping,
- tests that look redundant but are negative or positive controls.

Afterwards run the gates (`/run-checks` or the skill of that name) and report in one to three
sentences what you removed.
