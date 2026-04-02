---
discovered_date: 2026-04-01
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-912: `refine-to-ready-issue` loop missing `/ll:verify-issues` step causes infinite NEEDS_VERIFY cycle

## Summary

The `refine-to-ready-issue` sub-loop never calls `/ll:verify-issues`, but `ll-issues next-action` gates advancement on that command appearing in an issue's `session_commands`. As a result, after the sub-loop completes successfully (confidence check passes), `next-action` still returns `NEEDS_VERIFY <id>` and the outer `issue-refinement` loop re-processes the same issue indefinitely. Issues 8972–8974 (queued behind 8975) are never reached.

## Current Behavior

1. `issue-refinement` loop calls `ll-issues next-action` → `NEEDS_VERIFY ENH-8975`
2. Delegates to `refine-to-ready-issue` sub-loop: runs `format_issue`, `refine_issue`, `confidence_check` (passes at 0.97–1.00)
3. Sub-loop exits as `done`
4. `issue-refinement` calls `ll-issues next-action` again → **still** `NEEDS_VERIFY ENH-8975`
5. Steps 2–4 repeat forever (observed 3+ full cycles within one run before truncation)

## Expected Behavior

After `confidence_check` passes, the sub-loop should run `/ll:verify-issues <id>` so that `next-action` can advance the issue to the next stage (or to `ALL_DONE` if all issues pass). The outer loop should then move on to the remaining queued issues.

## Motivation

This bug causes the entire `issue-refinement` automation to stall indefinitely on the first `NEEDS_VERIFY` issue it encounters. All subsequent issues (passed via `ll-loop run issue-refinement 8972,8973,8974,8975`) are never processed. The loop will run until it hits `max_iterations: 200`, consuming substantial API budget (each iteration costs ~10 minutes of LLM time) with zero net progress after the first cycle.

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchor**: `confidence_check` state (transitions to `done` on yes)
- **Cause**: The `done` terminal state is reached immediately after `confidence_check` passes, with no intervening step to call `/ll:verify-issues`. Meanwhile, `next-action` (`scripts/little_loops/cli/issues/next_action.py`, function `cmd_next_action`, line 38) checks `"/ll:verify-issues" not in issue.session_commands` and returns `NEEDS_VERIFY` whenever that command hasn't been run — which it never is in the current sub-loop.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact line to change**: `refine-to-ready-issue.yaml:42` — `on_yes: done` must become `on_yes: verify_issue`
- **Gate confirmed**: `next_action.py:38-40` — absolute prerequisite: `NEEDS_VERIFY` fires before score checks (lines 41-49); no issue can advance past this gate until `/ll:verify-issues` appears in `session_commands`
- **How `session_commands` is populated**: The FSM executor (`fsm/executor.py:683-756`) does **not** write session log entries. The slash command itself, when executed by Claude, follows in-command instructions to call `ll-issues append-log`, which invokes `append_session_log_entry()` at `session_log.py:85-129`. That function appends a backtick-quoted command name to the `## Session Log` section of the issue file. `parse_session_log()` at `session_log.py:23-39` reads it back via regex. The proposed `verify_issue` state works because `commands/verify-issues.md:151` already contains the `ll-issues append-log` instruction — Claude will write the log entry automatically when `/ll:verify-issues` runs.
- **Existing states confirm pattern**: `format_issue` (line 19-23) and `refine_issue` (lines 25-29) are both `action_type: slash_command` + `next:` — exactly the pattern for the new `verify_issue` state

## Steps to Reproduce

1. Run `ll-loop run issue-refinement <issue-ids>` where at least one issue needs verification
2. Observe: `ll-issues next-action` repeatedly returns `NEEDS_VERIFY <same-id>` across loop iterations
3. Observe: `refine-to-ready-issue` sub-loop completes with confidence ≥ thresholds but issue never advances

## Proposed Solution

Add a `verify_issue` state to `refine-to-ready-issue.yaml` between `confidence_check` (on_yes) and `done`:

```yaml
confidence_check:
  ...
  on_yes: verify_issue   # was: done
  on_no: refine_issue
  on_error: failed

verify_issue:
  action: "/ll:verify-issues ${captured.issue_id.output}"
  action_type: slash_command
  next: done
  on_error: failed
```

