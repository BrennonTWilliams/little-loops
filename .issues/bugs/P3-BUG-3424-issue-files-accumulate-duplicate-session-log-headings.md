---
id: BUG-3424
type: BUG
title: Issue files accumulate duplicate Session Log headings
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T19:37:59Z'
---

# BUG-3424: Issue files accumulate duplicate Session Log headings

## Summary

54 issue files under `.issues/` at HEAD contain two or more line-anchored `## Session Log` H2 headings. The session-log readers in `scripts/little_loops/session_log.py` (`session_log_body`, `parse_session_log`, `count_session_commands`, `last_command_timestamp`) read only the **last** non-fenced section, so every entry in an earlier block is invisible to them — stale-refine detection, per-command timestamps, and command counts all under-report on those files.

Two observed shapes produce the duplicate:

1. **LLM hand-append at EOF.** A command pass writes `\n\n## Session Log\n- <entry>` at end of file even though a `## Session Log` heading already exists earlier. Reproduced in commit 98dbbaf83 on ENH-3423: the `/ll:verify-issues --auto` pass inserted `## Verification Notes` above the existing Session Log, then started a fresh `## Session Log` at EOF for its own entry. The manual-fallback instruction in `commands/verify-issues.md` section 4.5 (mirrored in `skills/capture-issue/SKILL.md:292`, `skills/decide-issue/SKILL.md:452`, `commands/scan-codebase.md:314`, `commands/ready-issue.md:365`) tells the model how to format the entry and where to put a *new* heading, but never says to reuse an existing heading when one is present.
2. **Post-Resolution restart.** In 7 of 12 sampled duplicate files the second heading immediately follows a `## Resolution` block. The Resolution templates in `scripts/little_loops/issue_lifecycle.py:355-415` and `scripts/little_loops/parallel/orchestrator.py:1960-1985` are appended at EOF *below* the existing Session Log, and a later pass then opened a new Session Log under the Resolution footer instead of returning to the original heading.

`append_session_log_entry` (`scripts/little_loops/session_log.py:281-343`) is **not** the writer at fault: it correctly finds the last fence-excluded, line-anchored heading (BUG-3202) and inserts under it. But it silently tolerates a duplicate and keeps feeding only the last block, so the file never self-heals and the earlier entries stay orphaned.

## Proposed fix

- (a) In `append_session_log_entry`, when more than one non-fenced `## Session Log` heading exists, merge every section's entries into a single block (preserving entry order, first heading's position) before inserting the new entry — so any subsequent `ll-issues append-log` repairs the file.
- (b) Tighten every manual-fallback instruction listed above to: "append under the existing `## Session Log` heading if one exists; create the heading only when none does."
- (c) One-shot normalization of the 54 existing files, either via `/ll:normalize-issues` or a new `ll-issues` subcommand that reuses the merge logic from (a).
- (d) Regression test: start from a fixture with two `## Session Log` blocks (one above a `## Resolution` footer, one below), call `append_session_log_entry`, assert exactly one heading remains with all prior entries plus the new one preserved in order.

## Relationships

- ENH-3423 documents this pattern as out of scope for its own fix.
- BUG-3202 (line-anchored heading match) and BUG-3150 (append lock) are the prior fixes in the same function; this extends, not reverts, them.


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
- `/ll:capture-issue` - 2026-09-09T19:38:06 - `43a86a4b-030b-4f3d-98cb-3c4b4bf26ccd.jsonl`
