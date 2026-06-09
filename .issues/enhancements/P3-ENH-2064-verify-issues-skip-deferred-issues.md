---
id: ENH-2064
title: "verify-issues should skip deferred issues and only verify open active issues"
type: ENH
priority: P3
status: open
captured_at: "2026-06-09T21:28:15Z"
discovered_date: "2026-06-09"
discovered_by: capture-issue
---

# ENH-2064: verify-issues should skip deferred issues and only verify open active issues

## Summary

The `/ll:verify-issues` command currently passes `ll-issues list --format path` without a status filter, which includes deferred, cancelled, and done issues alongside open ones. Deferred issues are intentionally parked and should not be verified until they are re-activated. Running verification on them wastes time, generates noise, and may produce misleading OUTDATED verdicts for issues that are on hold by design.

## Motivation

Deferred issues are parked by intent — they represent future work that is not currently actionable. Verifying them:
- Generates unnecessary OUTDATED noise for stale-by-design issues
- Wastes LLM calls on issues that won't be actioned
- Confuses the verification report by mixing active and inactive issues

The fix aligns `verify-issues` with the intent of the status field and produces a cleaner, more useful report.

## Current Behavior

`commands/verify-issues.md` (Phase 1, "Find Issues to Verify"):

```bash
# List all open issues (by frontmatter status)
ll-issues list --format path | sort
```

The comment says "by frontmatter status" but no `--status` flag is passed, so `ll-issues list` returns all issues regardless of status (open, deferred, done, cancelled).

## Expected Behavior

Only issues with `status: open`, `status: in_progress`, or `status: blocked` should be included. Deferred, done, and cancelled issues should be silently skipped.

## Scope Boundaries

- **In scope**: Updating the `ll-issues list` call in `commands/verify-issues.md` Phase 1 to filter by active statuses (`open`, `in_progress`, `blocked`); updating the surrounding comment and help-text description.
- **Out of scope**: Changing what verify-issues checks per issue, modifying `ll-issues list` behaviour, adding status filtering to other commands (e.g. `format-issue`, `ready-issue`).

## Implementation Steps

1. In `commands/verify-issues.md`, update the Phase 1 shell snippet to filter by active statuses:

   ```bash
   # List only active issues (open, in_progress, blocked)
   { ll-issues list --status open --format path; \
     ll-issues list --status in_progress --format path; \
     ll-issues list --status blocked --format path; } | sort -u
   ```

   Or, if `ll-issues list` supports comma-separated status values or multiple `--status` flags:

   ```bash
   ll-issues list --status open,in_progress,blocked --format path | sort
   ```

   Verify which form `ll-issues list` accepts before choosing.

2. Update the surrounding comment to match:
   ```
   # List all active issues (open, in_progress, blocked) — skips deferred, done, cancelled
   ```

3. Update the command's description/help text (the argument block at the top of the file) to mention that deferred issues are excluded.

## API/Interface

N/A — No public Python API changes. The fix is a 1-2 line shell snippet change inside `commands/verify-issues.md`.

## Verification

- Run `ll-issues list --status deferred --format path` and confirm none of those paths appear in the `verify-issues` run.
- Run `/ll:verify-issues` and confirm the output count matches `ll-issues list --status open --format path | wc -l` (plus in_progress/blocked).

## Impact

- **Priority**: P3 — Minor quality-of-life fix; deferred issues are rare but their inclusion generates misleading OUTDATED noise in verification reports.
- **Effort**: Small — 1-2 line shell snippet change plus a comment/help-text update.
- **Risk**: Low — Purely additive (narrower filter); does not alter verification logic or output format.
- **Breaking Change**: No

## Labels

`enhancement`, `ux`

## Session Log
- `/ll:format-issue` - 2026-06-09T21:40:05 - `aaaf9278-2b90-498b-bd12-a373a667efef.jsonl`
- `/ll:capture-issue` - 2026-06-09T21:28:15Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9ae3d06-f1c5-439f-bf3a-3e91da0365f2.jsonl`

---

## Status

**Current**: open
