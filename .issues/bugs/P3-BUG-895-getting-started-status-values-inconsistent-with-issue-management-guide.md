---
id: BUG-895
title: "GETTING_STARTED.md lists stale status values inconsistent with ISSUE_MANAGEMENT_GUIDE"
status: open
priority: P3
blocked_by: []
testable: false
confidence_score: 100
outcome_confidence: 75
---

## Summary

`GETTING_STARTED.md` documents a different set of issue `status` field values than the authoritative table in `ISSUE_MANAGEMENT_GUIDE.md`, leaving users with incorrect expectations about valid status values.

## Current Behavior

`docs/guides/GETTING_STARTED.md:178` says:
> The `status` field inside the issue file tracks where the issue is in the workflow: `open`, `backlog`, `active`, `in-progress`, `blocked`, or `completed`.

## Steps to Reproduce

1. Open `docs/guides/GETTING_STARTED.md`
2. Read the status values list at line 178
3. Compare with `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` lines 107–117
4. Observe: GETTING_STARTED lists `in-progress` and `blocked` which do not appear in the ISSUE_MANAGEMENT_GUIDE's canonical table

## Expected Behavior

The values should match the authoritative table in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`:

| Value | Meaning |
|-------|---------|
| `open` | Newly captured, not yet triaged |
| `backlog` | Triaged, queued for a later sprint |
| `active` | Currently being worked on |
| `completed` | Work finished and committed |
| `resolved` | Closed without a code change |
| `wont_do` | Decided not to implement |
| `superseded` | Replaced by another issue |

`in-progress` and `blocked` in GETTING_STARTED appear to be phase names from the lifecycle diagram (not frontmatter `status` values), and are not part of the ISSUE_MANAGEMENT_GUIDE's canonical table.

## Motivation

New users following `GETTING_STARTED.md` will attempt to set issue `status` to `in-progress` or `blocked`, then be confused when these values don't appear in the `ISSUE_MANAGEMENT_GUIDE.md` reference table. This creates a poor onboarding experience and erodes trust in the documentation. The fix is a single-sentence update with no code changes.

## Root Cause

`GETTING_STARTED.md` was not updated when the canonical status value set was finalized in `ISSUE_MANAGEMENT_GUIDE.md`. The `in-progress` and `blocked` values look like they were copied from the lifecycle workflow diagram rather than the frontmatter schema.

## Integration Map

### Files to Modify
- `docs/guides/GETTING_STARTED.md` — line 178, update the status values list to match the authoritative table

### Dependent Files (Callers/Importers)
- N/A — documentation-only change; no code imports these docs

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No other documentation files need updating. A codebase-wide search for `in-progress` and `blocked` as issue status values found that all occurrences outside `GETTING_STARTED.md` refer to FSM loop verdicts (`on_blocked`, route tables) or merge coordinator states — not issue frontmatter `status` values.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:105` explicitly notes: "The lifecycle diagram above shows conceptual workflow phases. The frontmatter `status` field uses a separate set of semantic values" — confirming the `in-progress`/`blocked` confusion stems from mixing lifecycle diagram phases with frontmatter field values.

### Tests
- N/A — no automated tests cover documentation prose

### Documentation
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — lines 107–117, the authoritative status value table (source of truth, read-only)

### Configuration
- N/A

## Implementation Steps

1. Confirmed: `scripts/little_loops/` has **no status validation code** — no enum, no `VALID_STATUS` constant, no frontmatter enforcement. `config-schema.json` also has no status enum. `ISSUE_MANAGEMENT_GUIDE.md:107–115` is solely the human/documentation-level canonical reference.
2. Update `GETTING_STARTED.md:178` — replace the existing sentence with one that lists the correct set: `open`, `backlog`, `active`, `completed`, `resolved`, `wont_do`, `superseded`
3. The replacement sentence should mirror the phrasing already in the file but remove `in-progress` and `blocked`; refer readers to `ISSUE_MANAGEMENT_GUIDE.md` for the full table.

## Impact

**Priority**: P3 — Medium
**Effort**: Low (single sentence change)
**Risk**: Low
**Breaking Change**: No

New users reading GETTING_STARTED will expect `in-progress` and `blocked` to be valid status values and be confused when they don't appear in the authoritative reference.

## Labels

`documentation`, `consistency`, `captured`

## Status

**Open** | Captured: 2026-03-26 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-03-26T21:15:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/184fd12a-1de3-4eba-9d21-0c994ea1a12d.jsonl`
- `/ll:format-issue` - 2026-03-26T21:09:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09734997-4b5e-4d15-a3cc-89e8eb882723.jsonl`
- `/ll:confidence-check` - 2026-03-26T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57cbeb51-65cf-4d20-9547-cc7a5990b7a5.jsonl`
