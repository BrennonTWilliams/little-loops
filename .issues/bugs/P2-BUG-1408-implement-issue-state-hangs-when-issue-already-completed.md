---
captured_at: '2026-05-09T22:24:13Z'
completed_at: '2026-05-09T22:57:33Z'
discovered_date: 2026-05-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1408: implement_issue state hangs when issue already completed

## Summary

When a guillotine (Option J) continuation session is spawned mid-loop, the fresh Claude session may find that the target issue is already in `.issues/completed/` — the work was committed during the previous session. The `implement_issue` state still runs `ll-auto --only <issue>` regardless, and the fresh session hangs indefinitely at 0% CPU with no exit condition, blocking the FSM.

## Motivation

FSM loops running `auto-refine-and-implement` or `sprint-refine-and-implement` require unattended operation. When Option J fires and the issue was already committed in the previous session, the loop stalls indefinitely — requiring manual intervention to resume. This undermines the reliability of automated overnight runs where the loop must handle continuation sessions correctly.

## Root Cause

`scripts/little_loops/loops/auto-refine-and-implement.yaml` — `implement_issue` state (line 101): the action `ll-auto --only ${captured.impl_id.output}` is invoked unconditionally. There is no pre-check whether the issue already exists in `.issues/completed/`. When `run_with_continuation` in `issue_manager.py` triggers Option J and spawns a fresh guillotine session, that session starts with a transcript-summary prompt but has nothing to implement. It produces no output and never exits.

The same `implement_issue` / `go_no_go` / `implement_next` block is mirrored in `sprint-refine-and-implement.yaml` (noted in a YAML comment at line 49 of the auto-refine loop), so the same bug is present in both files.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The full blocking chain:

1. `DefaultActionRunner.run()` at `scripts/little_loops/fsm/runners.py:146` blocks in `for line in process.stdout` waiting for the `ll-auto` shell subprocess to close its stdout (i.e., exit). No `_shutdown_requested` check runs during this wait; the per-action timeout is `state.timeout or self.fsm.default_timeout or 3600` — `implement_issue` has no explicit `timeout:`, so the effective limit is 3600 seconds (1 hour).

2. Inside `ll-auto`, `run_with_continuation()` at `issue_manager.py:279–305` spawns the guillotine Claude subprocess via `subprocess.Popen(["claude", "-p", guillotine_cmd])`. Control passes to `run_claude_command()` at `subprocess_utils.py:219–427`, which blocks on `selectors.DefaultSelector` reading that subprocess's stdout/stderr until both file descriptors close.

3. The guillotine Claude session receives the continuation prompt, finds ENH-652 already in `.issues/completed/`, has nothing to implement, produces no output, and never calls `sys.exit()`. The `selectors.DefaultSelector` loop in `run_claude_command()` therefore never terminates, keeping the entire chain blocked: `runners.py` → `ll-auto` → `run_with_continuation()` → `run_claude_command()`.

The completion guard in `implement_issue` short-circuits step 1 entirely: when the issue is already in `completed/`, `ll-auto` is never called, `run_with_continuation()` is never entered, and `runners.py` unblocks immediately.

## Current Behavior

1. `implement_issue` runs `ll-auto --only ENH-652`
2. During the `ll-auto` session, Claude commits the work and context fills → Option J guillotine fires
3. A fresh session starts with the guillotine summary prompt
4. ENH-652 is already in `.issues/completed/`; the fresh session has nothing to do
5. The session hangs at 0% CPU indefinitely
6. The FSM cannot advance past `implement_issue` until `ll-auto` exits — it never does

## Expected Behavior

Before invoking `ll-auto --only <issue>`, `implement_issue` should check whether the issue already appears in `.issues/completed/`. If a match is found, it should log a message and exit 0, letting the FSM advance to `implement_next` normally.

## Steps to Reproduce

1. Start `ll-loop run auto-refine-and-implement`
2. Wait for an issue to be implemented by `ll-auto` during a session that hits context limits (Option J fires)
3. Observe: the FSM enters `implement_issue` for the next continuation session
4. The continuation Claude process hangs at 0% CPU and never exits

## Proposed Solution

Add a completion guard to the `implement_issue` action in both YAML files. The current single-line `action: "ll-auto --only ${captured.impl_id.output}"` becomes a multiline `|` block:

```yaml
implement_issue:
  fragment: with_rate_limit_handling
  action: |
    ISSUE="${captured.impl_id.output}"
    if ls .issues/completed/*${ISSUE}* 2>/dev/null | grep -q .; then
      echo "Issue ${ISSUE} already completed, skipping ll-auto"
      exit 0
    fi
    ll-auto --only ${ISSUE}
  action_type: shell
  on_rate_limit_exhausted: done
  next: implement_next
```

