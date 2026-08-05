---
id: BUG-3055
title: Work-verification diagnostics print a full count beside a silently truncated
  list
type: BUG
priority: P4
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-05
captured_at: '2026-08-05T05:42:22Z'
completed_at: '2026-08-05T05:42:22Z'
relates_to:
- BUG-3054
- BUG-3058
labels:
- automation
- logging
- diagnostics
---

# BUG-3055: Work-verification diagnostics print a full count beside a silently truncated list

## Summary

`_detect_meaningful_changes` pairs a full `len()` with a hard-coded slice, so a
nine-file change logs as `Found 9 file(s) changed: [...5 items]` with no
indication that four were elided. When a failed automated run's log is the only
forensic record, the reader is left reconciling a count against a list that
contradicts it.

## Steps to Reproduce

1. Run `ll-auto` on an issue whose implementation touches more than five files
   outside the excluded directories.
2. Read the Phase 3 log line:
   ```
   [22:39:20] Found 9 file(s) changed: ['commands/refine-issue.md',
   'docs/reference/API.md', 'docs/reference/CLI.md',
   'scripts/little_loops/cli/issues/__init__.py',
   'scripts/little_loops/cli/issues/format_check.py']
   ```
3. Count the rendered entries: five. The other four are unrecoverable from the
   log.

## Current Behavior

`scripts/little_loops/work_verification.py`, four instances in
`_detect_meaningful_changes`, all the same shape (pre-fix line numbers
212-214, 236-238, 253-255, 278-281):

```python
logger.info(
    f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
)
```

Two more with `[:10]` on the excluded-file warnings (219, 293), and a fifth
near-analogue at `git_operations.py:878-880`:

```python
f"path(s) at teardown; preserving before removal: {sorted(paths)[:10]}"
```

Fixing one instance at a time would leave the next occurrence to be rediscovered
from a different code path.

## Expected Behavior

A truncated list says so and reports the full count, e.g.
`['a.py', ..., 'e.py'] (first 5 of 9)`. A list that fits renders unchanged, with
no annotation noise.

## Root Cause

Ordinary drift: the pattern was written once with an inline slice and copied to
each new diagnostic. Nothing tied the count expression to the rendering
expression, so they were free to disagree.

## Program Design

### Signatures

- `_sample(paths: list[str], limit: int = 5) -> str` — new, `work_verification.py`.
- `_detect_meaningful_changes(logger, changed_files, config, baseline_sha) -> bool` — existing, `work_verification.py:200`.
- `filter_excluded_files(files: list[str]) -> list[str]` — existing, `work_verification.py:31`; unchanged neighbour the helper sits beside.

### Call Path

`verify_work_was_done` (`work_verification.py:159`) -> `_detect_meaningful_changes` (`work_verification.py:200`) -> `_sample`, at all six diagnostic sites. Second consumer imports it through the existing `work_verification` block in `git_operations.py:19` for the teardown warning in `preserve_dirty_worktree_if_needed`.

Returns `f"{paths}"` when `len(paths) <= limit`, otherwise
`f"{paths[:limit]} (first {limit} of {len(paths)})"`. Placed in
`work_verification.py` beside `filter_excluded_files` and re-exported through
`git_operations.py`'s existing `work_verification` import block, which already
carries `EXCLUDED_DIRECTORIES` and `filter_excluded_files` under a `noqa: F401`.

Deliberately a formatter rather than a logging wrapper: the call sites differ in
level (`info` vs `warning`) and in surrounding prose, so only the rendering is
shared.

## Implementation Steps

1. Add `_sample` to `scripts/little_loops/work_verification.py`.
2. Replace all six slice sites in that module (four `[:5]`, two `[:10]`).
3. Add `_sample` to the `work_verification` import in `git_operations.py` and
   replace the `sorted(paths)[:10]` site.
4. Add `TestSample` to `scripts/tests/test_work_verification.py`: short list,
   list exactly at the limit, truncated list reporting the full count, custom
   limit, empty list.

## Impact

Diagnostic only — no behavior change. It earns its fix because these lines are
the primary evidence when an automated run fails without a human present, and a
count that disagrees with its own list actively misdirects the reader. It did so
during this session's investigation: the "9 vs 5" discrepancy had to be chased
into the source before it could be dismissed.

## Resolution

`_sample` added and applied at all seven sites across the two modules. A >5-file
change now renders `(first 5 of N)`; lists at or under the limit are unchanged.

## Status

**Completed** — 2026-08-05

## Session Log
- `hook:posttooluse-status-done` - 2026-08-05T05:46:28 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- run-forensics - 2026-08-05 - Noticed while reading a failed `ll-auto` log;
  fixed as a set across both modules.
