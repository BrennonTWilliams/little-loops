---
id: ENH-2064
title: verify-issues should skip deferred issues and only verify open active issues
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T21:28:15Z'
completed_at: '2026-06-09T22:07:02Z'
discovered_date: '2026-06-09'
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 82
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 22
score_change_surface: 25
decision_needed: false
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

`--format path` is an unrecognized argument — `ll-issues list` exits with error code 2 and produces no stdout output. As a result, verify-issues currently verifies **zero** issues. The intended behavior was to list all issues by frontmatter status, but no valid status filter is applied and the flag itself is invalid.

## Expected Behavior

Only issues with `status: open`, `status: in_progress`, or `status: blocked` should be included. Deferred, done, and cancelled issues should be silently skipped.

## Scope Boundaries

- **In scope**: Updating the `ll-issues list` call in `commands/verify-issues.md` Phase 1 to filter by active statuses (`open`, `in_progress`, `blocked`); updating the surrounding comment and help-text description.
- **Out of scope**: Changing what verify-issues checks per issue, modifying `ll-issues list` behaviour, adding status filtering to other commands (e.g. `format-issue`, `ready-issue`).

## Implementation Steps

1. In `commands/verify-issues.md`, update the Phase 1 shell snippet to filter by active statuses. Use `ll-issues list --json --status all` with a Python one-liner to extract absolute paths for active issues only:

   ```bash
   # List only active issues (open, in_progress, blocked) — skips deferred, done, cancelled
   ll-issues list --json --status all | \
     python3 -c "import json,sys; [print(i['path']) for i in json.load(sys.stdin) if i.get('status') in {'open','in_progress','blocked'}]" | \
     sort -u
   ```

   Note: `--format path` is not a supported flag; `--json` returns a JSON array where each entry includes a `path` field with the full absolute path. `--status` accepts single values only (no comma-separated list); `--status all` returns every issue regardless of status, enabling client-side filtering for the three active statuses.

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

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 76/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Current behavior is more broken than described — `ll-issues list --format path` is an unrecognized argument (exits non-zero, no stdout), so verify-issues currently verifies **zero** issues, not "includes deferred issues". The fix must restore functional issue-listing, not just add a status filter.

### Gaps to Address
- Correct the implementation steps: `--format path` is invalid; use `ll-issues list --json --status <s>` (confirmed: includes `path` field with full absolute paths) or `--flat --status <s>` + `ll-issues path`
- Remove the comma-separated `--status open,in_progress,blocked` option — single-value `--status` only (confirmed)
- Update current-behavior description to reflect the actual breakage

### Outcome Risk Factors
- **Resolve before starting**: two implementation options in the issue are both wrong (one uses invalid `--format path`, one uses unsupported comma-separated `--status`). Confirmed working form: `ll-issues list --json --status open` returns `path` field with full absolute path. Update implementation steps before coding.

## Session Log
- `/ll:manage-issue` - 2026-06-09T22:07:16 - `a12bd3d4-81d0-4675-94ca-bd47f1a3aa68.jsonl`
- `/ll:ready-issue` - 2026-06-09T22:05:17 - `e125722a-4a3e-46fb-b9bc-5adba3a69031.jsonl`
- `/ll:decide-issue` - 2026-06-09T21:58:31 - `aa990e7d-98c2-43b9-b091-b6f2f1777906.jsonl`
- `/ll:decide-issue` - 2026-06-09T21:48:26 - `62cd5994-9667-4e41-ae18-8c8318d67e92.jsonl`
- `/ll:format-issue` - 2026-06-09T21:40:05 - `aaaf9278-2b90-498b-bd12-a373a667efef.jsonl`
- `/ll:capture-issue` - 2026-06-09T21:28:15Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9ae3d06-f1c5-439f-bf3a-3e91da0365f2.jsonl`
- `/ll:confidence-check` - 2026-06-09T22:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9ae3d06-f1c5-439f-bf3a-3e91da0365f2.jsonl`
- `/ll:confidence-check` - 2026-06-09T23:00:00Z - `0be5a584-43c8-485e-b9ef-178e25fdb715.jsonl`
- `/ll:confidence-check` - 2026-06-09T23:30:00Z - `749387db-737f-4652-b13f-b958c8571cc0.jsonl`

---

## Status

**Current**: open
