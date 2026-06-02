---
id: ENH-1344
type: ENH
priority: P2

confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
size: Very Large
parent: ENH-1337
status: done
completed_at: 2026-05-10T00:00:00Z
---

# ENH-1344: Implement Per-Subtree Depth Limit in `recursive-refine`

## Summary

Implement the `max_depth` parameter for `recursive-refine` that tracks each issue's distance from a root and short-circuits further size-review decomposition once the cap is exceeded. Covers all code changes: YAML FSM states, config schema, Python config dataclass, and all tests.

## Parent Issue

Decomposed from ENH-1337: Add Per-Subtree Depth Limit to `recursive-refine`

## Motivation

`recursive-refine` currently relies on `max_iterations: 500` as its only depth defense. A single runaway subtree can consume the entire iteration budget while siblings starve. See ENH-1337 for full motivation and 2026 research citations.

## Proposed Solution

### Step 1 — Config schema + Python config wiring

Add `commands.recursive_refine` to `config-schema.json` (model: existing `commands.confidence_gate` at lines 351–421):

```json
"recursive_refine": {
  "type": "object",
  "description": "Configuration for the recursive-refine loop",
  "properties": {
    "max_depth": {
      "type": "integer",
      "minimum": 1,
      "default": 3,
      "description": "Maximum decomposition depth per subtree (default 3)"
    }
  }
}
```

Add `RecursiveRefineConfig` dataclass and extend `CommandsConfig` in `scripts/little_loops/config/automation.py`, following the `ConfidenceGateConfig` pattern (lines 152–172):

```python
@dataclass
class RecursiveRefineConfig:
    max_depth: int = 3

@dataclass
class CommandsConfig:
    # ... existing fields ...
    recursive_refine: RecursiveRefineConfig = field(default_factory=RecursiveRefineConfig)
```

Wire `max_depth: 3` into the `context:` block of `recursive-refine.yaml` with comment: `# canonical: commands.recursive_refine.max_depth`.

### Step 2 — `parse_input` depth-map initialization

After existing queue initialization, add:

```bash
while IFS= read -r id; do echo "$id 0"; done \
  < .loops/tmp/recursive-refine-queue.txt \
  > .loops/tmp/recursive-refine-depth-map.txt
> .loops/tmp/recursive-refine-skipped-depth.txt
```

### Step 3 — `dequeue_next` depth lookup

Append after the existing head/tail pop:

```bash
DEPTH=$(grep "^$CURRENT " .loops/tmp/recursive-refine-depth-map.txt 2>/dev/null | awk '{print $2}' || echo 0)
printf '%s' "$DEPTH" > .loops/tmp/recursive-refine-current-depth.txt
```

### Step 4 — Insert `check_depth` gate state

Insert between `recheck_scores` and `run_size_review` (replacing `recheck_scores → run_size_review` with `recheck_scores → check_depth → run_size_review`):

```yaml
check_depth:
  action: |
    MAX_DEPTH=$(python3 << 'PYEOF'
    import json
    from pathlib import Path
    p = Path('.ll/ll-config.json')
    cfg = {}
    if p.exists():
        try:
            cfg = json.loads(p.read_text())
        except Exception:
            pass
    print(cfg.get('commands', {}).get('recursive_refine', {}).get('max_depth', ${context.max_depth}))
    PYEOF
    )
    [ -z "$MAX_DEPTH" ] && MAX_DEPTH=${context.max_depth}
    CURRENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
    if [ "$CURRENT_DEPTH" -ge "$MAX_DEPTH" ]; then
      echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-depth.txt
      echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt
      echo 1
    else
      echo 0
    fi
  action_type: shell
  evaluate:
    type: output_numeric
    operator: lt
    target: 1
  on_yes: run_size_review
  on_no: dequeue_next
  on_error: run_size_review
```

Note: depth-capped IDs are written to **both** `recursive-refine-skipped-depth.txt` and `recursive-refine-skipped.txt` so outer-loop callers (`auto-refine-and-implement`, `sprint-refine-and-implement`) accumulate them correctly in `get_passed_issues`.

### Step 5 — `enqueue_children` / `enqueue_or_skip` updates

After prepending each child to the queue, append depth tracking:

```bash
PARENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
while IFS= read -r child; do
  echo "$child $((PARENT_DEPTH + 1))" >> .loops/tmp/recursive-refine-depth-map.txt
done < .loops/tmp/recursive-refine-new-children.txt
```

### Step 6 — `done` summary partitioning

Read both skip files and emit a `Skipped (depth-cap N)` line:

```bash
DEPTH_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-depth.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
DEPTH_COUNT=$(echo "$DEPTH_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
DEPTH_LIST=$(echo "$DEPTH_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
printf 'Skipped (depth-cap %d): %s\n' "$DEPTH_COUNT" "${DEPTH_LIST:-none}"
```

