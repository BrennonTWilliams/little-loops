---
id: BUG-3209
type: BUG
title: Automation skills spawn Agents with no blocking contract; headless turns can
  end with subagent results in flight
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:18Z'
---

# BUG-3209: Automation skills spawn Agents with no blocking contract; headless turns can end with subagent results in flight

## Summary

Five agent-spawning skills issue Agent/Task tool calls with no `run_in_background`
directive: `skills/audit-docs/SKILL.md`, `skills/audit-claude-config/SKILL.md`,
`skills/audit-issue-conflicts/SKILL.md`, `skills/confidence-check/SKILL.md`, and
`skills/wire-issue/SKILL.md`. The Agent tool defaults to background, so under a
headless `claude -p` turn (ll-auto, ll-parallel, ll-sprint, FSM prompt states) the
parent turn can end with subagent results still in flight — the completion
notification never arrives, exactly the failure mode BUG-3058 and the
manage-issue "Headless-Safe Final Test Run" section (`skills/manage-issue/SKILL.md:381-398`)
guard against for Bash test runs.

Nothing below the prompt layer compensates:

- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` (`host_runner.py:374`, documented at
  `host_runner.py:247`) is scoped to Bash `run_in_background`, not Agent-tool
  backgrounding — it never covered subagents, and ENH-3207 flipped it off by default.
- The process layer does not join: `subprocess_utils.py:600-645` stops reading on the
  stream-json `result` event, waits `post_stream_close_grace_seconds` (default 300,
  `config/automation.py:26`), then `_kill_process_group`. A still-running subagent is
  killed, not awaited — BUG-2718 raised that grace and BUG-2731 classifies the
  resulting exit 143 as INFRA_RETRY, but neither is a barrier.

Only two skills enforce blocking today: `skills/decide-issue/SKILL.md:335`
(`run_in_background: false`, waits in-turn) and `skills/go-no-go/SKILL.md:174,274`
(deliberately backgrounds, then relies on prose "wait until both have completed" with
no mechanical backstop).

Proposed fix: state the blocking contract once in the injected automation context
(when `LL_AUTOMATION=1`, every Agent spawn must be `run_in_background: false` and be
awaited in the same turn) rather than per-skill, and add the explicit directive to the
five silent skills. Consider whether go-no-go's intentional background fan-out should
be exempted or converted.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **File**: `path/to/file.py`
- **Anchor**: `in function buggy_func()`
- **Cause**: [Explanation of why bug happens]

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix


## Session Log
- `/ll:capture-issue` - 2026-08-16T02:10:51 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
