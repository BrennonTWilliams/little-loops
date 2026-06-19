---
id: ENH-2233
type: ENH
priority: P3
status: open
discovered_date: '2026-06-19'
discovered_by: capture-issue
captured_at: '2026-06-19T21:56:31Z'
decision_needed: false
depends_on:
- ENH-2164
relates_to:
- ENH-2164
- ENH-2227
- ENH-2228
- EPIC-2167
---

# ENH-2233: edit-routes — render and edit compound (multi-dimension) decision tables

## Summary

`ll-loop edit-routes` renders routing as a **state × verdict** matrix only. It cannot
show or edit the **compound, multi-dimension decision tables** that `lib/policy-router`
(ENH-2164) expresses — where a routing decision depends on a *conjunction of scored
dimensions* (e.g. `confidence>=85 & outcome>=75 -> implement`). This issue adds a
decision-table lens to `edit-routes` that renders a policy-router rule table as a true
condition-columns × action grid and round-trips edits back to the loop's
`context.policy_rules`.

## Motivation

The original framing that surfaced this: a user wanted `edit-routes` to express
"if readiness is in range X **and** complexity is above threshold Y, route to refine."
That capability is exactly what ENH-2164's engine provides — but `edit-routes` is the
**only authoring surface most users touch**, and it deliberately scoped compound
conditions *out* (ENH-2227 § Scope Boundaries; ENH-2228 likewise). So today the
generalized engine, once built, has **no editing lens** — its rule table lives as a
newline-separated `context.policy_rules` string that must be hand-edited in raw YAML.

A decision-table view collapses an N-dimension policy table into one readable grid
(condition columns = dimensions, each row = one conjunctive rule, first-match-wins,
final column = action state). This makes gaps, shadowed rules (an earlier row that
masks a later one), and missing catch-alls visible at a glance — the same value
ENH-2227 delivered for the simpler verdict matrix.

## Current Behavior

- `ll-loop edit-routes <loop>` (shipped via ENH-2227, extended by ENH-2228) extracts
  `route:` / `on_*` / `extra_routes` across states and renders a state × verdict
  matrix. It has no awareness of `context.policy_rules` or the policy-router fragment.
- A loop using `lib/policy-router` (ENH-2164) carries its decision logic in a
  `context.policy_rules` string (`dim:op:value [& dim:op:value] -> state`, `* -> state`
  catch-all). `edit-routes` shows only the single `classify` dispatch state's verdict
  arms — not the rule table that actually drives the decision.

## Expected Behavior

When a loop imports `lib/policy-router` and defines `context.policy_rules`,
`ll-loop edit-routes <loop> --decision-table` (or auto-detected) renders a compound grid:

```
| #  | confidence | outcome | security | aggregate | → action     |
|----|------------|---------|----------|-----------|--------------|
| 1  | —          | —       | <65      | —         | escalate     |
| 2  | >=85       | >=75    | —        | —         | implement    |
| 3  | —          | —       | —        | >=85      | done         |
| 4  | —          | —       | —        | >=60      | light_repair |
| 5  | *          | *       | *        | *         | deep_repair  |
```

1. Parse `context.policy_rules` into rows; the column set is the union of dimensions
   referenced across all rules (plus `aggregate`). Empty cell = dimension unconstrained
   in that rule (rendered `—`); `*` row = catch-all.
2. Edit in `$EDITOR` / CSV / markdown, mirroring ENH-2227's flow.
3. On save, serialize the grid back to the `dim:op:value & ... -> state` rule syntax and
   write it to `context.policy_rules`, preserving rule order (first-match-wins is
   order-sensitive — order must round-trip exactly).
4. Validation: every action-state column value must name a real state; warn on
   shadowed rows (a row whose conditions are a superset-match of an earlier row → never
   reached) and on a missing catch-all.

### Numeric/typed cells

Condition cells carry an operator + value (`>=85`, `<65`, `in[hot,warm]`). Rendering
and parsing must treat numeric comparisons numerically (see ENH-2164 typed-coercion
note) so a column sorts/validates correctly rather than lexically.

## Scope Boundaries

- **In scope**: detect/parse `context.policy_rules` for loops importing
  `lib/policy-router`; render compound condition-columns × action grid (markdown + CSV);
  `$EDITOR` round-trip back to `context.policy_rules` preserving rule order; shadowed-row
  + missing-catch-all + unknown-action-state warnings; reuse ENH-2227's extractor/
  renderer/parser/applier scaffolding in `route_table.py`
- **Out of scope**: the engine itself (ENH-2164); changes to the rule grammar
  (`|`-disjunction, nested booleans — still author multiple rows for OR); the simple
  state × verdict matrix path (unchanged, this is an additional mode); a visual/TUI
  diagram; runtime route injection (cancelled ENH-2226); pluggable operators (ENH-2234)

## API/Interface

```
ll-loop edit-routes <loop-name> [--decision-table] [--format markdown|csv] [--dry-run]
```

- `--decision-table` forces the compound-table lens; without it, auto-detect when the
  loop imports `lib/policy-router` and defines `context.policy_rules`, else fall back to
  the existing state × verdict matrix.
- Reuses `RouteTableExtractor` / `RouteTableRenderer` / `RouteTableParser` /
  `RouteTableApplier` in `scripts/little_loops/cli/loop/edit_routes.py` +
  `fsm/route_table.py`, adding a policy-rule extractor/serializer alongside them.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/edit_routes.py` — add `--decision-table` mode + auto-detect
- `scripts/little_loops/fsm/route_table.py` — policy-rule extractor + grid renderer + serializer
- `scripts/tests/test_ll_loop_edit_routes.py` — round-trip tests for compound tables

### Dependencies
- **ENH-2164** (`lib/policy-router.yaml`) — defines the `context.policy_rules` grammar
  this lens reads/writes; **must land first** (this issue is its authoring surface)

### Similar Patterns
- ENH-2227 / ENH-2228 — the existing `edit-routes` extractor/renderer/parser/applier to extend

## Impact

- **Priority**: P3 — unlocks the user-facing value of ENH-2164 (most users only touch `edit-routes`)
- **Effort**: Medium — extends an existing round-trip tool; main work is the grid serializer + order-preserving write-back
- **Risk**: Low-Medium — round-trip fidelity of an order-sensitive rule list is the main correctness concern
- **Breaking Change**: No — additive mode; existing verdict-matrix behavior unchanged

## Labels

`enh`, `loops`, `fsm`, `dx`, `routing`, `decision-table`

## Status

**Open** | Created: 2026-06-19 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-19T21:56:31Z - `7ad4c299-a78e-4069-93e8-64dd478cf18b.jsonl`
