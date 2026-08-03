---
id: BUG-3024
title: resolve_epic passes active-only ID set as all_known_ids, warning on every ref to a done issue
type: BUG
status: done
priority: P3
discovered_date: 2026-08-03
discovered_by: user-report
completed_at: '2026-08-03T15:44:23Z'
testable: true
labels:
- sprint
- dependency-graph
- false-positive
---

# BUG-3024: `resolve_epic` passes active-only ID set as `all_known_ids`, warning on every ref to a done issue

## Summary

`SprintManager.resolve_epic` passed the **active-only** issue ID set as
`DependencyGraph.from_issues(..., all_known_ids=...)`. That parameter's sole
purpose is to distinguish "this ref points at a real issue outside this graph"
(silent) from "this ref is dangling/typo'd" (warn). Feeding it an active-only
set made every `depends_on` / `blocked_by` / `blocks` reference to a **done,
cancelled, or deferred** issue log a spurious `unknown issue` warning at sprint
start.

Cosmetic only — wave scheduling was already correct, because a completed
blocker is not a graph node and its edge is dropped either way. The warning
falsely implies a broken reference in the user's issue files.

## Current Behavior

Observed on `ll-sprint run epic-3008`:

```
Issue ENH-3015 has depends_on unknown issue BUG-3009
```

`BUG-3009` exists on disk at
`.issues/bugs/P2-BUG-3009-cache-deferred-tools-config-never-threaded-into-host-runner.md`
with `status: done` and `completed_at: '2026-08-03T05:58:33Z'` — it is not
unknown, merely complete.

Root cause, `scripts/little_loops/sprint.py:350,367` (pre-fix):

```python
active_ids_set = {info.issue_id for info in all_active}   # line 350 — ACTIVE only
dep_graph = DependencyGraph.from_issues(child_infos, all_known_ids=active_ids_set)
```

`all_active` comes from `find_issues(self.config, status_filter=_ACTIVE_STATUSES)`,
where `_ACTIVE_STATUSES = {"open", "in_progress", "blocked"}` (`sprint.py:15`),
so done/cancelled/deferred IDs are absent from the set and trip the warn branch
at `dependency_graph.py:142-147`.

This contradicts the documented contract of the parameter
(`dependency_graph.py:80`): *"Set of all issue IDs that exist **on disk**."*

`resolve_epic` also never passed `completed_ids`, so the earlier
"already satisfied" skip at `dependency_graph.py:140` could not fire either.
This does not change scheduling (done issues are not graph nodes, so the edge
is dropped regardless) — it is the same gap, not a second defect.

## Steps to Reproduce

1. Create an EPIC with two active children, one of which declares
   `depends_on: [<ID>]` where `<ID>` is a sibling with `status: done`.
2. Run `ll-sprint run <epic-id>` (or `SprintManager.load_or_resolve("EPIC-NNN")`).
3. Observe `Issue <child> has depends_on unknown issue <ID>` on stderr, despite
   `<ID>` having a file on disk.

## Expected Behavior

No warning for a reference to any issue that exists on disk, regardless of its
status. Genuinely dangling references (no file at all) must still warn.

## Deviation from Established Convention

Every other call site in the repo already derives this set correctly, via
`gather_all_issue_ids(issues_dir, config=config)` — a filename-only scan of the
type-scoped category dirs, which by design includes done/deferred issues
(`dependency_mapper/operations.py:362-368`):

- `scripts/little_loops/issue_manager.py:1468`
- `scripts/little_loops/issue_parser.py:2123`
- `scripts/little_loops/cli/deps.py:385`
- `scripts/little_loops/cli/sprint/run.py:502`
- `scripts/little_loops/cli/sprint/manage.py:96`
- `scripts/little_loops/cli/sprint/show.py:187`
- `scripts/little_loops/cli/sprint/edit.py:114`
- `scripts/little_loops/cli/issues/link.py:226`
- `scripts/little_loops/cli/issues/sequence.py:79`

`sprint.py:367` was the lone outlier.

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint.py` — `SprintManager.resolve_epic`, the
  `DependencyGraph.from_issues(...)` call (was line 367).

### Tests
- `scripts/tests/test_sprint.py` — class `TestSprintManagerLoadOrResolve`,
  alongside the existing `test_load_or_resolve_epic_depends_on_ordering`.

### Dependent Files (Callers/Importers)
- None. The change is confined to one call site inside `resolve_epic`; the
  `DependencyGraph.from_issues` signature is unchanged.

## Program Design

### Signatures

No signature changes — the fix is a corrected argument at one existing call
site. The relevant existing signatures:

```python
# scripts/little_loops/dependency_graph.py — classmethod, unchanged
@classmethod
def from_issues(
    cls,
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
) -> "DependencyGraph": ...

