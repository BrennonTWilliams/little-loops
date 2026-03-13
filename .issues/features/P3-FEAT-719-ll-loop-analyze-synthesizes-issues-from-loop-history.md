---
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# FEAT-719: ll-loop analyze synthesizes issues from loop history

## Summary

Add a new `/ll:` skill (or `ll-loop analyze` subcommand) that finds the most recently run or interrupted loop via `ll-loop list --running`, loads its execution history with `ll-loop history <name>`, analyzes the results, and synthesizes actionable issues (bugs, enhancements, features) to create or update.

## Current Behavior

- `ll-loop history <name>` shows raw execution events for a named loop
- `ll-loop list --running` lists active/interrupted loops
- No tool bridges loop execution data into the issue tracker
- Users manually inspect history output and decide whether to file issues

## Expected Behavior

A new command/skill that:
1. Runs `ll-loop list --running` (and optionally `--status interrupted`) to find recent loops
2. Selects the most recent loop (or prompts if multiple candidates exist)
3. Runs `ll-loop history <name>` to retrieve execution events
4. Analyzes the history for: repeated failures, stuck states, unexpected terminations, performance anomalies, or improvement patterns
5. Synthesizes findings into issue proposals (BUG/ENH/FEAT) with context from the loop run
6. Creates new issues or updates existing ones via the standard issue lifecycle

## Motivation

Loop execution produces rich diagnostic data — failed states, retry counts, stall events, unexpected transitions — but that data is currently siloed in the history output and never feeds back into the issue tracker. Closing this loop (pun intended) makes automation failures self-documenting and turns loop runs into a source of continuous improvement rather than a black box.

## Proposed Solution

Create a new skill `ll:analyze-loop` (or extend `ll-loop` with an `analyze` subcommand) that:

1. Calls `ll-loop list --running --json` to enumerate candidates
2. Selects the most recent by timestamp (or last-modified state file)
3. Calls `ll-loop history <name> --verbose` and parses the event stream
4. Classifies events into issue signals:
   - `ERROR`/`SIGKILL` states → BUG candidates
   - Repeated retries on same state → ENH candidates (retry config, stall detection)
   - Successful but slow states → ENH candidates (performance)
   - Unexpected `next` routing on error → BUG candidates (FSM logic)
5. Deduplicates against existing active issues (same loop name + state)
6. Presents proposed issues to the user for confirmation
7. Calls `/ll:capture-issue` (or writes files directly) for approved issues

## Integration Map

### Files to Create
- `skills/analyze-loop/SKILL.md` — skill definition and invocation instructions
- `skills/analyze-loop/skill.py` (optional) — structured event parsing logic

### Files to Modify
- `scripts/little_loops/fsm/history.py` (or equivalent) — expose structured event access if needed
- `skills/capture-issue/SKILL.md` — no changes needed; skill is a consumer

### Similar Patterns
- `skills/loop-suggester/SKILL.md` — adjacent loop-analysis skill
- `skills/scan-codebase/SKILL.md` — same "analyze → propose issues" pattern
- `scripts/skills/analyze_log/SKILL.md` — analyzes log files for issues (closest analog)

### Tests
- `scripts/tests/` — mock `ll-loop list` and `ll-loop history` output, verify issue proposal logic

### Configuration
- No new config keys; respects existing `issues.*` settings for duplicate detection and templates

## Use Case

A developer runs a nightly `ll-loop run issue-fixer` loop. In the morning they run:
```
/ll:analyze-loop
```
The skill finds the interrupted `issue-fixer` loop, sees that state `verify` failed 3 times with SIGKILL before succeeding, and proposes BUG-720: "verify state killed by SIGKILL in issue-fixer loop". The developer approves and the bug is filed with the loop history snippet as context.

## API/Interface

```bash
# Skill invocation (auto-selects most recent loop)
/ll:analyze-loop

# Skill with explicit loop name
/ll:analyze-loop issue-fixer

# CLI subcommand alternative
ll-loop analyze
ll-loop analyze issue-fixer --tail 100
```

Expected output:
```
Analyzing loop: issue-fixer (last run: 2026-03-13 02:14)

Found 3 issue signals:

  [1] BUG P2 — verify state terminated by SIGKILL (3 occurrences)
  [2] ENH P3 — scan state retried 5x; consider raising retry limit
  [3] ENH P4 — fetch state avg 45s; caching may help

Create all 3 issues? [Y/n/select]
```

## Implementation Steps

1. Implement `ll-loop list --running --json` consumer to pick most recent loop
2. Parse `ll-loop history --verbose` output into structured event list
3. Define classification rules for issue signal types (SIGKILL, retry flood, slow state)
4. Deduplicate signals against active issues using title similarity
5. Render proposals table and collect user confirmation
6. Create/update issue files via `ll-issues` or direct file writes
7. Add `git add` staging for created/updated files
8. Write tests for event classification and deduplication logic

## Impact

- **Priority**: P3 - High-value diagnostics tool; low user friction to install
- **Effort**: Medium - Event parsing and classification are the main complexity
- **Risk**: Low - Read-only loop interaction; only creates/updates issue files
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `issue-management`, `captured`

## Status

**Open** | Created: 2026-03-13 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1bce590-015a-4862-aabe-11dcbf71a389.jsonl`
