---
id: BUG-1647
type: BUG
priority: P2
status: open
captured_at: 2026-05-23T22:24:46Z
discovered_date: 2026-05-23
discovered_by: capture-issue
---

# BUG-1647: `ll-issues search --sort created --desc` Returns Oldest Issues at Top

## Summary

`ll-issues search --sort created --desc --limit 3` returns OLD issues at the top instead of the most recently captured ones. Two interacting defects: (1) the missing-date sentinel in `_sort_issues()` is `datetime.max`/`date.max`/`9999`, which sorts to the TOP under `--desc`, masking the real newest issues; (2) 223 of 1556 issues have neither `captured_at` nor `discovered_date` because two Python writers (`sync.py::_create_local_issue` and `issue_lifecycle.py::create_issue_from_failure`) don't populate creation timestamps in frontmatter — those 223 are exactly the rows that bubble to the top.

FEAT-1180 (done 2026-04-18) added `captured_at`-preferred read logic, but did not address direction-aware sentinels or writer gaps.

## Current Behavior

```
$ ll-issues search --sort created --desc --limit 3
# Top rows are old issues with no captured_at/discovered_date,
# not the most recently captured ones (BUG-1645, ENH-1644, etc.).
```

- `_sort_issues()` in `scripts/little_loops/cli/issues/search.py` (~line 215) uses fixed-max sentinels (`datetime.max`, `date.max`, `9999`) for missing values, which sort to the TOP under `--desc`.
- Same pattern affects `comp_date`, `confidence_score`, and `outcome_confidence` keys.
- Of 1556 issues: 181 have `captured_at`, 1332 have only `discovered_date`, and 223 have NEITHER.
- The 223 timestamp-less issues come from:
  - `_create_local_issue()` at `scripts/little_loops/sync.py:655` — writes only `discovered_date` (no `captured_at`).
  - `create_issue_from_failure()` at `scripts/little_loops/issue_lifecycle.py:408` — writes NO frontmatter at all (only body markdown including a "Created: …" line).

## Expected Behavior

`ll-issues search --sort created --desc` shows the most recently captured issues at the top. `--asc` shows the oldest at the top. Issues missing a creation timestamp sort to the END in either direction (never the top), and future issues created via `sync.py` / `issue_lifecycle.py` always have `captured_at` in frontmatter.

## Motivation

`ll-issues search --sort created --desc` is the canonical way to confirm a just-captured issue landed in the backlog — it's used during capture workflows, after `ll-sync pull`, and whenever a user wants to see what's freshest. Today it surfaces the 223 timestamp-less rows (~14% of issues) at the top instead, so users may reasonably conclude their recent capture failed or got mis-routed and re-run the capture, file a duplicate, or lose trust in the sort. The writer-side gap also keeps growing the broken cohort with every `sync.py::_create_local_issue` and `issue_lifecycle.py::create_issue_from_failure` invocation, so the read-side workaround alone isn't enough — both ends need fixing to stop the bleeding and restore correct "newest first" ordering.

## Steps to Reproduce

1. `cd` into the little-loops repo (which has the 223 timestamp-less issues).
2. Run `ll-issues search --sort created --desc --limit 5`.
3. Observe: top rows are old issues (no `captured_at` / `discovered_date`), not the most recently captured (BUG-1645, ENH-1644, ENH-1646, etc.).

## Root Cause