### Steps 7, 9, 10 — Tests (TDD mode: all tests ship with implementation)

**Create** `scripts/tests/test_loops_recursive_refine.py`: Follow the fixture pattern from `scripts/tests/test_ll_loop_execution.py:TestEndToEndExecution` and the `_make_mock_popen_factory` helper (lines 26–39). Add a synthetic 4-level decomposition fixture with `max_depth: 2` that verifies:
- Root issues start at depth 0
- Children are enqueued at depth 1
- Issues at depth ≥ 2 are written to `recursive-refine-skipped-depth.txt` and `recursive-refine-skipped.txt`
- `done` summary includes `Skipped (depth-cap N)` line

**Update** `scripts/tests/test_builtin_loops.py` — fix 3 breaking tests:
- `TestRecursiveRefineLoop.test_required_states_exist` (line 1612): add `"check_depth"` to the `required` set
- `TestRecursiveRefineLoop.test_recheck_scores_on_no_routes_to_run_size_review` (line 1777): update assertion to `== "check_depth"`
- `TestRecursiveRefineLoop.test_recheck_scores_on_error_routes_to_run_size_review` (line 1784): update assertion to `== "check_depth"`

**Update** `scripts/tests/test_config_schema.py` — add `TestConfigSchema.test_recursive_refine_in_schema`: assert `commands.recursive_refine` key exists with `max_depth` (`type: integer`, `minimum: 1`, `default: 3`), following the `test_commands_rate_limits_block` pattern (line 56).

### Step 8 — Python config dataclass

Already covered in Step 1 above.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/config/__init__.py` — add `RecursiveRefineConfig` to the `from .automation import (...)` block and to `__all__`, following the pattern for `ConfidenceGateConfig` and `RateLimitsConfig`
11. Update `scripts/little_loops/config/core.py::BRConfig.to_dict()` — add `"recursive_refine": {"max_depth": self._commands.recursive_refine.max_depth}` inside the `"commands"` dict, following the `confidence_gate` / `rate_limits` serialization pattern
12. Update `scripts/tests/test_config.py::TestCommandsConfig` — extend `test_from_dict_with_all_fields` and `test_from_dict_with_defaults` to cover the new `recursive_refine` field; add `RecursiveRefineConfig` to imports
13. Update `scripts/tests/test_builtin_loops.py::TestRecursiveRefineLoop.test_context_thresholds_defined` — add `assert "max_depth" in ctx` alongside the existing context-key assertions

## Acceptance Criteria

- [ ] `recursive-refine.yaml` exposes `max_depth` in `context:` and reads `.ll/ll-config.json` override.
- [ ] Depth map file is created in `parse_input` and updated whenever children are enqueued.
- [ ] `check_depth` state short-circuits size-review once the current issue's depth ≥ `max_depth`, marking it `depth-cap` skipped.
- [ ] Depth-capped IDs are written to both `recursive-refine-skipped-depth.txt` and `recursive-refine-skipped.txt`.
- [ ] `done` summary includes a `Skipped (depth-cap N): IDs...` line when applicable.
- [ ] `config-schema.json` includes `commands.recursive_refine.max_depth` (integer, minimum 1, default 3).
- [ ] `CommandsConfig` in `automation.py` has `recursive_refine: RecursiveRefineConfig` field.
- [ ] New `scripts/tests/test_loops_recursive_refine.py` covers a synthetic 4-level decomposition with `max_depth: 2`.
- [ ] 3 existing tests in `test_builtin_loops.py` updated to expect `check_depth`.
- [ ] New config schema test in `test_config_schema.py`.
- [ ] No regression in existing recursive-refine tests.

## Scope Boundaries

- **In scope**: YAML depth tracking, gate state, summary partitioning, config schema, Python config dataclass, all tests.
- **Out of scope**: Documentation (ENH-1345), per-issue retry budget (ENH-1339), cycle detection (ENH-1338).

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/loops/recursive-refine.yaml` — add `max_depth` to `context:`, insert `check_depth` state, update `parse_input`/`dequeue_next`/`enqueue_children`/`enqueue_or_skip`/`done`
- `config-schema.json` — add `commands.recursive_refine` with `max_depth`
- `scripts/little_loops/config/automation.py` — add `RecursiveRefineConfig` dataclass, extend `CommandsConfig`
- `scripts/tests/test_loops_recursive_refine.py` — **create new file**
- `scripts/tests/test_builtin_loops.py` — fix 3 breaking assertions
- `scripts/tests/test_config_schema.py` — add new schema test

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — re-exports `CommandsConfig` in `__all__` and the top-level `from ... import` block; must also export `RecursiveRefineConfig` to match the pattern for `ConfidenceGateConfig` and `RateLimitsConfig` [Agent 1]
- `scripts/little_loops/config/core.py` — imports `CommandsConfig` and calls `CommandsConfig.from_dict()` in `BRConfig._parse_config()`; **`BRConfig.to_dict()` serializes the `"commands"` dict manually and will silently omit `commands.recursive_refine` unless a `"recursive_refine": {"max_depth": ...}` entry is added** alongside the existing `confidence_gate`, `tdd_mode`, `rate_limits` entries [Agent 2]

