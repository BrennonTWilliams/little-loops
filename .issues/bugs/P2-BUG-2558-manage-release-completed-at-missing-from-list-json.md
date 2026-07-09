---
id: BUG-2558
title: "manage-release reports 0 completed issues — ll-issues list --json omits completed_at (ENH-1421 regression of BUG-942)"
type: BUG
priority: P2
status: done
captured_at: '2026-07-09T03:40:00Z'
completed_at: '2026-07-09T03:45:00Z'
discovered_date: '2026-07-09'
discovered_by: user-report
relates_to:
  - BUG-942
  - ENH-1421
labels:
  - manage-release
  - json-contract
  - regression-guard
  - changelog
confidence_score: 100
outcome_confidence: 95
---

# BUG-2558: manage-release reports 0 completed issues — `ll-issues list --json` omits `completed_at`

## Summary

`/ll:manage-release` reports **"0 completed issues since last release"** on every
release, even when many issues were completed since the last tag (observed during
`v1.140.0`: FEAT-2551/2552/2413, ENH-2418, BUG-2547, … were all missed).

## Root Cause

`commands/manage-release.md` Agent 2 filtered completed issues with:

```python
ll-issues list --status done --json | python3 -c "
data = json.load(sys.stdin)
prev_ts = '$(echo ${PREV_TIMESTAMP})'
results = [i for i in data if i.get('completed_at', '') >= prev_ts]"
```

But `ll-issues list --json` **never emitted a `completed_at` key**
(`scripts/little_loops/cli/issues/list_cmd.py`; `IssueInfo` has no
`completed_at` field, and the JSON dict dropped the already-computed
`comp_date`). The filter was therefore always `'' >= <timestamp>` → `False` →
**0 results, regardless of baseline tag.** Reproduced: 2318 done issues, 0 with a
`completed_at` key.

### Regression history

- **BUG-942** (done 2026-04-03, commit `6fd22e10`) fixed the same symptom using
  `git log --diff-filter=A ... -- .issues/completed/`.
- **ENH-1421** ("decouple issue status from directory structure", commit
  `0c623c09`) removed that fix — correctly, since `.issues/completed/` no longer
  exists — but replaced it with the broken `completed_at`-from-JSON filter,
  silently re-introducing BUG-942.

### Contributing data gap

`ll-issues set-status <id> done` (`cli/issues/set_status.py`) wrote only
`{"status": ...}` and never stamped `completed_at`, so manually-completed issues
had no timestamp at all (155/2272 done issues affected).

## Resolution

**Fixed**: 2026-07-09

1. `list_cmd.py` now emits `completed_at` in `--json` (frontmatter + Resolution
   parse via `_parse_completion_date(..., batch_dates={})` — no per-file git
   subprocess). Day-granularity ISO date or `null`.
2. `commands/manage-release.md` Agent 2 filter compares on **date** (not fragile
   lexical strings across mixed tz offsets), and Wave-2 synthesis gained a
   **loud empty-result guard** so a future double-zero is surfaced, not shipped.
3. `set_status.py` stamps `completed_at` on `done` (and cascade-to-done),
   matching the lifecycle/parallel/sync paths.
4. Regression tests: `test_json_output_contracts.py` (contract now requires
   `completed_at`; reproduces the manage-release filter) and
   `test_set_status_cli.py` (done stamps completed_at; non-terminal does not).
5. `docs/reference/json-output-contracts.md` documents the new field (additive,
   non-breaking).

Verified end-to-end: the hardened filter now finds 26 issues completed since
`v1.139.0` (previously 0). Full suite: `python -m pytest scripts/tests/` → 14405
passed.

## Impact

- **Priority**: P2 — changelog automation silently produced empty release notes.
- **Effort**: Small — one CLI field + one command prompt + a data-gap close.
- **Risk**: Low — additive JSON field; isolated command-prompt change.
- **Breaking Change**: No.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T03:41:18 - `11b4a990-6665-4782-a360-644029312fa4.jsonl`