- **File**: `scripts/little_loops/cli/issues/search.py`
- **Anchor**: `_sort_issues()` (~line 215) and `_parse_discovered_date()` (~line 21)
- **Cause**: Missing-value sentinels are direction-agnostic — they always use the MAX value, which sorts to the top under `--desc`. Combined with 223 issues that have no creation timestamp (from writers that don't populate `captured_at`), the result is that the "newest" sort actually surfaces the oldest rows.

Also at the writer side:
- **File**: `scripts/little_loops/sync.py`
- **Anchor**: `_create_local_issue()` lines 655–750 (computes `now` at line 693 but only uses it for `last_synced`).
- **Cause**: Doesn't write `captured_at` into frontmatter.

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `create_issue_from_failure()` lines 408–505.
- **Cause**: Writes raw markdown body with no YAML frontmatter at all.

## Proposed Solution

### 1. Direction-aware sentinel — `scripts/little_loops/cli/issues/search.py::_sort_issues`

Make the missing-value sentinel direction-aware so unknowns always sort to the END regardless of `--desc` / `--asc`:

```python
def key(item):
    ...
    if sort_field in ("date", "created"):
        sentinel = datetime.min if descending else datetime.max
        return (disc_date or sentinel,)
    if sort_field == "completed":
        sentinel = date.min if descending else date.max
        return (comp_date or sentinel,)
    if sort_field == "confidence":
        sentinel = -1 if descending else 9999
        return (issue.confidence_score if issue.confidence_score is not None else sentinel,)
    if sort_field == "outcome":
        sentinel = -1 if descending else 9999
        return (issue.outcome_confidence if issue.outcome_confidence is not None else sentinel,)
```

### 2. File mtime fallback in `_parse_discovered_date()`

Change the signature to accept the file path and, when both `captured_at` and `discovered_date` are missing, fall back to `file_path.stat().st_mtime` converted to a naive `datetime`. Update the single call site (~line 319) to pass `issue.path`. `_parse_updated_date()` (line 53) already demonstrates the same mtime fallback pattern with `try/except OSError` — match its shape.

This guarantees every issue has a usable sort key today, without needing to mutate the 223 files.

### 3. Writer audit — populate `captured_at` in both Python issue creators

**`scripts/little_loops/sync.py::_create_local_issue` (lines 655–750)**
Already computes `now` at line 693. Add `"captured_at": now` to the frontmatter dict alongside the existing `discovered_date` (keep `discovered_date` for backward compat with anything that reads it).

**`scripts/little_loops/issue_lifecycle.py::create_issue_from_failure` (lines 408–505)**
Add a YAML frontmatter block at the top of the assembled content containing at minimum: `status: open`, `priority: …`, `captured_at: {_iso_now()}`, and any other fields the rest of the system expects (`IssueInfo` / `parse_frontmatter` rely on `status` for the canonical-status check). Reuse the existing `_iso_now()` helper at `issue_lifecycle.py:28` — do NOT introduce a new helper.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/search.py` — direction-aware sentinel in `_sort_issues()`; mtime fallback in `_parse_discovered_date()`
- `scripts/little_loops/sync.py` — `_create_local_issue()` adds `captured_at`
- `scripts/little_loops/issue_lifecycle.py` — `create_issue_from_failure()` writes frontmatter (with `captured_at`, `status`, `priority`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/list_cmd.py` — imports `_parse_discovered_date` and `_sort_issues` from `search.py`; signature change to `_parse_discovered_date` will ripple to its call site (verify and update)

### Similar Patterns
- `_parse_updated_date()` at `search.py:53` already uses the mtime fallback pattern — mirror its shape for consistency

### Tests
- `scripts/tests/cli/issues/test_search.py` (or equivalent — grep for `_sort_issues` / `cmd_search`) — new cases for sentinel direction (see Tests section)
- `scripts/tests/test_sync.py` — new test asserting `_create_local_issue` writes parseable `captured_at`
- `scripts/tests/test_issue_lifecycle.py` — new test asserting `create_issue_from_failure` writes frontmatter with `captured_at` + `status: open`

### Documentation
- N/A — output format unchanged; sentinel/mtime are implementation details

### Configuration
- N/A

## Implementation Steps

1. Fix sentinel direction in `_sort_issues()` for `date`/`created`, `completed`, `confidence`, `outcome` keys.
2. Add file-path parameter and mtime fallback to `_parse_discovered_date()`; update its single call site.
3. Add `captured_at` to `sync.py::_create_local_issue` frontmatter.
4. Add YAML frontmatter (with `captured_at`, `status: open`, `priority`) to `issue_lifecycle.py::create_issue_from_failure`.
5. Add tests for sort direction, sentinel placement, mtime fallback, and both writer paths.
6. Verify: `ll-issues search --sort created --desc --limit 5` shows BUG-1645, ENH-1644, ENH-1646, BUG-1647 at top (or whatever the current freshest captures are).

## Impact

- **Priority**: P2 — Core CLI sort returns misleading results that actively hide newly captured issues; users sorting `--desc` may believe their recent captures didn't land. Not P1 only because there is a workaround (manually scan, or use `git status` for very recent issues).
- **Effort**: Small–Medium — focused changes in three files plus tests; pattern (mtime fallback) already exists in the same module.
- **Risk**: Low — read-side sentinel change is well-contained; writer additions only ADD fields (no field removed); existing tests should catch regressions.
- **Breaking Change**: No — output format unchanged; only ordering of timestamp-less issues changes (top → bottom).

## Tests

- `--sort created --desc` with a mix of issues — one with `captured_at`, one with `discovered_date`, one with neither — verify ordering is `captured_at` > `discovered_date` > mtime-fallback (or as fixture mtimes dictate).
- `--sort created --asc` with the same mix — verify missing-date issues sort LAST, not first.
- `--sort confidence --desc` and `--sort completed --desc` with missing values — verify they sort last.
- `sync.py::_create_local_issue` — assert the written file's frontmatter contains a parseable `captured_at`.
- `issue_lifecycle.py::create_issue_from_failure` — assert the written file has frontmatter with `captured_at` and `status: open`.

## Out of Scope

- Backfilling `captured_at` into the 223 existing files. The mtime fallback handles them at read time; a one-time migration would mutate ~14% of issue files for marginal benefit and can be filed as a separate optional issue (`ENH-…-backfill-captured-at-from-mtime`) if desired.
- Removing `discovered_date` in favor of `captured_at`. Keep both — `sync.py` still pulls `discovered_date` from GitHub, and 1332 existing files use it.

## Verification

```bash
# 1. Sort fix works against current repo
ll-issues search --sort created --desc --limit 5
# → top rows should be the most recently captured (BUG-1645, ENH-1644, etc.)
#   not the 223 timestamp-less ones

# 2. Ascending still works
ll-issues search --sort created --asc --limit 5
# → top rows should be the oldest captured

# 3. Writer fix — sync path: unit-test verifies new file has captured_at
# 4. Writer fix — failure path: unit-test verifies create_issue_from_failure output
# 5. Full suite
python -m pytest scripts/tests/ -k "search or sort or sync or lifecycle" -v
```

## Related

- FEAT-1180 (done) — added `captured_at`-preferred read logic in `_parse_discovered_date`; this bug is a follow-up addressing sentinel direction and writer-side gaps that were out of scope there.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `cli`, `sorting`, `ll-issues`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-23T22:29:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a14dcc8c-8173-4ee8-9e95-97fd610a6f26.jsonl`
- `/ll:capture-issue` - 2026-05-23T22:24:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04d83e92-8a0d-4374-ac0b-80222c2a5b59.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2
