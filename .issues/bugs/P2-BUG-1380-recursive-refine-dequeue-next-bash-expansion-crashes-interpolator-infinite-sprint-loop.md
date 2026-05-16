---
id: BUG-1380
type: BUG
priority: P2
status: resolved
captured_at: 2026-05-07 00:00:00+00:00
completed_at: 2026-05-07T00:00:00Z
discovered_date: 2026-05-07
discovered_by: user
decision_needed: false
confidence_score: 99
outcome_confidence: 100
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 5
score_change_surface: 10
---

# BUG-1380: `recursive-refine` `dequeue_next` Bash Expansion Crashes Interpolator, Causes Infinite Sprint Loop

## Summary

`dequeue_next` in `recursive-refine.yaml` uses bash parameter expansion with default-value modifiers (`${DEPTH:-0}` and `${DEPTH:+" (depth: $DEPTH)"}`). The FSM interpolator's regex `r"\$\{([^}]+)\}"` matches any `${...}` in an action template and raises `InterpolationError` for any match that lacks a `.` (the required `namespace.path` separator). Because neither `DEPTH:-0` nor `DEPTH:+" (depth: $DEPTH)"` contains a dot, interpolation throws before the action is executed. The exception routes `dequeue_next` to `on_error: done`, short-circuiting all refinement work.

In `sprint-refine-and-implement`, this caused an infinite loop: recursive-refine exits via its `done` terminal (the success path), the outer sprint loop routes to `get_passed_issues`, which finds nothing passed or skipped and routes back to `get_next_issue` without adding the issue to the outer skip file. The same issue is re-picked on every iteration. The loop ran 191 times on BUG-635 before being killed with Ctrl+C.

## Observed Behavior

Debug trace (loop-viz, `bug-fixes` sprint):

```
[1/500] get_next_issue   -> BUG-635  ✓ yes  -> refine_issue
[2/500] refine_issue     [1/500] parse_input -> Queued 1 issue(s)  ✓ yes  -> dequeue_next
                         [2/500] dequeue_next (0s)         -> done   ← no action output
        -> get_passed_issues  exit: 1  ✗ no  -> get_next_issue
[4/500] get_next_issue   -> BUG-635  (repeat forever)
```

- No `action_start` event for `dequeue_next` — interpolation fails before the action runs.
- The `action_error` event is emitted internally but not displayed by the CLI formatter.
- `(0s)` execution time and immediate `-> done` routing are the only visible signals.

## Root Cause

**File:** `scripts/little_loops/loops/recursive-refine.yaml` — `dequeue_next.action`, lines 88 and 96

```yaml
# Line 88 — bash default-value expansion:
printf '%s' "${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt

# Line 96 — bash conditional expansion:
DEPTH_STR=${DEPTH:+" (depth: $DEPTH)"}
```

**Interpolator:** `scripts/little_loops/fsm/interpolation.py`

```python
VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")

def replace_var(match):
    full_path = match.group(1)
    if "." not in full_path:
        raise InterpolationError(
            f"Invalid variable: ${{{full_path}}} (expected namespace.path)"
        )
```

`${DEPTH:-0}` → `full_path = "DEPTH:-0"` → no `.` → `InterpolationError`.  
`${DEPTH:+" (depth: $DEPTH)"}` → `full_path = 'DEPTH:+" (depth: $DEPTH)"'` → no `.` → `InterpolationError`.

**Failure cascade:**

1. `interpolate(action_template, ctx)` throws `InterpolationError` in `_run_action()`
2. `_run_action_or_route()` catches it → emits `action_error` (not shown in CLI) → returns `(None, "done")`
3. `_execute_state()` returns `"done"` → recursive-refine terminates with `terminated_by="terminal"`, `final_state="done"`
4. Outer sprint loop: `refine_issue.on_success` → `get_passed_issues` (correct routing for `done` terminal)
5. `get_passed_issues`: `recursive-refine-passed.txt` and `recursive-refine-skipped.txt` are both empty (parse_input cleared them, dequeue_next never ran) → exit 1 → `get_next_issue`
6. `get_next_issue`: issue not in outer skip file → re-queues same issue → infinite loop

## Historical Context

- **Introduced by:** `d7418d80` — `improve(recursive-refine): emit real-time dequeue progress line to stderr (ENH-1348)` — added the progress `printf` with `${DEPTH:-0}` and `${DEPTH:+" (depth: $DEPTH)"}`.
- **Partially fixed by:** `0906e0af` — `fix(recursive-refine): drop braces from bare bash vars to avoid interpolation clash` — dropped braces from simple bare-bash vars (`${DEPTH}` → `$DEPTH`) but missed expansion-modifier forms that require braces.
- **Correctly escaped elsewhere in same file:** `done` state already uses `$${PASSED_LIST:-none}` (double `$$` → literal `${}`), showing the pattern was known but applied inconsistently.

## Fix

Escape the two bash parameter expansions using `$${}` (interpolator converts `$${` → `${` at runtime):

```yaml
# Line 88 — before:
printf '%s' "${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt
# After:
printf '%s' "$${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt

# Line 96 — before:
DEPTH_STR=${DEPTH:+" (depth: $DEPTH)"}
# After:
DEPTH_STR=$${DEPTH:+" (depth: $DEPTH)"}
```

**File changed:** `scripts/little_loops/loops/recursive-refine.yaml` (2 lines)

## Verification

- 139 interpolation and recursive-refine tests pass after fix (`python -m pytest scripts/tests/ -k "recursive_refine or interpolat" -v`)
- Debug output for `dequeue_next` now shows action text and progress line instead of silent `-> done`
