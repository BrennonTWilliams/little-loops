---
id: ENH-2234
type: ENH
priority: P4
status: deferred
discovered_date: '2026-06-19'
discovered_by: capture-issue
captured_at: '2026-06-19T21:56:31Z'
decision_needed: false
depends_on:
- ENH-2164
blocked_by:
- ENH-2164
relates_to:
- ENH-2164
- ENH-2233
- EPIC-2167
---

# ENH-2234: Pluggable operator registry for the decision-table matcher

## Summary

Once the general decision-table engine (`lib/policy-router`, ENH-2164) ships with its
fixed comparison vocabulary (`>=, <=, ==, !=, <, >`, plus range/membership as built),
allow third parties and extensions to **register custom comparison operators** —
e.g. `semver_gte`, `age_within`, `path_glob`, domain-specific matchers — by mirroring
the existing FSM **evaluator registry** pattern. This is the deepest tier of
generalization and is **intentionally deferred** until there is demonstrated demand for
domain-specific comparators beyond the built-in set.

## Motivation

ENH-2164's rule grammar (`dim:op:value -> state`) has a closed operator set. That covers
the overwhelming majority of routing decisions (numeric thresholds, ranges, membership,
equality). But some domains want comparators the core can't reasonably ship:

- version routing (`engine:semver_gte:2.4 -> upgrade_path`)
- time-window routing (`last_seen:age_within:7d -> active`)
- path/glob routing (`changed_file:path_glob:src/** -> deep_review`)

Hard-coding every such operator into the engine bloats it and never converges. A
registry lets the comparator vocabulary grow **out-of-tree**, the same way the FSM
already lets evaluators be discovered rather than enumerated.

## Why Deferred

Per EPIC-2167's "prove before mandate" discipline: do not build the extensibility layer
until the fixed vocabulary is shipped (ENH-2164) **and** a real loop needs an operator
the core doesn't provide. Premature plugin surfaces are a maintenance liability with no
proven caller. Promote to `open` when a concrete loop requirement for a non-built-in
operator appears.

## Expected Behavior (sketch — refine on un-defer)

- An operator registry keyed by name, seeded with the built-in comparators, mirroring
  the evaluator dispatch in `scripts/little_loops/fsm/evaluators.py`.
- Extensions register `(name, fn)` where `fn(lhs_value, rhs_literal) -> bool`, discovered
  via the same entry-point mechanism extensions already use (`ll-create-extension`).
- The policy-rule parser resolves unknown operator tokens against the registry before
  erroring; a registered operator name is usable directly in `context.policy_rules`.
- `ll-loop validate` reports an unresolved operator token as an error with the list of
  available (built-in + registered) operators.

## Scope Boundaries

- **In scope** (when un-deferred): operator registry + dispatch; entry-point discovery
  for extension-supplied operators; parser/validator integration; docs + a worked example
- **Out of scope**: the built-in vocabulary itself (ENH-2164); the edit-routes lens
  (ENH-2233 — though it would need to render custom-operator cells as opaque strings);
  `expr:`-style free predicates (a separate escape-hatch design, noted on ENH-2164)

## Impact

- **Priority**: P4 — pure extensibility; no value until a non-built-in operator is needed
- **Effort**: Medium — registry + discovery + parser/validator wiring
- **Risk**: Low — additive; built-ins remain the default path
- **Breaking Change**: No

## Labels

`enh`, `loops`, `fsm`, `dx`, `routing`, `decision-table`, `extensibility`

## Status

**Deferred** | Created: 2026-06-19 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-06-19T21:56:31Z - `7ad4c299-a78e-4069-93e8-64dd478cf18b.jsonl`
