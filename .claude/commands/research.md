---
description: Document how a part of this codebase works today, with file and line references. Use for "how does X work", "where is Y handled", or before changing an area you have not touched.
argument-hint: [question, e.g. "how does session revocation work"]
---

# Research

$ARGUMENTS

Your only job is to **document what exists**. Not to improve it.

- Do NOT suggest changes, refactors or future enhancements unless explicitly asked.
- Do NOT critique the implementation.
- Describe what exists, where it lives, how it works, and how the pieces connect.

## Process

1. Read any file the question names — fully, no offset tricks.
2. Follow the layers rather than grepping blindly. This repository has a fixed shape:
   `routes` -> `services` -> `repositories` -> `models`, with `core/domain` at the bottom, and
   `features/<area>/` on the frontend. The answer usually spans exactly one vertical slice.
3. Check the contracts before assuming: `backend/.importlinter` and
   `frontend/.dependency-cruiser.cjs` state what may import what, so they tell you where logic
   *cannot* be.
4. Read the tests. In this repository they carry the reasoning — many docstrings record a
   measurement or a defect that motivated the code.

## Output

```markdown
# Research: [topic]

**Commit**: [hash]  **Branch**: [name]

## Question
[verbatim]

## Summary
[the answer in a few sentences]

## How it works
- [step, with `path/to/file.py:123`]

## Where the boundaries are
[which layer owns what, and which contract enforces it]

## Open questions
[what remains unclear — say so rather than guessing]
```

Prefer concrete `file:line` references over prose. If something is genuinely undocumented and
unclear from the code, say that instead of inventing an explanation.
