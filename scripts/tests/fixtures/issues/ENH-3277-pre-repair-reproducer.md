---
id: ENH-9814
title: Fixture — ENH-3277 pre-repair reproducer for Phase 7c (ENH-3280)
type: enhancement
status: open
priority: P3
decision_needed: false
---

# ENH-9814: Fixture — ENH-3277 pre-repair reproducer for Phase 7c (ENH-3280)

## Summary

Hand-authored reconstruction of ENH-3277's pre-repair state, per ENH-3280 Implementation
Step 4. No git revision (committed or abandoned) holds ENH-3277's original pre-repair text
— it was hand-repaired before this issue was verified — so this fixture is built from
ENH-3280's own quoted *Current Behavior* text rather than `git show`. Option A stands in
for ENH-3277's actual winning option; Option B stands in for its rejected `--raw` option.

## Proposed Solution

**Option A**: Read project config via the existing `ProjectConfig` accessor.

**Option B**: Read project config via `ll-config get --raw project.<key>`.

> **Selected:** Option A — the accessor already exists and needs no new CLI surface.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-21.

**Selected**: Option A

**Reasoning**: The `ProjectConfig` accessor already covers every call site; `--raw` would
add a second read path for no behavioral gain.

## Program Design

**Recommendation: Option B.** Reads should go through `ll-config get --raw project.<key>`.

### Signatures

- `ll-config get --raw project.<key>` — new CLI surface Option B would add, invoked from
  every call site instead of the existing accessor. (A brand-new identifier introduced only
  here, never named inside Option B's own block, would be outside Phase 7c's detector-driven
  candidate list by design -- see Proposed Solution § *Input* in ENH-3280 — so this fixture
  deliberately reuses Option B's own identifier rather than inventing a new one.)

## Implementation Steps

1. *If Option B is taken*, the following elsewhere in this issue change and must be
   updated in the same pass: every call site's read path, the Program Design Signatures
   above, and the Scope Boundaries note below.
2. Under the recommended **Option B** they become genuine drop-ins via
   `ll-config get --raw project.<key>`, which must land before either YAML is touched.

## Scope Boundaries

- No new production code — **conditional on the *DECISION REQUIRED* outcome**.

## Status

**Open** | Created: 2026-08-23 | Priority: P3
