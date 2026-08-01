---
id: ENH-2939
title: Delete session-log JSONL-hunting prose in favor of ll-issues append-log
type: ENH
priority: P1
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
program_design_not_applicable: true
relates_to:
- ENH-2950
- ENH-2952
labels:
- skills
- cleanup
- determinism
---

# ENH-2939: Delete session-log JSONL-hunting prose in favor of `ll-issues append-log`

## Summary

Markdown-only cleanup (no Python changes) removing prose that duplicates an existing CLI, and establishing the session-log convention the rest of EPIC-2938 adopts. Cheapest child; do first.

**Descoped after review** (2026-07-31), because neither remaining item fit a markdown-only issue:

- decide-issue's option-detection prose → **ENH-2950**. It cannot delegate to `ll-issues check-decidable`: that command is exit-code only (`locate_enumerable_options` returns just `(count, heading)`), while Phase 3b *materializes* `**Option A**`/`**Option B**` blocks into the file. Delegating requires widening the locator's return shape — a Python change.
- the 17-site flag-parse block → **ENH-2952**. The consolidation is not obviously a net context win and needs measurement first; bundling it would have blocked this sweep.

## Current Behavior

**Session-log JSONL hunting**: 7 files (`audit-claude-config`, `capture-issue`, `confidence-check`, `go-no-go`, `issue-size-review`, `manage-issue`, `scope-epic`) instruct the LLM to find the current session log by scanning `~/.claude/projects/` for the dash-encoded project dir and the most recently modified `.jsonl`. 11 other files already call `ll-issues append-log` or `little_loops.session_log.append_session_log_entry` — so the convention exists and these 7 are the stragglers.

## Expected Behavior

All 7 JSONL-hunting blocks replaced with `ll-issues append-log <issue_path> "<command>"` (or a one-line pointer to `little_loops.session_log.append_session_log_entry` where a path-only variant is needed). No skill or command instructs scanning `~/.claude/projects/`.

## Proposed Solution

Pure markdown edits. Reuse points: `ll-issues append-log`, `scripts/little_loops/session_log.py::append_session_log_entry`.

## Implementation Steps

1. Sweep the 7 session-log files; replace hunt-prose with the CLI/helper call.
2. Run `ll-verify-skills` and `python -m pytest scripts/tests/` (no behavior change expected).

## Acceptance Criteria

- [ ] No skill/command instructs scanning `~/.claude/projects/` for session JSONL files
- [ ] All 7 files call `ll-issues append-log` (or the `session_log` helper where a path-only variant is needed)
- [ ] `ll-verify-skills` passes; `python -m pytest scripts/tests/` green
- [ ] Net markdown reduction recorded in the PR/commit description

## Program Design

### Types

- N/A — markdown-only change; no Python types added or modified

### Signatures

Existing surfaces consumed (unchanged):
- `ll-issues append-log <issue_path> <log_command>`
- `little_loops.session_log.append_session_log_entry(...)`

## Scope Boundaries

- In scope: prose deletion/replacement in the 7 session-log files.
- Out of scope: any Python/CLI changes; decide-issue option detection (ENH-2950); the flag-parse block (ENH-2952).

## Impact

- **Priority**: P1 - Cheapest child; sets the session-log convention the rest of EPIC-2938 adopts
- **Effort**: Small - Markdown edits only, 7 files
- **Risk**: Low - No behavior change; verified by ll-verify-skills + existing tests

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Notes

Originally scoped as three sweeps; items 1 and 3 were split to ENH-2950 and ENH-2952 respectively after review found neither could be done markdown-only.