# scripts/little_loops/dependency_mapper/operations.py:362 — unchanged
def gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]: ...
```

New local in `SprintManager.resolve_epic`:
`all_known_ids: set[str] | None`, replacing the `active_ids_set` argument.
`active_ids_set` is retained — it is still used at `sprint.py:351` to intersect
forward/backward child lookups down to the active set, and now also serves as
the `except`-branch fallback.

### Call Path

`SprintManager.resolve_epic` (`sprint.py`)
-> `gather_all_issue_ids(self.config.project_root / self.config.issues.base_dir,
   config=self.config)` — filename-only scan across `config.issue_categories`,
   returning every ID on disk regardless of status
-> passed as `all_known_ids=` into `DependencyGraph.from_issues(child_infos, ...)`
-> consumed by the three warn-guard branches in `from_issues`:
   `dependency_graph.py:111` (`blocked_by`), `:129` (`blocks`), `:143`
   (`depends_on`), each of which now finds done/deferred IDs present and skips
   the `logger.warning` while still `continue`-ing past the edge.

On exception, falls back to `all_known_ids = active_ids_set`, reproducing the
pre-fix behavior rather than propagating.

## Acceptance Criteria

- [x] `resolve_epic` derives `all_known_ids` from all issues on disk, not the
      active-only set.
- [x] A `depends_on` reference to a `done` issue produces **no** `unknown issue`
      warning.
- [x] The done blocker is still excluded from the resolved sprint, and wave
      ordering among active children is unchanged.
- [x] A genuinely dangling reference (no file on disk) **still** warns —
      guarding against a fix that merely silences the log.
- [x] The added test fails against the pre-fix code with the exact production
      message, proving it is a real regression guard.
- [x] `python -m pytest scripts/tests/` exits 0 apart from pre-existing,
      unrelated failures.

## Resolution

- **Action**: fix
- **Completed**: 2026-08-03
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sprint.py` (`resolve_epic`): `all_known_ids` is now
  derived from `gather_all_issue_ids(config.project_root / config.issues.base_dir,
  config=self.config)`, matching the nine other call sites. Wrapped in
  `try/except` that falls back to the previous `active_ids_set` so a config or
  scan failure degrades to prior behavior rather than crashing sprint
  resolution — mirroring the defensive shape at `issue_parser.py:2118-2125`.
  Added an explanatory comment recording why the active-only set is wrong.
- `scripts/tests/test_sprint.py`: added two tests to
  `TestSprintManagerLoadOrResolve`, plus an `import logging` for `caplog` use.
  - `test_load_or_resolve_epic_depends_on_done_issue_no_warning` — reproduces
    the reported scenario (EPIC-3008 / done BUG-3009 / ENH-3015 depending on it,
    plus an active sibling); asserts no `unknown issue` record is logged, the
    done blocker stays out of the sprint, and both active children schedule.
  - `test_load_or_resolve_epic_depends_on_dangling_issue_still_warns` — asserts
    a ref to a nonexistent `BUG-9999` **does** still warn, so the fix cannot
    later be widened into swallowing real dangling refs.

### Verification Results
- Pre-fix failure confirmed: with the one-line change reverted, the new test
  fails with the literal production message
  `Issue ENH-3015 has depends_on unknown issue BUG-3009` — the guard is not a
  tautology.
- Tests: `scripts/tests/test_sprint.py` — 103 passed.
- Full suite: `python -m pytest scripts/tests/` — 17101 passed, 33 skipped,
  1 failed. The single failure is
  `integration/test_init_e2e.py::TestInitLogoBanner::test_yes_run_prints_logo_banner_on_tty`,
  verified pre-existing by re-running it with these changes stashed — it fails
  identically on clean `main` (the ASCII logo banner no longer contains the
  literal string `little loops`). Unrelated to this fix; left for its own issue.
- Lint: `ruff check` on both changed files — PASS.
- Format: `ruff format --check` on both changed files — PASS (scoped to the two
  changed files, since bare `ruff format scripts/` reformats ~30 unrelated
  files due to format drift on `main`).
- Types: `mypy scripts/little_loops/sprint.py` — PASS.

## Status

**Completed** | Created: 2026-08-03 | Priority: P3

## Impact

- **Priority**: P3 — no functional impact; a misleading warning that suggests
  broken issue references where none exist, on every EPIC sprint run whose
  children depend on completed work (i.e. routinely, mid-epic).
- **Effort**: Small — one call site, plus two regression tests.
- **Risk**: Low — strictly widens the "known" set, so it can only remove
  warnings, never scheduling edges. The dangling-ref test pins the boundary.
- **Breaking Change**: No.

## Notes

Discovered from a user-reported warning during an `ll-sprint run epic-3008`
session; not part of EPIC-3008's own scope, hence no `parent`.

The pre-existing `test_init_e2e.py::TestInitLogoBanner` failure surfaced while
verifying this fix and is **not** addressed here — it warrants its own issue.


## Session Log
- `hook:posttooluse-status-done` - 2026-08-03T15:45:27 - `7939e26d-6a15-469e-8ea1-eadcf1af1588.jsonl`
