---
description: Write a post-mortem for a production incident. Use after an outage or a data problem, once the timeline and the fix are known.
argument-hint: [what happened]
---

# Post-mortem

$ARGUMENTS

Gather first: the timeline, what the users saw, the fix, and the evidence (logs, metrics, the
diff that introduced it). Every request carries an `X-Request-Id` that appears in both the
response body and the logs — start there when reconstructing a user report.

## Structure

### Root cause
Which component failed and why. When was that code last changed, and what triggered the failure
now. The chain from trigger to the symptom a user noticed. Why the existing safeguards — the
contracts, the tests, the probes — did not catch it.

### Resolution
The specific changes, immediate and follow-up. Name any temporary workaround still in place, so
it does not become permanent by forgetting.

### What went wrong beyond the bug
Systemic, not personal: missing alert, late detection (how long?), no fallback, a gap in the
tests or in the deployment. If the answer is "we found out from a user", say so.

### What we do differently
Each item as **Goal** (the problem it removes) and **How** (the concrete step). An item without
a How is a wish.

### Takeaway
Two to four bullets: what this revealed about the system, not about the incident.

## Style

- Numbers, not adjectives: "270 of 300 analyses" rather than "many".
- A regression test that reproduces the failure is part of the fix, not a follow-up.
- Focus on improvement, never on blame.
