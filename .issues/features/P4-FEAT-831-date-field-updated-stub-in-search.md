---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 93
outcome_confidence: 79
---

# FEAT-831: `--date-field=updated` stub in `ll-issues search`

## Summary

The `--date-field` argument in `ll-issues search` advertises `choices=["discovered", "updated"]`, but the `"updated"` branch silently falls back to `discovered_date`. The comment in code explicitly states: `"updated" not stored; fall back to discovered_date`.

## Location

- **File**: `scripts/little_loops/cli/issues/search.py`
- **Line(s)**: 240-246 (at scan commit: 8c6cf90)
- **Anchor**: `in function _load_issues_with_status`, `cmd_search`
- **Code**:
```python
date_field = getattr(args, "date_field", "discovered")
if date_field == "discovered":
    ref_date = disc_date
else:
    # "updated" not stored; fall back to discovered_date
    ref_date = disc_date
```

## Current Behavior

`--date-field=updated` is accepted by the CLI but behaves identically to `--date-field=discovered`. Users are misled into thinking they're filtering by last update date.

## Expected Behavior

Either implement the `updated` date (e.g., from the last Session Log entry or file mtime) or remove the `"updated"` choice from the CLI until it's implemented.

## Use Case

A developer wants to find issues that were last worked on within the past week. They run `ll-issues search --date-field=updated --since 2026-03-12` expecting to see recently-touched issues, but get results based on discovery date instead.

## Acceptance Criteria

- [ ] `--date-field=updated` uses an actual last-modified date (file mtime or last session log entry)
- [ ] OR: Remove `"updated"` from `choices` and document it as a future feature

## Proposed Solution

Derive the updated date from the last `## Session Log` entry timestamp, or fall back to `os.path.getmtime()` on the issue file. The Session Log approach is more semantically meaningful.

## Impact

- **Priority**: P4 - Advertised but non-functional CLI option; misleading behavior
- **Effort**: Small - Parse last session log timestamp or use file mtime
- **Risk**: Low - Fixes existing stub; no new API surface
- **Breaking Change**: No (changes behavior of a currently-broken option)

## Labels

`feature`, `cli`, `issues`

## Status

**Open** | Created: 2026-03-19 | Priority: P4

## Verification Notes

- **Verdict**: VALID
- **Verified**: 2026-03-19
- **File exists**: Yes — `scripts/little_loops/cli/issues/search.py`
- **Line numbers**: Accurate — code block at lines 240–246 matches exactly
- **Code snippet**: Confirmed — `date_field == "discovered"` branch and `else` branch both assign `ref_date = disc_date`, with comment `# "updated" not stored; fall back to discovered_date`
- **CLI choices**: Confirmed — `choices=["discovered", "updated"]` at `scripts/little_loops/cli/issues/__init__.py:167`
- **Minor inaccuracy**: Anchor says `in function _load_issues_with_status` but the code lives in `cmd_search` (line 149). Does not affect validity.

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:26:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
