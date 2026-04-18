# BUG-1183: autodev skips parent after breakdown signal + no children — Implementation Plan

**Issue:** `.issues/bugs/P2-BUG-1183-autodev-skips-parent-after-breakdown-signal-no-children.md`
**Priority:** P2  **Confidence:** 98
**Date:** 2026-04-18
**Decision: Option A** — localize the fix to `check_broke_down.action` in both `autodev.yaml` and `recursive-refine.yaml` (preserves BUG-1079 invariant, no cross-loop contract change).

## Problem

`check_broke_down` treats `broke_down == 1` as proof that children exist. When the sub-loop's `/ll:issue-size-review --auto` only recommends breakdown without creating child files, the loop shortcuts to `enqueue_or_skip`, which silently reports "no further decomposition possible" and drops the parent.

## Fix — Option A

Change `check_broke_down.action` in both loops to emit `1` (shortcut) **only when** the breakdown flag is set AND the `*-new-children.txt` scratch file written by `detect_children` is non-empty. Evaluator and `on_yes`/`on_no`/`on_error` routes are unchanged.

### autodev.yaml (lines 248–262)

```yaml
check_broke_down:
  action: |
    FLAG=$(cat .loops/tmp/autodev-broke-down 2>/dev/null || echo 0)
    if [ "$FLAG" = "1" ] && [ -s .loops/tmp/autodev-new-children.txt ]; then
      echo 1
    else
      echo 0
    fi
  action_type: shell
  evaluate:
    type: output_numeric
    operator: lt
    target: 1
  on_yes: recheck_scores     # 0 → flag unset OR no children → proceed
  on_no: enqueue_or_skip     # 1 → flag set AND children exist → shortcut
  on_error: recheck_scores
```

Comment must be rewritten to reflect new semantics.

### recursive-refine.yaml (lines 221–234)

Mirror fix using `.loops/tmp/recursive-refine-broke-down` and `.loops/tmp/recursive-refine-new-children.txt`.

## BUG-1079 Invariant Preservation

When breakdown actually creates children: flag=1 AND new-children.txt non-empty → still shortcuts to `enqueue_or_skip` → no double `/ll:issue-size-review`. Preserved.

## Phase 0: Tests (Red, TDD mode on)

File: `scripts/tests/test_builtin_loops.py`

**Update existing** — `TestAutodevLoop.test_check_broke_down_reads_autodev_namespaced_flag` (line 1173):
- Add `assert "autodev-new-children.txt" in action`.

**Add to `TestAutodevLoop`** (mirroring `TestRecursiveRefineLoop:1331-1364`):
- `test_check_broke_down_evaluate_output_numeric_lt_1`
- `test_check_broke_down_on_yes_routes_to_recheck_scores`
- `test_check_broke_down_on_no_routes_to_enqueue_or_skip`
- `test_check_broke_down_on_error_routes_to_recheck_scores`
- `test_check_broke_down_requires_children_file` — asserts action references both `autodev-broke-down` AND `autodev-new-children.txt`.

**Add to `TestRecursiveRefineLoop`**:
- `test_check_broke_down_requires_children_file` — asserts action references `recursive-refine-new-children.txt`.

**Integration test** in `scripts/tests/test_ll_loop_execution.py`: skipped as redundant with structural tests — `check_broke_down` is a pure shell state; asserting the action content + routes covers the regression. (`_make_mock_popen_factory` would not observe the condition because the action would still just echo a number — the bug is in *what number* gets echoed, which is covered by asserting the shell script content.)

## Phase 1: Implement (Green)

1. Edit `scripts/little_loops/loops/autodev.yaml` `check_broke_down` state.
2. Edit `scripts/little_loops/loops/recursive-refine.yaml` `check_broke_down` state.

## Phase 2: Docs

- `docs/guides/LOOPS_GUIDE.md:451` — update autodev flow diagram branch label `[already size-reviewed?]` → `[broke_down AND children exist?]`.
- `docs/guides/LOOPS_GUIDE.md:468` — recursive-refine Breakdown guard prose: "flag is set → skip" → "flag is set AND children file is non-empty → skip".
- `docs/guides/LOOPS_GUIDE.md:505` — recursive-refine flow diagram branch label update.

## Phase 3: Verify

- `python -m pytest scripts/tests/test_builtin_loops.py -v`
- `python -m pytest scripts/tests/`
- `ruff check scripts/`
- `python -m mypy scripts/little_loops/`

## Out of Scope

- Live replay against FEAT-1181 — requires real autodev run (10+ min wall clock). Structural + unit tests are sufficient regression guard.
- Signal contract change in `/ll:issue-size-review --auto` (Option B) — explicitly rejected per issue analysis.

## Success Criteria

- [x] Plan written
- [ ] New tests fail against current code (Red)
- [ ] autodev.yaml `check_broke_down` updated
- [ ] recursive-refine.yaml `check_broke_down` updated
- [ ] New tests pass (Green)
- [ ] LOOPS_GUIDE.md updated in 3 spots
- [ ] Full test suite + lint + mypy pass
