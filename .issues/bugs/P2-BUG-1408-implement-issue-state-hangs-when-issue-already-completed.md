---
captured_at: '2026-05-09T22:24:13Z'
discovered_date: 2026-05-09
discovered_by: capture-issue
---

# BUG-1408: implement_issue state hangs when issue already completed

## Summary

When a guillotine (Option J) continuation session is spawned mid-loop, the fresh Claude session may find that the target issue is already in `.issues/completed/` — the work was committed during the previous session. The `implement_issue` state still runs `ll-auto --only <issue>` regardless, and the fresh session hangs indefinitely at 0% CPU with no exit condition, blocking the FSM.

## Motivation

FSM loops running `auto-refine-and-implement` or `sprint-refine-and-implement` require unattended operation. When Option J fires and the issue was already committed in the previous session, the loop stalls indefinitely — requiring manual intervention to resume. This undermines the reliability of automated overnight runs where the loop must handle continuation sessions correctly.

## Root Cause

`scripts/little_loops/loops/auto-refine-and-implement.yaml` — `implement_issue` state (line 101): the action `ll-auto --only ${captured.impl_id.output}` is invoked unconditionally. There is no pre-check whether the issue already exists in `.issues/completed/`. When `run_with_continuation` in `issue_manager.py` triggers Option J and spawns a fresh guillotine session, that session starts with a transcript-summary prompt but has nothing to implement. It produces no output and never exits.

The same `implement_issue` / `go_no_go` / `implement_next` block is mirrored in `sprint-refine-and-implement.yaml` (noted in a YAML comment at line 49 of the auto-refine loop), so the same bug is present in both files.

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

Add a completion guard to the `implement_issue` action in both YAML files:

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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `implement_issue` state (line 101)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — mirrored `implement_issue` state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:162` — `run_with_continuation()` — Option J guillotine path that spawns the hung session
- `scripts/little_loops/loops/lib/common.yaml` — `with_rate_limit_handling` fragment used by `implement_issue`

### Similar Patterns
- `get_next_issue` state already skips issues via `ll-issues next-issue --skip` — the completion check is a complementary guard at the execute layer

### Tests
- `scripts/tests/` — add a test covering the completion guard scenario (issue already in `.issues/completed/` before `ll-auto --only` runs)

### Documentation
- N/A — no documentation references this FSM state behavior

### Configuration
- N/A — no configuration files affected

## Implementation Steps

1. Add a completion guard (`ls .issues/completed/*${ISSUE}* 2>/dev/null | grep -q .`) at the top of the `implement_issue` action in `auto-refine-and-implement.yaml`
2. Mirror the same guard in the `implement_issue` state of `sprint-refine-and-implement.yaml`
3. Verify the guard exits 0 and logs a message when the issue is already in `.issues/completed/`
4. Confirm the FSM advances to `implement_next` normally after the early exit

## Impact

- **Priority**: P2 — Blocks automated loop runs when Option J fires mid-implementation; discovered in a real loop run
- **Effort**: Small — Additive 4-line shell guard in two YAML state files; no Python changes required
- **Risk**: Low — Guard is purely additive; existing code paths when the issue is not yet completed are unchanged
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `automation`, `loops`, `captured`

## Status

**Open** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-05-09T22:33:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43665bb5-b08a-4083-80d6-5bfcdabc4d8c.jsonl`
- `/ll:capture-issue` - 2026-05-09T22:24:13Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efbb9709-7a24-4905-85fd-8a5a0825d700.jsonl`
