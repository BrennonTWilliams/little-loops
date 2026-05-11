---
id: ENH-1347
type: ENH
priority: P2

size: Medium
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-03T16:51:28Z
parent: ENH-1344
---

# ENH-1347: YAML FSM Depth Tracking for `recursive-refine` Depth Limit

## Summary

Add per-subtree depth tracking to `recursive-refine.yaml`: initialize a depth-map in `parse_input`, read depth in `dequeue_next`, insert a `check_depth` gate state between `recheck_scores` and `run_size_review`, append child depths in `enqueue_children`/`enqueue_or_skip`, and emit a `Skipped (depth-cap N)` summary line in `done`. Includes all loop behavior tests.

## Current Behavior

`recursive-refine.yaml` declares `max_depth: 3` in its `context:` block but never reads or enforces it. The only depth defense is the top-level `max_iterations: 500` budget, which a single runaway subtree can exhaust while sibling subtrees receive zero refinement iterations.

## Expected Behavior

A new `check_depth` gate state is inserted between `recheck_scores` and `run_size_review`. Each dequeued issue has its depth looked up from `recursive-refine-depth-map.txt`; if depth ≥ `max_depth`, the issue is written to both skip files and the loop advances to `dequeue_next` without running size review. Child issues are enqueued with `parent_depth + 1`. The `done` state reports a `Skipped (depth-cap N): IDs...` summary line.

## Parent Issue

Decomposed from ENH-1344: Implement Per-Subtree Depth Limit in `recursive-refine`

## Prerequisite

**ENH-1346 must be completed first** — this child depends on `max_depth: 3` being present in `recursive-refine.yaml`'s `context:` block and on `config-schema.json` having the `commands.recursive_refine` definition.

## Motivation

`recursive-refine` currently relies on `max_iterations: 500` as its only depth defense. A single runaway subtree can consume the entire iteration budget while siblings starve. This child implements the YAML state machine changes that enforce the depth cap at runtime.

## Proposed Solution

### Step 1 — `parse_input` depth-map initialization

After existing queue initialization in `parse_input`, add:

```bash
while IFS= read -r id; do echo "$id 0"; done \
  < .loops/tmp/recursive-refine-queue.txt \
  > .loops/tmp/recursive-refine-depth-map.txt
> .loops/tmp/recursive-refine-skipped-depth.txt
```

### Step 2 — `dequeue_next` depth lookup

Append after the existing head/tail pop in `dequeue_next`:

```bash
DEPTH=$(grep "^$CURRENT " .loops/tmp/recursive-refine-depth-map.txt 2>/dev/null | awk '{print $2}' || echo 0)
printf '%s' "$DEPTH" > .loops/tmp/recursive-refine-current-depth.txt
```

### Step 3 — Insert `check_depth` gate state

Insert between `recheck_scores` and `run_size_review` (replacing the `recheck_scores → run_size_review` edges with `recheck_scores → check_depth → run_size_review`):

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

Update `recheck_scores` transitions:
- `on_no` → `check_depth` (was `run_size_review`)
- `on_error` → `check_depth` (was `run_size_review`)

### Step 4 — `enqueue_children` / `enqueue_or_skip` updates

After prepending each child to the queue in both states, append depth tracking:

```bash
PARENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
while IFS= read -r child; do
  echo "$child $((PARENT_DEPTH + 1))" >> .loops/tmp/recursive-refine-depth-map.txt
done < .loops/tmp/recursive-refine-new-children.txt
```

Both `enqueue_children` (lines 190–211) and `enqueue_or_skip` (lines 301–348) prepend children from `recursive-refine-new-children.txt` — this block applies to both.

### Step 5 — `done` summary partitioning

In the `done` state (lines 350–369), add:

```bash
DEPTH_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-depth.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
DEPTH_COUNT=$(echo "$DEPTH_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
DEPTH_LIST=$(echo "$DEPTH_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
printf 'Skipped (depth-cap %d): %s\n' "$DEPTH_COUNT" "${DEPTH_LIST:-none}"
```

### Step 6 — Tests (TDD mode)

**Create** `scripts/tests/test_loops_recursive_refine.py`:
Follow the fixture pattern from `scripts/tests/test_ll_loop_execution.py:TestEndToEndExecution` (lines 95–198) and the `_make_mock_popen_factory` helper (lines 26–41).

