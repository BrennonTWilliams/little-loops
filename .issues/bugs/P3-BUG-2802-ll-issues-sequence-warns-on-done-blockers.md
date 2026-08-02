---
discovered_date: 2026-07-25
status: done
completed_at: '2026-07-25T16:15:29Z'
---

# BUG-2802: `ll-issues sequence` warns on every reference to a `done` issue

## Summary

`ll-issues sequence` emits `"Issue <X> blocked by unknown issue <Y>"` and
`"Issue <X> has depends_on unknown issue <Y>"` warnings for any `blocked_by` /
`depends_on` reference whose target is a `status: done` issue. All known-issue
IDs live on disk in the type-scoped category directories (per the project
convention documented on `gather_all_issue_ids`), so the references are valid
— the warnings are noise.

Root cause: `sequence.py` builds the dependency graph without passing
`all_known_ids` to `DependencyGraph.from_issues()`, so the `all_known_ids is
None` branch always fires. The correct pattern is already used by
`find_issues()` in `issue_parser.py:1280-1284` and by every other call site in
the codebase.

## Evidence

Captured 2026-07-25, `10:50:47` from another project's `.issues/`:

```
Issue ENH-068 blocked by unknown issue ENH-067
Issue ENH-090 blocked by unknown issue ENH-089
Issue ENH-093 blocked by unknown issue ENH-088
Issue ENH-093 blocked by unknown issue ENH-087
Issue ENH-093 blocked by unknown issue ENH-092
Issue ENH-094 blocked by unknown issue ENH-088
Issue ENH-094 blocked by unknown issue ENH-087
Issue ENH-094 blocked by unknown issue ENH-092
Issue ENH-099 blocked by unknown issue ENH-088
Issue FEAT-024 blocked by unknown issue ENH-043
Issue ENH-066 has depends_on unknown issue ENH-063
Issue ENH-151 has depends_on unknown issue ENH-150
```

Each referenced ID exists on disk under that project's `.issues/enhancements/`
(or `features/`) with `status: done` — the file was not moved to
`completed/`, matching the project convention `gather_all_issue_ids` documents
("Done and deferred issues remain in type dirs with status frontmatter, so
scanning only type dirs finds all known IDs.").

| Warning | Referenced ID | Referenced ID status | File on disk |
|---|---|---|---|
| ENH-068 blocked by ENH-067 | ENH-067 | `done` | yes |
| ENH-090 blocked by ENH-089 | ENH-089 | `done` (completed 2026-07-23) | yes |
| ENH-093 blocked by ENH-088 | ENH-088 | `done` | yes |
| ENH-093 blocked by ENH-087 | ENH-087 | `done` (completed 2026-07-22) | yes |
| ENH-093 blocked by ENH-092 | ENH-092 | `done` (completed 2026-07-22) | yes |
| ENH-094 blocked by ENH-088 | ENH-088 | `done` | yes |
| ENH-094 blocked by ENH-087 | ENH-087 | `done` | yes |
| ENH-094 blocked by ENH-092 | ENH-092 | `done` | yes |
| ENH-099 blocked by ENH-088 | ENH-088 | `done` | yes |
| FEAT-024 blocked by ENH-043 | ENH-043 | `done` | yes |
| ENH-066 depends_on ENH-063 | ENH-063 | `done` | yes |
| ENH-151 depends_on ENH-150 | ENH-150 | `done` | yes |

Sanity-check: ENH-066's frontmatter declares `depends_on: ENH-063, ENH-065`.
ENH-065 has no `status:` field, so it stays in the active issue set and does
**not** trigger a warning — only ENH-063 (done) does. This confirms the
warning fires only for references whose target is missing from the active set,
not for genuinely missing IDs.

## Root Cause

`scripts/little_loops/cli/issues/sequence.py:34` (v1.150.0):

```python
graph = DependencyGraph.from_issues(issues)   # ← no all_known_ids
```

`find_issues()` (`issue_parser.py:1249-1251`) skips `status in ("done",
"cancelled", "deferred")` by default, so done issues are absent from the
`issues` list passed to `from_issues()`.

`DependencyGraph.from_issues()` then evaluates (`dependency_graph.py:101-107`
and `131-139`):

```python
if blocker_id not in all_issue_ids:
    if all_known_ids is None or blocker_id not in all_known_ids:
        logger.warning(
            f"Issue {issue.issue_id} blocked by unknown issue {blocker_id}"
        )
    continue
```

With `all_known_ids=None`, the inner branch always fires when a done issue is
referenced. The warning tests in
`scripts/tests/test_dependency_graph.py:208-215` and `:99-126` cover the
"unknown ID" case but do not exercise the "known-on-disk but done" case,
which is why the bug slipped through.

The correct pattern is already used in `issue_parser.py:1267-1284`
(`skip_blocked=True` path) and other call sites:

```python
all_known_ids: set[str] | None = None
try:
    from little_loops.dependency_mapper import gather_all_issue_ids

    issues_dir = config.project_root / config.issues.base_dir
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)
except Exception:
    pass
graph = DependencyGraph.from_issues(all_active, all_known_ids=all_known_ids)
```

`gather_all_issue_ids` (`dependency_mapper/operations.py:261-293`) is
filename-only and lightweight: it scans `bugs/`, `features/`,
`enhancements/`, `epics/` (NOT `completed/`) and extracts
`(BUG|FEAT|ENH|EPIC)-\d+` matches. Done issues kept in the type dirs are
correctly included.

## Recommended Fix

Edit `scripts/little_loops/cli/issues/sequence.py` to match the
`issue_parser.py:1267-1284` pattern:

```python
issues = find_issues(config, type_prefixes=type_prefixes)

if not issues:
    print("No active issues found.")
    return 0

# gather all known IDs so references to done/cancelled issues don't warn
all_known_ids: set[str] | None = None
try:
    from little_loops.dependency_mapper import gather_all_issue_ids

    issues_dir = config.project_root / config.issues.base_dir
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)
except Exception:
    pass

graph = DependencyGraph.from_issues(issues, all_known_ids=all_known_ids)
```

### Test coverage to add

A new test in `scripts/tests/test_dependency_graph.py` should cover the
"known on disk but absent from `issues`" case, asserting that no warning
fires when `all_known_ids` is supplied. The existing
`test_depends_on_unknown_target_warns` and `test_blocked_by_unknown_warns`
tests cover the negative case but not the positive one.

## Impact

- Severity: low (cosmetic — does not break the sequence output, just pollutes
  the log).
- Scope: any repo with a non-trivial backlog of `done` issues that are still
  referenced by `blocked_by` / `depends_on`. Confirmed in another project;
  the same pattern will fire in `brenentech/little-loops` itself once any
  tracked issue references a completed predecessor.
- The dependency graph itself is correct: `get_blocking_issues()` /
  `get_pending_prerequisites()` already treat a `completed` blocker as
  resolved (`from_issues` line 99), and `get_execution_waves` similarly
  treats completed depends_on targets as satisfied. Only the warning
  emission is wrong.

## Out of Scope (verified)

None of the 12 referencing issues need editing. Every `blocked_by` /
`depends_on` reference is valid and points at a completed predecessor that
the dep graph already handles correctly.

## Side Observation (unrelated)

While reading the frontmatter, ENH-043 in that project's `.issues/enhancements/`
lacks an `id:` field — only `priority`, `parent`, `size`, `status`, etc.
The filename-derived ID still resolves, but a stricter schema check might
trip. Not a blocker for this bug.
