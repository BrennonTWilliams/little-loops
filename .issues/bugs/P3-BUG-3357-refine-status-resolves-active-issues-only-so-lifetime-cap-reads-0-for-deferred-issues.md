---
id: BUG-3357
type: BUG
title: refine-status resolves active issues only, so lifetime cap reads 0 for deferred
  issues
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T23:26:59Z'
---

# BUG-3357: refine-status resolves active issues only, so lifetime cap reads 0 for deferred issues

## Summary

`ll-issues refine-status` resolves IDs against the *active* issue set only, unlike every other `ll-issues` probe used by the refinement loops, which resolve any status.

## Current Behavior

`cli/issues/refine_status.py` uses `find_issues(config)` (active issues only) and, when the positional ID is not in that set, prints `Error: issue '<id>' not found in active issues.` — to **stdout** — and exits 1. Every sibling probe in `refine-to-ready-issue.yaml` (`check-flag`, `check-verify-verdict`, `check-open-questions`, `check-acceptance-criteria`, `check-design`, `show`) resolves via `resolve_issue_path`, which finds issues regardless of status.

Consequence in `refine-to-ready-issue.yaml` `check_lifetime_limit`: for a deferred (or otherwise non-active) issue, the `refine-status ... --json | python3 -c ...` pipeline swallows the failure and reads `refine_count: 0`, so the lifetime cap silently never fires for exactly the issues most likely to have burned refine budget before being deferred.

## Expected Behavior

`refine-status <id>` resolves any status (mirror `resolve_issue_path` semantics), or at minimum exits with a distinct code and stderr (not stdout) so callers can discriminate "not found" from "count 0". The `--json` no-ID listing mode may reasonably stay active-only.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml`.

## Status

**Open** | Created: 2026-08-28 | Priority: P3