Add a synthetic 4-level decomposition fixture with `max_depth: 2` that verifies:
- Root issues start at depth 0
- Children are enqueued at depth 1
- Issues at depth ≥ 2 are written to `recursive-refine-skipped-depth.txt` and `recursive-refine-skipped.txt`
- `done` summary includes `Skipped (depth-cap N)` line

**Update** `scripts/tests/test_builtin_loops.py` — fix 3 breaking tests:
- `TestRecursiveRefineLoop.test_required_states_exist` (line 1612): add `"check_depth"` to the `required` set
- `TestRecursiveRefineLoop.test_recheck_scores_on_no_routes_to_run_size_review` (line 1777): update assertion to `== "check_depth"`
- `TestRecursiveRefineLoop.test_recheck_scores_on_error_routes_to_run_size_review` (line 1784): update assertion to `== "check_depth"`
- `TestRecursiveRefineLoop.test_context_thresholds_defined` (line 1700): add `assert "max_depth" in ctx`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add 4 new structural tests for `check_depth` to `TestRecursiveRefineLoop` in `scripts/tests/test_builtin_loops.py`, following the `check_broke_down` cluster (lines 1721–1762):
   - `test_check_depth_evaluate_output_numeric_lt_1` — asserts `evaluate.type == "output_numeric"`, `operator == "lt"`, `target == 1`
   - `test_check_depth_on_yes_routes_to_run_size_review` — asserts `on_yes == "run_size_review"`
   - `test_check_depth_on_no_routes_to_dequeue_next` — asserts `on_no == "dequeue_next"`
   - `test_check_depth_on_error_routes_to_run_size_review` — asserts `on_error == "run_size_review"`

## Acceptance Criteria

- [ ] `recursive-refine.yaml` `parse_input` initializes `recursive-refine-depth-map.txt` (root IDs at depth 0) and clears `recursive-refine-skipped-depth.txt`
- [ ] `dequeue_next` writes current issue depth to `recursive-refine-current-depth.txt`
- [ ] `check_depth` state short-circuits size-review once depth ≥ `max_depth`, writing to both skip files
- [ ] `recheck_scores` `on_no` and `on_error` route to `check_depth` (not `run_size_review`)
- [ ] `enqueue_children` and `enqueue_or_skip` both append child depths to the depth map
- [ ] `done` summary includes `Skipped (depth-cap N): IDs...` line when applicable
- [ ] `test_loops_recursive_refine.py` created with synthetic 4-level decomposition fixture
- [ ] 3 existing `test_builtin_loops.py` assertions updated for `check_depth`
- [ ] `test_context_thresholds_defined` updated with `"max_depth"` assertion
- [ ] No regression in existing recursive-refine tests

## Scope Boundaries

- **In scope**: `recursive-refine.yaml` state machine changes (Steps 1–5), all loop behavior tests
- **Out of scope**: Config schema and Python config layer (ENH-1346), documentation (ENH-1345)

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/loops/recursive-refine.yaml` — all YAML state changes (Steps 1–5)
- `scripts/tests/test_loops_recursive_refine.py` — **create new file** with end-to-end depth-cap fixture
- `scripts/tests/test_builtin_loops.py` — fix 4 assertions

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — third outer-loop invoker; calls `recursive-refine` via `loop: recursive-refine` in `refine_unresolved` state with `context_passthrough: true`; does not read `recursive-refine-skipped.txt` (no `get_passed_issues` state) — no code change needed, listed for implementer awareness

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestRecursiveRefineLoop`: add 4 new structural tests for `check_depth` state (alongside the 3 break-fix updates already in scope), following the `check_broke_down` cluster at lines 1721–1762:
  - `test_check_depth_evaluate_output_numeric_lt_1` — verifies `evaluate.type == "output_numeric"`, `operator == "lt"`, `target == 1`
  - `test_check_depth_on_yes_routes_to_run_size_review` — verifies `on_yes == "run_size_review"`
  - `test_check_depth_on_no_routes_to_dequeue_next` — verifies `on_no == "dequeue_next"`
  - `test_check_depth_on_error_routes_to_run_size_review` — verifies `on_error == "run_size_review"`

### Similar Patterns

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:check_refine_limit` (lines 213–230) — exact structural model for `check_depth` (`output_numeric`, `operator: lt`, `target: 1`, shell echo 0/1)
- `scripts/little_loops/loops/recursive-refine.yaml:check_broke_down` — existing `output_numeric` gate in same loop
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:check_lifetime_limit` (lines 34–75) — Python here-doc `.ll/ll-config.json` override pattern

