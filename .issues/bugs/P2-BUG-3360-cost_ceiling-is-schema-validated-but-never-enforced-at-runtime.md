---
id: BUG-3360
type: BUG
title: cost_ceiling is schema-validated but never enforced at runtime
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-30'
captured_at: '2026-08-30T04:51:19Z'
labels:
- fsm
- loops
- dead-code
---

# BUG-3360: cost_ceiling is schema-validated but never enforced at runtime

## Summary

`StateConfig.cost_ceiling` (ENH-2477) is a fully-plumbed dataclass with
serialization and validation, but **no runtime consumer**. A loop author can
declare a per-state USD spend cap, `ll-loop validate` reports the loop as
valid, and the cap is never checked during the run. The knob is a silent no-op
that reads as spend protection.

Its documented companion — FEAT-2476's global `--max-cost` accumulator, which
`CostCeilingConfig`'s own docstring says it "composes with"
(`fsm/schema.py:401`) — was **cancelled**, so the enforcement half of the
design never landed on either side.

## Current Behavior

`cost_ceiling` exists end-to-end on the config path:

| Site | Role |
|------|------|
| `fsm/schema.py:397-434` | `CostCeilingConfig` dataclass (`cost_ceiling_per_state`, `cost_warn_at`) + `to_dict`/`from_dict` |
| `fsm/schema.py:735` | `StateConfig.cost_ceiling` field |
| `fsm/schema.py:846-847` | serialized in `StateConfig.to_dict` |
| `fsm/schema.py:888-890,960` | deserialized in `StateConfig.from_dict` |
| `fsm/validation/structural_rules.py:755-757` | dispatch when present |
| `fsm/validation/structural_rules.py:762-831` | `_validate_state_cost_ceiling` — rejects negatives, warns on `cost_warn_at >= cost_ceiling_per_state` |
| `scripts/tests/test_fsm_validation_structural.py:702-769` | validation-only test coverage |

And nowhere on the execution path:

```
$ grep -rn "cost_ceiling" scripts/little_loops/fsm/executor.py
(no output)

$ grep -rn "cost_warn_at|\.cost_ceiling" scripts/little_loops/ scripts/tests/ \
    | grep -v "schema.py|structural_rules.py"
scripts/tests/test_fsm_validation_structural.py: ...   # validation tests only
```

Reproduced against a minimal loop declaring both keys on a shell state:

```yaml
states:
  work:
    action: "echo hi"
    action_type: shell
    cost_ceiling:
      cost_ceiling_per_state: 1.0
      cost_warn_at: 0.5
    next: done
```

`ll-loop validate` → `is valid`. No warning that the ceiling is inert.

Two aggravating details:

1. **`cost_ceiling` is absent from `fsm-loop-schema.json`.** It is not among
   the 45 properties of `/definitions/stateConfig`, which declares
   `additionalProperties: false`. The dataclass path accepts it anyway, so the
   JSON schema and the dataclass schema disagree about whether the key exists
   at all.
2. **The data needed to enforce it is already being written live.**
   `PersistentExecutor._handle_event()` appends a per-`action_complete` row —
   `state`, `iteration`, `input_tokens`, `output_tokens`, cache tokens,
   `model` — to `<run_dir>/usage.jsonl` at `fsm/persistence.py:1008-1036`, and
   `fsm/cost_graph.py` already aggregates those rows into `PerStateCost` with
   `estimate_cost_usd`. Only the in-run comparison and route are missing.

(Note: `cost_graph.py`'s module docstring cites this writer at
`fsm/persistence.py:637-655`; the real site is `:1008-1036`. Worth refreshing
while in the area.)

## Expected Behavior

One of:

- **Enforce it.** After each state visit, sum that visit's cost from the rows
  already being appended to `usage.jsonl` and compare against
  `cost_ceiling_per_state`; emit a warning at `cost_warn_at`; route or abort on
  breach, following `host_guard.py`'s existing
  `on_budget_exceeded`/`budget_state` shape (`fsm/host_guard.py:68-82`,
  routed at `fsm/executor.py:795-800`). This also requires adding
  `cost_ceiling` to `/definitions/stateConfig` in `fsm-loop-schema.json` so the
  two schemas agree.
- **Remove it.** Drop `CostCeilingConfig`, the `StateConfig` field, the
  validation branch, and the validation tests. Per-state cost stays observable
  after the fact via `cost_graph.py` / `/ll:debug-loop-run`, which is what it
  is actually used for today.

Either is acceptable; what is not acceptable is a validated-but-inert spend
cap. If enforcement is chosen, settle the naming collision flagged on
EPIC-3022 first: EPIC-3041's FEAT-3038/FEAT-3039 independently add a second
"route on running out of X" shape to the same FSM layer, and
`fsm-loop-schema.json` should not grow two divergent conventions.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — per-state-visit cost check + route (enforce path)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `cost_ceiling` to `/definitions/stateConfig` (enforce path)
- `scripts/little_loops/fsm/schema.py:397-434,735,846-847,888-890,960` — `CostCeilingConfig` (removal path)
- `scripts/little_loops/fsm/validation/structural_rules.py:755-831` — validation branch (removal path)
- `scripts/little_loops/fsm/cost_graph.py` — refresh the stale `persistence.py:637-655` docstring citation → `:1008-1036`

### Similar Patterns
- `scripts/little_loops/fsm/host_guard.py:68-82` + `fsm/executor.py:795-800` — the `on_budget_exceeded`/`budget_state` route shape to mirror
- `scripts/little_loops/fsm/cost_graph.py` — existing `usage.jsonl` → `PerStateCost` aggregation to reuse

### Tests
- `scripts/tests/test_fsm_validation_structural.py:702-769` — extend with a runtime-enforcement case, or delete with the removal

## Impact

- **Priority**: P2 — no crash or data loss, but a safety knob that reports
  valid and does nothing is worse than an absent one: an author who sets
  `cost_ceiling_per_state: 5.0` on an expensive state reasonably believes spend
  is bounded, and it is not.
- **Effort**: Small either way. Removal is mechanical. Enforcement is one
  executor check plus a JSON-schema entry, reusing `cost_graph.py`'s existing
  aggregation and `host_guard.py`'s existing route shape.
- **Risk**: Low. No loop in this repo declares `cost_ceiling` today, so neither
  path changes existing behavior.
- **Breaking Change**: Removal breaks any out-of-repo loop that declares the
  key — but only by rejecting a key that never did anything.

## Root Cause

ENH-2477 ("F6 (finishes) — Per-state cost attribution: stable JSON + per-state
ceilings", done 2026-07-07) delivered the attribution half — `usage.jsonl`,
`cost_graph.py`, the stable JSON shape — and landed the ceiling **schema** as
the declarative surface for FEAT-2476 to enforce. FEAT-2476 ("F2 — `--max-cost`
accumulator + 80%/100% guard") was subsequently cancelled, orphaning the
schema. Nothing failed loudly because a config key with no reader raises no
error, and the validation tests pass regardless.

## Status

**Open** | Created: 2026-08-30 | Priority: P2