### Similar Patterns

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:check_refine_limit` — exact model for `check_depth` gate state
- `scripts/little_loops/loops/recursive-refine.yaml:check_broke_down` — existing `output_numeric` gate in same loop
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:check_lifetime_limit` — Python inline config-override pattern

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py::TestCommandsConfig.test_from_dict_with_all_fields` (line 449) — update: add `"recursive_refine": {"max_depth": 5}` to test `data` dict and `assert config.recursive_refine.max_depth == 5`; also add `RecursiveRefineConfig` to the file's import block [Agent 3]
- `scripts/tests/test_config.py::TestCommandsConfig.test_from_dict_with_defaults` (line 473) — update: add `assert config.recursive_refine.max_depth == 3` to confirm the default is surfaced correctly [Agent 3]
- `scripts/tests/test_builtin_loops.py::TestRecursiveRefineLoop.test_context_thresholds_defined` (line 1700) — update: add `assert "max_depth" in ctx` alongside existing `readiness_threshold`, `outcome_threshold`, `max_refine_count` assertions [Agent 3]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Line reference corrections:**
- `ConfidenceGateConfig` dataclass is at `automation.py:96–111` (the issue text says "following the `ConfidenceGateConfig` pattern (lines 152–172)" but lines 151–172 are `CommandsConfig` itself; follow `ConfidenceGateConfig` at 96–111 for the `RecursiveRefineConfig` structure)
- **`CommandsConfig.from_dict()` at `automation.py:163–172` also needs updating** — add `recursive_refine=RecursiveRefineConfig.from_dict(data.get("recursive_refine", {}))` to its return; without this, `.ll/ll-config.json` values are not surfaced through `CommandsConfig`
- `config-schema.json` closes the `commands` object with `additionalProperties: false` at line 422 — insert the `recursive_refine` block before line 422, not after
- `_make_mock_popen_factory` is at `test_ll_loop_execution.py:26–41` (issue says 26–39); `TestEndToEndExecution` class is at lines 95–198

**Confirmed current `recheck_scores` transitions (`recursive-refine.yaml:251–291`):**
- `on_yes` → `dequeue_next`
- `on_no` → `run_size_review` → becomes `check_depth` after this PR
- `on_error` → `run_size_review` → becomes `check_depth` after this PR

**Both `enqueue_children` (lines 190–211) and `enqueue_or_skip` (lines 301–348) prepend children from `recursive-refine-new-children.txt`** — the Step 5 depth-map append block applies to both states.

**`done` state is at lines 350–369** — Step 6 inserts the `Skipped (depth-cap N)` `printf` alongside the existing `Passed`/`Skipped` lines.

**`refine-to-ready-issue.yaml` models (verified):**
- `check_refine_limit` (lines 213–230): structural model for `check_depth` (`output_numeric`, `operator: lt`, `target: 1`, shell echo 0/1)
- `check_lifetime_limit` (lines 34–75): Python here-doc `.ll/ll-config.json` override pattern (walk `cfg.get('commands', {}).get(...)` with `${context.max_depth}` as YAML-interpolated fallback)

## Impact

- **Priority**: P2 — Defensive; no current outage but real risk with large issues
- **Effort**: Medium — Well-specified changes with code snippets in parent issue
- **Risk**: Low — Default `max_depth: 3` is permissive; new state is purely additive
- **Breaking Change**: No

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-03T15:58:59 - `dbb0e63c-be49-432f-9671-f8f7f8a4d675.jsonl`
- `/ll:confidence-check` - 2026-05-03T00:00:00 - `c9e566ce-792b-43e0-bdf1-cf831bfcaa71.jsonl`
- `/ll:wire-issue` - 2026-05-03T15:51:58 - `ea3b6b2c-b0c9-45be-b20f-36916aa5d82d.jsonl`
- `/ll:refine-issue` - 2026-05-03T15:48:05 - `250d0331-e2df-4ba1-aae2-e18bac88b7d1.jsonl`
- `/ll:refine-issue` - 2026-05-03T15:48:00 - `250d0331-e2df-4ba1-aae2-e18bac88b7d1.jsonl`
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `9f5908fa-e7cf-482b-a91b-52624eb2a99c.jsonl`
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `dbb0e63c-be49-432f-9671-f8f7f8a4d675.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-03
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1346: Config Schema + Python Config Layer for `recursive-refine` Depth Limit
- ENH-1347: YAML FSM Depth Tracking for `recursive-refine` Depth Limit