The `ls .issues/completed/*${ISSUE}*` pattern is consistent with how other YAML loop states perform existence checks. The codebase also uses `find .issues -name "*-${ISSUE}-*" ! -path "*/completed/*"` (e.g., `autodev.yaml:284`) for the inverse (finding active files); either approach works here — the `ls` glob is simpler for a pure presence check.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `implement_issue` state (line 101)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — mirrored `implement_issue` state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:162` — `run_with_continuation()` — Option J guillotine path that spawns the hung session; guillotine subprocess launched at lines 279–305
- `scripts/little_loops/subprocess_utils.py:219` — `run_claude_command()` — blocking `selectors.DefaultSelector` loop that keeps `run_with_continuation()` blocked until the guillotine Claude process exits
- `scripts/little_loops/fsm/runners.py:146` — `DefaultActionRunner.run()` — `for line in process.stdout` blocks the FSM Python thread until `ll-auto` exits; no interruptible poll
- `scripts/little_loops/loops/lib/common.yaml:49` — `with_rate_limit_handling` fragment used by `implement_issue`

### Similar Patterns
- `get_next_issue` state already skips issues via `ll-issues next-issue --skip` — the completion check is a complementary guard at the execute layer

### Tests
- `scripts/tests/test_builtin_loops.py:903` — `TestAutoRefineAndImplementLoop` class: existing tests for `implement_issue` state (assert `${captured.impl_id.output}` present, assert `next: implement_next`); extend with a test asserting the completion guard shell pattern is present in the action
- `scripts/tests/test_builtin_loops.py` — add a parallel `TestSprintRefineAndImplementLoop` test or extend the existing sprint loop test class to cover the same guard in `sprint-refine-and-implement.yaml`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop` (line 903): add two new methods asserting the guard: `assert "completed" in action` and `assert "exit 0" in action`; follow the assertion pattern in `TestAutodevLoop.test_enqueue_children_moves_parent_to_completed` (line 1935) which checks `.issues/completed` guard presence the same way
- `scripts/tests/test_builtin_loops.py` — **`TestSprintRefineAndImplementLoop` does not exist** — the "extend existing sprint loop test class" in Implementation Steps must instead _create_ the class from scratch; model it on `TestAutoRefineAndImplementLoop` structure (fixture loads YAML, each method calls `data["states"].get("implement_issue", {})`), include at minimum: `test_required_states_exist`, `test_implement_issue_uses_impl_id`, `test_implement_issue_routes_to_implement_next`, `test_implement_issue_has_completed_guard`

### Documentation
- N/A — no documentation references this FSM state behavior

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — flow diagrams for both `auto-refine-and-implement` (around line 429) and `sprint-refine-and-implement` (around line 391) label the `implement_issue` state as `(ll-auto --only)`; diagrams remain accurate for the normal path — optionally annotate to document the completion guard skip behavior (low priority)

### Configuration
- N/A — no configuration files affected

## Implementation Steps

1. In `scripts/little_loops/loops/auto-refine-and-implement.yaml:103`, change the `implement_issue` `action` from a single-line string to a multiline `|` block with the completion guard prepended
2. Mirror the same guard change in `scripts/little_loops/loops/sprint-refine-and-implement.yaml:109`
3. In `scripts/tests/test_builtin_loops.py:903`, add a test method to `TestAutoRefineAndImplementLoop` asserting that `implement_issue.action` contains the `completed/*${ISSUE}*` guard pattern and `exit 0`; add the same assertion to the sprint loop test class
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to verify both loop YAMLs parse and validate correctly with the new multiline action

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Create `TestSprintRefineAndImplementLoop`** in `scripts/tests/test_builtin_loops.py` — no existing class for `sprint-refine-and-implement.yaml`; model after `TestAutoRefineAndImplementLoop` (line 903) with a `LOOP_FILE = BUILTIN_LOOPS_DIR / "sprint-refine-and-implement.yaml"` fixture; include at minimum the `implement_issue` guard assertions
6. **Check `autodev.yaml`** `implement_current` state (line 226): it also uses `ll-auto --only` but with `fragment: shell_exit` and `on_error: done` — architecturally distinct from the continuation-session hang scenario; confirm it does not need the same guard before closing this bug

## Impact

- **Priority**: P2 — Blocks automated loop runs when Option J fires mid-implementation; discovered in a real loop run
- **Effort**: Small — Additive 4-line shell guard in two YAML state files; no Python changes required
- **Risk**: Low — Guard is purely additive; existing code paths when the issue is not yet completed are unchanged
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `automation`, `loops`, `captured`

## Resolution

**Fixed** — Added a completion guard to `implement_issue` in both `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml`. The guard checks `.issues/completed/*${ISSUE}*` before invoking `ll-auto`; if the issue is already completed it logs a message and exits 0, letting the FSM advance to `implement_next` without hanging. Tests added to `TestAutoRefineAndImplementLoop` and the new `TestSprintRefineAndImplementLoop` class.

## Status

**Completed** | Created: 2026-05-09 | Closed: 2026-05-09 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-05-09T22:57:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-09T22:51:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de4c5b4a-06c0-43a4-9d1e-6b87f562eac4.jsonl`
- `/ll:confidence-check` - 2026-05-09T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed8c7dae-b8ca-4e7d-b2dc-1671f93fa9c2.jsonl`
- `/ll:wire-issue` - 2026-05-09T22:47:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/012eddcb-ecda-4387-b9dd-73a65f9c3355.jsonl`
- `/ll:refine-issue` - 2026-05-09T22:42:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed8c7dae-b8ca-4e7d-b2dc-1671f93fa9c2.jsonl`
- `/ll:format-issue` - 2026-05-09T22:33:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43665bb5-b08a-4083-80d6-5bfcdabc4d8c.jsonl`
- `/ll:capture-issue` - 2026-05-09T22:24:13Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efbb9709-7a24-4905-85fd-8a5a0825d700.jsonl`
