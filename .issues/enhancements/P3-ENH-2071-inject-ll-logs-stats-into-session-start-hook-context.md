---
id: ENH-2071
title: Inject ll-logs stats into session_start hook context
type: ENH
priority: P3
status: open
discovered_date: "2026-06-10"
discovered_by: capture-issue
captured_at: "2026-06-10T15:59:33Z"
labels: [ll-logs, session-start, telemetry, hooks, correction-rate]
parent: EPIC-1918
relates_to: [EPIC-1918]
---

# ENH-2071: Inject ll-logs stats into session_start hook context

## Summary

The session_start hook already injects a `project_context` block (recently touched files, recent corrections, recently completed issues). It does not include skill-level correction-rate signals from `ll-logs stats`. Adding a compact stats summary surfaces patterns like `audit-loop-run` sitting at 20% correction rate — the kind of signal that should inform every session without requiring a manual query.

## Current Behavior

The `session_start` hook assembles a `project_context` block containing recently-touched files, recent corrections, and recently-completed issues. Correction-rate data from `ll-logs stats` is not included — it is only accessible by running `ll-logs stats` manually outside a session.

## Expected Behavior

The `session_start` hook output includes a `## Skill Signals (30d)` block when `.ll/history.db` is present and has data. Skills with `correction_rate > 5%` are visually flagged (e.g., `← flag` suffix). The block is silently absent (no error, no empty section) when `history.db` is missing or `ll-logs stats` exits non-zero. The block is capped at 15 lines regardless of catalog size.

## Motivation

Correction-rate data is the most direct signal that a skill is under-performing. Currently that signal only surfaces if someone runs `ll-logs stats` manually. Injecting a compact version into session context makes it ambient — the harness can self-improve faster because every session starts with awareness of where it's failing.

## Implementation Steps

1. **In `session_start` Python handler** (`scripts/little_loops/hooks/session_start.py` or equivalent), after the existing `project_context` assembly:
   - Run `ll-logs stats --project . --window-days 30 -j` (subprocess, timeout 5s, silent on error)
   - Filter to skills where `correction_rate > 0.05` OR `invocations >= 20` (the high-volume hot path)
   - Format as a compact table (max 10 rows) under a `## Skill Signals` subsection
2. **Cap output**: if the table would exceed ~400 chars, truncate to top-5 by correction rate and add "…N more" note
3. **Guard on `history.db` existence**: if `.ll/history.db` is absent or `ll-logs stats` exits non-zero, skip the section silently
4. **Format**:
   ```
   ## Skill Signals (30d)
   confidence-check: 221 calls, 0% corrections
   audit-loop-run: 5 calls, 20% corrections ← flag
   capture-issue: 34 calls, 3% corrections
   ```

## API / Interface

New key in the `project_context` dict passed to the session_start template:

```python
"skill_signals": [
    {"skill": "audit-loop-run", "invocations": 5, "correction_rate": 0.20},
    ...
]
```

## Scope Boundaries

- Does not include automated remediation or alerts based on correction signals
- Does not surface historical trending or time-series charts (single 30d window only)
- Does not modify or re-rank the skills being surfaced
- Does not pull stats from providers other than `ll-logs stats`
- Does not add a new CLI subcommand; change is internal to the `session_start` handler

## Impact

- **Priority**: P3 - Useful telemetry improvement; non-blocking, no user-facing workflow changes
- **Effort**: Small - Adds one subprocess call and a compact formatter to the existing `session_start` handler; no new modules or schema changes needed
- **Risk**: Low - Read-only subprocess call, guarded by silent-on-error; no behavioral change when stats are unavailable
- **Breaking Change**: No

## Acceptance Criteria

- Session_start output includes `## Skill Signals` block when `history.db` is present and has data
- Skills with correction_rate > 5% are visually flagged (e.g., `← flag` suffix or bolded)
- Block is absent (no error, no empty section) when `history.db` missing or `ll-logs stats` fails
- Block does not exceed 15 lines regardless of catalog size

## Session Log
- `/ll:format-issue` - 2026-06-10T16:05:17 - `d19c37d7-acef-4974-bf90-d673d4b0ec70.jsonl`

- `/ll:capture-issue` - 2026-06-10T15:59:33Z - surfaced via conversation analysis; `audit-loop-run` 20% correction rate was invisible until manually running `ll-logs stats`