### Confirmed Current `recheck_scores` Transitions (`recursive-refine.yaml:251–291`)

- `on_yes` → `dequeue_next` (unchanged)
- `on_no` → `run_size_review` → **becomes `check_depth` after this PR**
- `on_error` → `run_size_review` → **becomes `check_depth` after this PR**

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`recursive-refine.yaml` state inventory**: 13 states, 374 lines; `check_depth` confirmed absent; `max_depth: 3` declared in `context:` block at line 28 but never consumed — `${context.max_depth}` interpolation in the proposed `check_depth` action will resolve correctly
- **Exact state line numbers** (verified, issue references accurate within 1–2 lines):
  - `recheck_scores`: line 252 (`on_no: run_size_review`, `on_error: run_size_review` — confirmed targets for Step 3 replacement)
  - `enqueue_children`: line 191 (prepends `recursive-refine-new-children.txt`, then moves parent to `.issues/completed/`)
  - `enqueue_or_skip`: line 302 (same queue-prepend + parent-move pattern as `enqueue_children`)
  - `done`: line 351 (reads only `passed.txt` and `skipped.txt` — no depth data available today)
- **Test line corrections** (off by 1 from issue):
  - `test_recheck_scores_on_no_routes_to_run_size_review`: actual line **1778** (issue says 1777)
  - `test_recheck_scores_on_error_routes_to_run_size_review`: actual line **1785** (issue says 1784)
- **`test_context_thresholds_defined` (line 1700) is already complete**: `assert "max_depth" in ctx` exists at line 1706 — **do not update this test**; remove it from the Step 6 to-do (only 3 tests need updating, not 4)
- **`test_loops_recursive_refine.py`**: confirmed absent at `scripts/tests/test_loops_recursive_refine.py` — must be created
- **Outer loop dependents** that read `recursive-refine-skipped.txt` via `get_passed_issues`:
  - `scripts/little_loops/loops/auto-refine-and-implement.yaml`
  - `scripts/little_loops/loops/sprint-refine-and-implement.yaml`
  — The double-write in Step 3 (`recursive-refine-skipped-depth.txt` **and** `recursive-refine-skipped.txt`) is correct and required for these callers

## Impact

- **Priority**: P2
- **Effort**: Medium — Careful YAML state machine edits + new test fixture
- **Risk**: Low — New state is purely additive; default `max_depth: 3` is permissive
- **Breaking Change**: No

## Labels

`enhancement`, `automation`, `loops`, `yaml-fsm`

## Resolution

Implemented all 5 YAML state machine steps:

1. `parse_input` — initializes `recursive-refine-depth-map.txt` (root IDs at depth 0) and clears `recursive-refine-skipped-depth.txt`
2. `dequeue_next` — reads depth from map using `grep`/`awk`, writes to `recursive-refine-current-depth.txt` with `${DEPTH:-0}` default
3. `check_depth` gate state — inserted between `recheck_scores` and `run_size_review`; echoes 0/1 based on depth vs `max_depth` (config override via `.ll/ll-config.json`); depth-capped IDs written to both skip files; `recheck_scores.on_no` and `on_error` updated to route to `check_depth`
4. `enqueue_children` and `enqueue_or_skip` — both append `child $((PARENT_DEPTH + 1))` entries to depth-map after queue-prepend
5. `done` — added `Skipped (depth-cap N): IDs` summary line

Tests: created `scripts/tests/test_loops_recursive_refine.py` (14 shell-execution tests across 5 test classes); updated `test_builtin_loops.py` with `check_depth` in required states, 2 corrected transition assertions, and 4 new structural tests.

## Status

**Completed** | Created: 2026-05-03 | Completed: 2026-05-03 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-03T16:40:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/758e65f0-d85f-4f64-9923-01f4774eca98.jsonl`
- `/ll:confidence-check` - 2026-05-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77a563f2-e263-4e8c-83f7-088bad88d5ff.jsonl`
- `/ll:wire-issue` - 2026-05-03T16:34:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7cf8909d-20a1-44b0-ba53-d2ba5b2712f1.jsonl`
- `/ll:refine-issue` - 2026-05-03T16:27:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9839f41f-ca15-47f8-ad6b-d3afab2e7508.jsonl`
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbb0e63c-be49-432f-9671-f8f7f8a4d675.jsonl`
- `/ll:manage-issue` - 2026-05-03T16:51:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
