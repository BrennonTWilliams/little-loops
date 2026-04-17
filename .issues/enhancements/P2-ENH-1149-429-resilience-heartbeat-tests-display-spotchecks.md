---
id: ENH-1149
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1145
related: [ENH-1144, ENH-1145, ENH-1147, ENH-1148]
size: Small
confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1149: 429 Resilience — Heartbeat Tests: Display, Spot-checks & Conditional

## Summary

Add the `rate_limit_waiting` negative-edge assertion to `test_ll_loop_display.py`, spot-check all rate-limit-adjacent test files for regressions introduced by ENH-1144, and apply conditional updates to `test_config.py` / `test_config_schema.py` if the color key was added.

## Parent Issue

Decomposed from ENH-1145: 429 Resilience — Heartbeat Tests

## Depends On

- ENH-1144 — executor changes must be present to run spot-checks meaningfully

## Expected Behavior

### 1. `test_ll_loop_display.py` — negative-edge assertion (Step 6 of parent)

In the `_collect_edges`-oriented test block at lines 2408-2421, add:

```python
def test_collect_edges_excludes_rate_limit_waiting(self):
    # rate_limit_waiting is event-only, not a routed edge
    fsm = FSM(max_rate_limit_retries=3, on_rate_limit_exhausted="b", ...)
    edges = _collect_edges(fsm)
    assert not any(label == "rate_limit_waiting" for _, _, label in edges)
```

Use `max_rate_limit_retries=3` and `on_rate_limit_exhausted="b"` (same fixture as `test_collect_edges_includes_on_rate_limit_exhausted` at `:2408-2421`). This is the first absence assertion in this suite — the pattern `assert not any(...)` is intentional.

### 2. Spot-check test files

Run each file and confirm it passes. No structural changes expected — these are regression guards:

- `scripts/tests/test_ll_loop_execution.py`
- `scripts/tests/test_ll_loop_state.py`
- `scripts/tests/test_rate_limit_circuit.py`
- `scripts/tests/test_fsm_persistence.py`
- `scripts/tests/test_fsm_fragments.py`
- `scripts/tests/test_fsm_schema.py`
- `scripts/tests/test_fsm_validation.py`
- `scripts/tests/test_enh1138_doc_wiring.py`
- `scripts/tests/test_circuit_breaker_doc_wiring.py`
- `scripts/tests/test_cli_loop_lifecycle.py`
- `scripts/tests/test_builtin_loops.py`

### 3. Conditional: `test_config.py` and `test_config_schema.py`

**Only apply if ENH-1144 added a `rate_limit_waiting` color key** to `CliColorsEdgeLabelsConfig`.

`test_config.py:1353-1363` — `TestCliColorsEdgeLabelsConfig.test_defaults`:
- Add assertion for `rate_limit_waiting` default color immediately after the existing `rate_limit_exhausted == "38;5;214"` at `:1363`

`test_config_schema.py` (63 lines, no existing `fsm_edge_labels` assertions):
- Add a new test case validating `rate_limit_waiting` color key in schema, following the `rate_limit_exhausted` pattern

## Integration Map

### Files to Modify
- `scripts/tests/test_ll_loop_display.py` (assertion addition after `:2421`)
- (Conditional) `scripts/tests/test_config.py:1353-1363`
- (Conditional) `scripts/tests/test_config_schema.py` (no existing `fsm_edge_labels` assertions — new test case)

