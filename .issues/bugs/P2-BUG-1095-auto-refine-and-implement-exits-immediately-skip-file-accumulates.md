---
discovered_date: 2026-04-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-1095: auto-refine-and-implement exits immediately after skip file accumulates

## Summary

The `auto-refine-and-implement` loop exits immediately on every run once its skip file (`.loops/tmp/auto-refine-and-implement-skipped.txt`) has accumulated skipped issue IDs from a prior run. The file is never cleared between runs, so `ll-issues next-issue --skip "$SKIPPED"` returns nothing (exit code 1), routing the loop to the `done` terminal state without processing any issues.

## Current Behavior

After a first full run that skips any issues:

1. Skipped IDs are written to `.loops/tmp/auto-refine-and-implement-skipped.txt`
2. On the next run, `get_next_issue` reads the accumulated skip list
3. All active issues are in the skip list → `ll-issues next-issue --skip` returns nothing
4. Loop routes to `done` immediately — no issues are processed

The bug is dormant until at least one issue has been skipped; once any ID accumulates, the loop becomes permanently stuck on subsequent runs.

## Expected Behavior

Each invocation of `ll-loop run auto-refine-and-implement` should start with a fresh skip file, processing the full backlog in priority order. Implemented issues are already in `completed/` and won't be returned by `ll-issues next-issue` regardless of the skip list.

## Root Cause

**File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`

The loop's `initial` state is `get_next_issue`. There is no `init` state to truncate session-scoped temp files before the run begins. The skip file persists across invocations.

```yaml
# Current — no init state
initial: get_next_issue
```

The skip file was designed for within-run deduplication (avoid re-processing a decomposed parent in the same session), but it also gates the very first action of the next run.

## Proposed Solution

Add an `init` state before `get_next_issue` that truncates the skip file and impl queue:

```yaml
initial: init

states:
  init:
    action: mkdir -p .loops/tmp && rm -f .loops/tmp/auto-refine-and-implement-skipped.txt && rm -f .loops/tmp/auto-refine-and-implement-impl-queue.txt
    action_type: shell
    next: get_next_issue
```

This matches the codebase convention established in `scripts/little_loops/loops/issue-refinement.yaml:11-14`, which is the canonical cleanup-init pattern:

```yaml
# issue-refinement.yaml:11-14 — reference implementation
init:
  action: mkdir -p .loops/tmp && rm -f .loops/tmp/issue-refinement-commit-count && rm -f .loops/tmp/issue-refinement-skip-list
  action_type: shell
  next: evaluate
```

Single-line shell action with `next:` (unconditional — no exit-code evaluation needed for a cleanup step).

This is safe because:
- Implemented issues are in `completed/` — `ll-issues next-issue` never returns them
- Decomposed parents should also be in `completed/` (see BUG-1096); fix #2 is a prerequisite for this fix to be fully correct
- Failed-refinement issues get a fresh attempt on each run (desirable)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — add `init` state, change `initial`

### Dependent Files
- `.loops/tmp/auto-refine-and-implement-skipped.txt` — cleared on each run start
- `.loops/tmp/auto-refine-and-implement-impl-queue.txt` — cleared on each run start
- BUG-1096 (`recursive-refine` decomposed parents not moved to `completed/`) — should be fixed first so cleared skip file does not cause re-decomposition

### Similar Patterns
- `scripts/little_loops/loops/issue-refinement.yaml:11-14` — canonical `rm -f` init pattern to follow (single-line, `next:` routing)

### Tests
- `scripts/tests/test_builtin_loops.py` — existing loop tests referencing `auto-refine-and-implement`; extend with a second-run scenario: run once to accumulate skipped IDs, verify a second run still processes new issues
- Verify loop processes at least one issue after a prior run that accumulated skipped IDs
- Verify loop does not re-process implemented issues (they are in `completed/`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:861` — `test_required_top_level_fields` asserts `data.get("initial") == "get_next_issue"` — **WILL BREAK**; must update expected value to `"init"` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:864-877` — `test_required_states_exist` `required` set should include `"init"` for completeness (does not break, but incomplete) [Agent 3 finding]
- New test: `test_init_state_exists` — assert `"init" in data["states"]` [Agent 3 finding]
- New test: `test_init_state_is_shell_type` — assert `data["states"]["init"]["action_type"] == "shell"` and `data["states"]["init"]["next"] == "get_next_issue"` [Agent 3 finding]
- New test: `test_init_clears_skip_file` — assert `"auto-refine-and-implement-skipped.txt"` in `init.action` [Agent 3 finding]
- New test: `test_init_clears_impl_queue_file` — assert `"auto-refine-and-implement-impl-queue.txt"` in `init.action` [Agent 3 finding]
- Pattern to follow: `scripts/tests/test_builtin_loops.py:476-482` — `TestIssueRefinementSubLoop.test_init_action_clears_skip_list` is the canonical template [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:411-419` — FSM flow diagram shows `get_next_issue` as the entry state; prepend `init →` to reflect the new initial state [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:422` — skip-tracking paragraph describes the skip file without noting per-run truncation; add a note that `init` clears the skip file on each fresh `ll-loop run` invocation [Agent 2 finding]

### Related Loops
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — sibling loop with identical skip file structure (`.loops/tmp/sprint-refine-and-implement-skipped.txt`); likely has the same cross-run accumulation bug — track as a separate issue

## Implementation Steps

1. In `auto-refine-and-implement.yaml`, change `initial: get_next_issue` to `initial: init`
2. Add `init` state (before `get_next_issue`) that truncates both temp files with `: >`
3. Confirm BUG-1096 is also fixed so decomposed parents are in `completed/` before this runs
4. Run the loop twice: first run should process issues, second run should pick up any new issues created by decomposition, not exit immediately; extend `scripts/tests/test_builtin_loops.py` with a second-run scenario

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_builtin_loops.py:861` — change `assert data.get("initial") == "get_next_issue"` to `== "init"` (breaking assertion)
6. Update `scripts/tests/test_builtin_loops.py:864-877` — add `"init"` to `required` set in `test_required_states_exist` for completeness
7. Add 4 new structural tests to `TestAutoRefineAndImplementLoop` in `test_builtin_loops.py`: `test_init_state_exists`, `test_init_state_is_shell_type`, `test_init_clears_skip_file`, `test_init_clears_impl_queue_file` — follow the `TestIssueRefinementSubLoop.test_init_action_clears_skip_list` pattern at line 476-482
8. Update `docs/guides/LOOPS_GUIDE.md:411-419` — prepend `init →` to the FSM flow diagram entry
9. Update `docs/guides/LOOPS_GUIDE.md:422` — note that `init` truncates the skip file on each fresh run

## Impact

- **Priority**: P2 — Loop is functionally broken after first use; silently does nothing
- **Effort**: Minimal — Two-line YAML change
- **Risk**: Low — Additive state; no logic changes to processing
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `auto-refine-and-implement`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-13T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:wire-issue` - 2026-04-13T20:18:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/380433f9-aa5c-461b-919e-c5a4226b42c9.jsonl`
- `/ll:refine-issue` - 2026-04-13T20:12:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7573101-1e4a-4e97-80cd-2130b1c40d72.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6681d3d-2446-482f-83ae-c425d516d2ac.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P2