This ensures `session_commands` contains `/ll:verify-issues` before the sub-loop exits, satisfying `next-action`'s gate condition.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add `verify_issue` state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/issue-refinement.yaml` — invokes the sub-loop via `loop: refine-to-ready-issue`
- `scripts/little_loops/cli/issues/next_action.py` — `cmd_next_action()` reads `session_commands` to gate NEEDS_VERIFY

### Similar Patterns
- `scripts/little_loops/loops/issue-refinement.yaml` — verify that the outer loop's state machine handles the new terminal state correctly
- `scripts/little_loops/loops/incremental-refactor.yaml:33-37` — `commit_step` uses `slash_command` + `next:` to non-terminal state; exact structural pattern for `verify_issue`
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — `verify_tests → commit` chain: `on_yes` from evaluate state routing to an intermediate `slash_command` state before `done`

### Tests
- `scripts/tests/test_builtin_loops.py:374-443` — `TestIssueRefinementSubLoop` class: template for structural loop test; no equivalent class exists yet for `refine-to-ready-issue.yaml` — **new class needed** (see Implementation Steps)
- `scripts/tests/test_next_action.py:91-117` — `test_needs_verify` and `test_needs_score`: NEEDS_VERIFY gate test pattern; existing tests are sufficient, no new tests needed here
- `scripts/tests/test_fsm_executor.py:172-191` — `test_unconditional_next_transition`: FSM `next:`-chained state execution pattern

### Session Log Mechanism (needed to understand why fix works)
- `scripts/little_loops/session_log.py:85-129` — `append_session_log_entry()`: writes the `/ll:verify-issues` log line to disk when called
- `scripts/little_loops/session_log.py:23-39` — `parse_session_log()`: reads log entries back via regex on `## Session Log` section
- `scripts/little_loops/issue_parser.py:369-391` — populates `IssueInfo.session_commands` from parsed log
- `commands/verify-issues.md:151` — `ll-issues append-log` instruction in verify-issues command (makes the fix self-contained)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. **Modify `scripts/little_loops/loops/refine-to-ready-issue.yaml:42`**: Change `on_yes: done` → `on_yes: verify_issue`
2. **Add `verify_issue` state** in `refine-to-ready-issue.yaml` between `confidence_check` and `done` (after line 44), following the `format_issue`/`refine_issue` pattern (lines 19-29):
   ```yaml
   verify_issue:
     action: "/ll:verify-issues ${captured.issue_id.output}"
     action_type: slash_command
     next: done
     on_error: failed
   ```
3. **Add `TestRefineToReadyIssueSubLoop` class** to `scripts/tests/test_builtin_loops.py` (after line 443), following the `TestIssueRefinementSubLoop` pattern (lines 374-443). Minimum assertions:
   - `verify_issue` state exists in `data["states"]`
   - `confidence_check.on_yes == "verify_issue"` (not `"done"`)
   - `verify_issue.get("action_type") == "slash_command"`
   - `verify_issue.get("next") == "done"`
   - `verify_issue.get("on_error") == "failed"`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v -k "refine_to_ready or IssueRefinement"` to verify the new tests pass

## Impact

- **Priority**: P2 — Blocks entire `issue-refinement` loop from making progress; wastes significant API budget per run
- **Effort**: Small — One-line YAML change to add a state and redirect a transition
- **Risk**: Low — Additive change; only affects sub-loop exit path when confidence check passes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `issue-refinement`, `refine-to-ready`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-04-02T02:43:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbde4238-c365-4ed1-af0f-b596132407a8.jsonl`
- `/ll:confidence-check` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5896a354-c3e5-4bd9-bc1b-afa4b8d6b211.jsonl`
- `/ll:refine-issue` - 2026-04-02T02:18:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5896a354-c3e5-4bd9-bc1b-afa4b8d6b211.jsonl`
- `/ll:format-issue` - 2026-04-02T02:14:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5896a354-c3e5-4bd9-bc1b-afa4b8d6b211.jsonl`
- `/ll:capture-issue` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eaf73d5c-81eb-45a4-a5e6-b157f77ba059.jsonl`

---

**Open** | Created: 2026-04-01 | Priority: P2