### Files to Spot-check (run only)
- `scripts/tests/test_ll_loop_execution.py`
- `scripts/tests/test_ll_loop_state.py`
- `scripts/tests/test_rate_limit_circuit.py`
- `scripts/tests/test_fsm_persistence.py`
- `scripts/tests/test_fsm_fragments.py`
- `scripts/tests/test_fsm_schema.py`
- `scripts/tests/test_fsm_validation.py`
- `scripts/tests/test_enh1138_doc_wiring.py`
- `scripts/tests/test_circuit_breaker_doc_wiring.py`
- `scripts/tests/test_cli_loop_lifecycle.py`
- `scripts/tests/test_builtin_loops.py`
- `scripts/tests/test_fsm_executor.py` — primary executor test suite; covers `rate_limit_exhausted` event emission and routing at lines 4318-4814; ENH-1144 executor changes could surface regressions here [_Wiring pass added by `/ll:wire-issue`_]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:481-491` — `BRConfig.to_dict()` manually enumerates all `CliColorsEdgeLabelsConfig` fields inline (not via the dataclass's `to_dict()`). If ENH-1144 adds a `rate_limit_waiting` field to `CliColorsEdgeLabelsConfig`, this block must also gain an entry — verify ENH-1144 covered it before applying the conditional test updates.

### Source References
- `_collect_edges` defined at `scripts/little_loops/cli/loop/layout.py:188-215`, signature `def _collect_edges(fsm: FSMLoop) -> list[tuple[str, str, str]]`. Emits labels: `yes`, `no`, `error`, `partial`, `blocked`, `retry_exhausted`, `rate_limit_exhausted`, `next`, route verdicts, `_` (route default), extra-route keys. The string `rate_limit_waiting` is **not** present — confirming it's event-only.
- `CliColorsEdgeLabelsConfig` at `scripts/little_loops/config/cli.py:76-102` — 9 fields: `yes`, `no`, `error`, `partial`, `next`, `default`, `blocked`, `retry_exhausted`, `rate_limit_exhausted`. **No `rate_limit_waiting` field as of 2026-04-17.**

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-04-17:_

- **Fixture correction:** The draft code in "Expected Behavior #1" uses `FSM(max_rate_limit_retries=3, on_rate_limit_exhausted="b", ...)`. The actual pattern at `test_ll_loop_display.py:2408-2421` uses the test-class helper `self._make_fsm(states={...})` with `StateConfig` entries. Mirror that helper; do not instantiate `FSM` directly. Example shape:
  ```python
  fsm = self._make_fsm(
      states={
          "a": StateConfig(action="step", max_rate_limit_retries=3, on_rate_limit_exhausted="b"),
          "b": StateConfig(terminal=True),
      }
  )
  edges = _collect_edges(fsm)
  assert not any(label == "rate_limit_waiting" for _, _, label in edges)
  ```
- **Absence-assertion novelty confirmed:** `grep "not any"` in `test_ll_loop_display.py` returns zero hits. This will be the first absence assertion in the `_collect_edges` suite — add a brief comment explaining intent.
- **Conditional branch status (2026-04-17):** `rate_limit_waiting` has zero matches across `scripts/**` (source and tests). ENH-1144 has not added a color key, and `rate_limit_waiting` is not emitted as an event anywhere (`executor.py` emits only `rate_limit_exhausted` at `:1001` and `rate_limit_storm` at `~:1023`). The conditional updates to `test_config.py` and `test_config_schema.py` therefore DO NOT apply at time of writing — verify by running `grep -n "rate_limit_waiting" scripts/little_loops/config/cli.py` in Step 1 before branching.
- **test_config_schema.py structure:** 64 lines, four tests validating schema-level properties (block existence, `additionalProperties`, `type`, scalar defaults). No tests currently validate individual color keys. If the conditional applies, add a new test case following the existing schema-navigation pattern: `data["properties"]["commands"]["properties"]["rate_limits"]["properties"]...`.
- **Existing `rate_limit_exhausted` coverage** (for spot-check sanity): `test_fsm_fragments.py:649,661`, `test_fsm_schema.py:527-612`, `test_fsm_validation.py:70-159`, `test_builtin_loops.py:1098,1101`, `test_fsm_executor.py:4318-4814`. Regressions here would most likely surface in these files.

## Implementation Steps

1. Check if ENH-1144 added `rate_limit_waiting` to `CliColorsEdgeLabelsConfig`: `grep -n "rate_limit_waiting" scripts/little_loops/config/cli.py`
2. Add negative-edge assertion to `test_ll_loop_display.py` (lines 2408-2421 area)
3. Run spot-check suite:
   ```bash
   python -m pytest scripts/tests/test_ll_loop_execution.py \
     scripts/tests/test_ll_loop_state.py \
     scripts/tests/test_rate_limit_circuit.py \
     scripts/tests/test_fsm_persistence.py \
     scripts/tests/test_fsm_fragments.py \
     scripts/tests/test_fsm_schema.py \
     scripts/tests/test_fsm_validation.py \
     scripts/tests/test_enh1138_doc_wiring.py \
     scripts/tests/test_circuit_breaker_doc_wiring.py \
     scripts/tests/test_cli_loop_lifecycle.py \
     scripts/tests/test_builtin_loops.py \
     scripts/tests/test_fsm_executor.py -v
   ```
4. (Conditional) If color key exists, add assertions to `test_config.py` and `test_config_schema.py`
5. Run full expanded suite per ENH-1145 Step 9

## Acceptance Criteria

- `test_ll_loop_display.py` asserts `rate_limit_waiting` is not in collected edges — test passes
- All 11 spot-check files pass with no regressions
- (Conditional) If color key exists: `test_config.py` and `test_config_schema.py` have passing assertions for `rate_limit_waiting`

## Session Log
- `/ll:refine-issue` - 2026-04-17T08:31:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f251cbb-bdbf-46f1-9afb-74de9598acdb.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/714a7073-85c4-4a11-87ff-d55b6cd3eeba.jsonl`
- `/ll:wire-issue` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/767d1ea4-e340-45cf-b84a-5cd330c9af1e.jsonl`

---

## Status
- [ ] Open
