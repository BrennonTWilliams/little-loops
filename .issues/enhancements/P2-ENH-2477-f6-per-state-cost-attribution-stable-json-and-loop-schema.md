---
id: ENH-2477
title: "F6 (finishes) — Per-state cost attribution: stable JSON + per-state ceilings"
type: ENH
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [FEAT-2476]
labels:
  - token-cost
  - cli
  - json-schema
  - fsm
  - tier-1
---

# ENH-2477: F6 (finishes) — Per-state cost attribution

## Summary

Finish the per-state cost table already partially built at
`scripts/little_loops/cli/loop/_helpers.py:1665–1690`: stabilize its JSON
schema, surface `cache_read` / `cache_creation` broken out (already in
the underlying `usage` aggregate), add a stable JSON output path for
downstream consumers, and add `cost_ceiling_per_state` /
`cost_warn_at` per-state keys to the loop YAML schema. This is
EPIC-2456 § Children [TBD-5].

## Motivation

EPIC-2456 Goal #2 names per-state spend as a first-class output, and
ENH-1797 (Cost / token telemetry per FSM state in loop runs) already
shipped the row layout. What's missing is (a) a **stable JSON schema**
that downstream consumers can parse without scraping the CLI table, and
(b) **per-state ceilings** that compose with FEAT-2476's `--max-cost`
ceiling. The loop YAML currently has no cost-shape field; downstream
tests that lock the JSON shape don't exist yet, so a v2 print rewrite
would silently break consumers.

## Current Behavior

- `scripts/little_loops/cli/loop/_helpers.py:1665–1690` prints a per-
  state cost table by reading `UsageEvent` rows from `history.db`.
- `scripts/little_loops/fsm/executor.py:1295–1305` already aggregates
  `cache_read_tokens` / `cache_creation_tokens` per state.
- The CLI prints a textual table; no stable JSON shape exists; no
  `cost_ceiling_per_state` field in the loop YAML schema.

## Expected Behavior

- `ll-loop run` emits a per-state cost summary as both (a) the existing
  human-readable table and (b) a stable JSON object — locked in tests
  so future rewrites don't silently break consumers.
- JSON keys exactly: `state`, `iterations`, `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`,
  `cost_usd`, `wallclock_ms`. Top-level `states: [...]` plus
  `totals: {...}`.
- Loop YAML schema gains `cost_ceiling_per_state: <float>` and
  `cost_warn_at: <float>` keys per state (composes with FEAT-2476's
  global ceiling).
- `ll-ctx-stats` can read the JSON output and surface per-state spend
  to humans.

## Proposed Solution

1. **`scripts/little_loops/fsm/cost_graph.py`** (new, ~50 LOC):
   - `PerStateCost.from_history(db_path)` — reconstructs per-state
     aggregates from `.ll/history.db` `usage_event` rows
   - `.to_dict()` — returns the stable JSON shape above
   - `.table()` — returns the existing human-readable column layout

2. **`scripts/little_loops/cli/loop/_helpers.py:1665–1690` extension**:
   - Replace the inline table builder with `PerStateCost.from_history`
   - Add `--cost-output-json <path>` flag for machine-readable output
   - JSON shape locked in `scripts/tests/test_cli_cost_table.py`

3. **`scripts/little_loops/fsm/schema.py`**: add
   `cost_ceiling_per_state` and `cost_warn_at` keys under each state
   block in the loop YAML schema. Validation rejects negative or
   non-numeric values.

4. **`scripts/little_loops/cli/ctx_stats.py`**: extend
   `cost_attribution()` query (already on the F5 roadmap) to break out
   per-state spend instead of just per-invocation.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/cost_graph.py` (new) — `PerStateCost`
- `scripts/little_loops/cli/loop/_helpers.py:1665–1690` — replace inline
- `scripts/little_loops/fsm/schema.py` — YAML schema additions
- `scripts/little_loops/cli/ctx_stats.py` — per-state readout
- `scripts/little_loops/fsm/executor.py:1295` — wire JSON emission

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/general-task.yaml`,
  `loops/deep-research.yaml` — opt into the new YAML fields
- `scripts/tests/test_cli_cost_table.py` (new) — JSON schema lock-in

### Similar Patterns

- `scripts/little_loops/fsm/validation.py` already returns typed
  outcomes that compose with budget primitives — reuse the pattern
- The JSON layout mirrors the format produced by ENH-2461's
  `input_tokens` / `output_tokens` / `cache_read_input_tokens` /
  `cache_creation_input_tokens` columns — keep consistent

### Tests

- `scripts/tests/test_cli_cost_table.py` (new) — JSON schema lock;
  refactor-safe across `_helpers.py` rewrites
- `scripts/tests/test_fsm_cost_graph.py` (new) — `PerStateCost.from_history`
  on a fixture DB round-trips through `.to_dict()`

### Documentation

- `docs/reference/API.md` — `fsm/cost_graph.py` + JSON schema doc
- `docs/ARCHITECTURE.md` — Token cost layer section (EPIC-2456 passes)
- `.ll/ll-config.json` — note the new YAML fields

### Configuration

- None added at the `ll-config` level; cost fields live in loop YAML
  (matches `model:` field convention)

## Implementation Steps

1. Add `cost_ceiling_per_state` / `cost_warn_at` to `fsm/schema.py`
2. Author `fsm/cost_graph.py` with `PerStateCost`
3. Replace the inline table builder at `_helpers.py:1665–1690` with
   `PerStateCost.from_history(...).table()`
4. Add `--cost-output-json <path>` flag to `ll-loop run`
5. Extend `cli/ctx_stats.py` to read per-state cost
6. Lock JSON schema in `scripts/tests/test_cli_cost_table.py`
7. Update loops (`general-task.yaml`, `deep-research.yaml`) to declare
   per-state ceilings for the most expensive states
8. Verify `python -m pytest scripts/tests/` exits 0

## Acceptance Criteria

- `ll-loop run --cost-output-json /tmp/per-state.json` emits JSON whose
  schema is locked by `scripts/tests/test_cli_cost_table.py`
- JSON breaks out `cache_read_tokens` / `cache_creation_tokens` and
  matches `usage_event` totals at run finish
- Loop YAML accepts `cost_ceiling_per_state` / `cost_warn_at` per state;
  validation rejects negative values
- Schema-version bump (if shape changes) is reflected in tests
- `python -m pytest scripts/tests/` exits 0

## Scope Boundaries

- **In**: Stable JSON shape; per-state YAML schema; CLI output flag;
  context-stats readout
- **Out**: OTel `gen_ai.usage.*` emission (F5 child owns that); cost
  ceiling guard (FEAT-2476 owns that); routing cascade (F7-lite)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Tier 1 [TBD-5], Goal #2 |
| `scripts/little_loops/cli/loop/_helpers.py:1665–1690` | Where the new builder plugs in |
| `FEAT-2476` | Sibling: composes per-state ceilings with the global `--max-cost` flag |
| `ENH-2461` | Persistence layer for the underlying `input_tokens` etc. |

## Impact

- **Priority**: P2 — finishes in-flight work; no new primitives, just
  stabilization
- **Effort**: Small — ~40–80 LOC across cost_graph + CLI flag + tests
- **Risk**: Low — additive JSON output; human-readable table preserved
- **Breaking Change**: No — existing CLI table output unchanged; new
  JSON is opt-in via flag

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
