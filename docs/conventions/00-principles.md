# General principles and design

Language-independent foundations. The goal: code that is easy to understand, change and test,
and that ages slowly.

## SOLID (practically, not academically)

**S — Single Responsibility.** A unit has one reason to change. A `UserRegistration` service
does not also send emails and record metrics — it delegates those to collaborators. The test:
can you describe what it does without the word "and"?

**O — Open/Closed.** Extend by adding, not by modifying. A new AI provider means a new adapter,
not `if provider == "openai": ... elif ...` inside the logic. We get there through interfaces
(ports).

**L — Liskov Substitution.** A port implementation must work everywhere the port is expected —
with no surprises (an adapter must not suddenly raise an exception the port does not describe,
nor return `None` where the contract says "a list").

**I — Interface Segregation.** Narrow, dedicated interfaces instead of one god interface.
`ChatModel` and `EmbeddingModel` separately — an embeddings consumer must not depend on chat
methods.

**D — Dependency Inversion.** High layers (the domain) depend on abstractions, not on details
(database, HTTP, SDKs). Details are injected. This is the heart of testability.

## DRY, KISS, YAGNI

- **DRY** — one business rule in one place. But careful: *accidental* similarity is not
  duplication — do not abstract two things merely because they look alike today (premature
  abstraction hurts more than duplication).
- **KISS** — the simplest solution that works. Wisdom is not complexity.
- **YAGNI** — do not build for hypothetical requirements. **A deliberate exception:** we put
  seams (ports) where change is nearly certain — AI/LLM, payments, auth providers. That does
  not break YAGNI, because the seam is cheap and the change is real.

## Composition over inheritance

By default, compose behaviour from small collaborators instead of building class hierarchies.
Inheritance only for a genuine, stable "is-a" relationship. Deep hierarchies mean brittleness.

## Layer separation (hexagonal / ports and adapters)

Three rings, dependencies pointing **inwards**:

```
  Infrastructure (DB, HTTP, SDKs, queues)   <- adapters
        │  implements ports
  Application / services (use cases)        <- orchestration, transactions
        │  calls ports (interfaces)
  Domain (entities, rules, types, ports)    <- pure, no framework imports
```

- The **domain** imports neither FastAPI, Beanie/PyMongo, LiteLLM nor TanStack — nothing from
  the edge.
- **Ports** (interfaces) are defined by the domain/application; **adapters** in infrastructure
  satisfy them.
- A **router/controller** translates HTTP into a service call and nothing more.

The effect: swapping the database, the AI provider or the web framework is an adapter
replacement rather than open-heart surgery.

## Error handling — explicitly

Distinguish:

- **Expected / domain errors** (validation, "not found", "insufficient funds") -> part of the
  contract. In Python: dedicated domain exceptions caught centrally and mapped onto responses,
  **or** a result type. In TS: `Result<T,E>` (`neverthrow`) at the boundaries.
- **Exceptional errors** (the database died, a bug) -> an exception -> a global handler -> log
  + 500 + alert. Do not swallow them quietly.

Rules: never `except Exception: pass`; do not use exceptions for normal control flow; an error
message says *what* and *why*, without leaking internal details to the client.

## Naming and readability

- Names reveal intent: `active_subscriptions`, not `data`. Functions are verbs, collections are
  plural.
- A function fits on a screen and stays at one level of abstraction. Nesting depth <= 2–3;
  deeper means extracting a function.
- No magic numbers — named constants. No commented-out code (that is what git is for).
- A comment explains *why*, not *what* (the code says what).

## The boy scout rule

Leave the code cleaner than you found it. Small, continuous improvements beat a grand
"refactor next month".
