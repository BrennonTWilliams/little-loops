---
id: BUG-842
type: BUG
priority: P2
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# BUG-842: ll-sprint and ll-parallel hardcode git remote name "origin"

## Summary

`ll-sprint` and `ll-parallel` hardcode the git remote name `"origin"` in `worker_pool.py` and `merge_coordinator.py` with no way to configure it. Repos that use a different remote name (e.g., `"main"`) fail 100% of parallel runs — every issue fails at the `git fetch origin <base>` step before any implementation work begins.

## Current Behavior

- `worker_pool.py` (`_sync_with_base()`) runs `git fetch origin <base>` and immediately returns `False` (fatal) if the fetch fails — no fallback, no config.
- `merge_coordinator.py` runs `git fetch origin <base>` — also hardcoded but does fall back to local base on failure.
- `ParallelConfig` in `types.py` has no `remote_name` field, so there is no config-driven way to override the remote name.

When a repo's remote is not named `"origin"`, all 8 issues fail with:
```
fatal: 'origin' does not appear to be a git repository
Failed to fetch origin/heads/main
```

## Expected Behavior

- `ParallelConfig` has a `remote_name` field (default `"origin"`) that can be set in `ll-config.json` under `parallel.remote_name`.
- Both `worker_pool.py` and `merge_coordinator.py` read `remote_name` from config instead of hardcoding `"origin"`.
- `worker_pool.py` degrades gracefully on fetch failure (falls back to local base, like `merge_coordinator.py` already does) instead of treating it as fatal.

## Motivation

Any project whose git remote is not named `"origin"` is completely unable to use `ll-sprint` or `ll-parallel`. This is a silent blocker — the error occurs before any implementation attempt and results in 0/N success rate, wasting all configured workers. A simple config field + two-line fix unblocks the entire parallel processing pipeline for non-standard remotes.

## Steps to Reproduce

1. Set up a repo where `git remote -v` shows a remote named anything other than `"origin"` (e.g., `"main"`).
2. Run `ll-sprint run <sprint-name>` with any issues.
3. Observe: all issues fail immediately with `fatal: 'origin' does not appear to be a git repository`.

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `in _sync_with_base()` (approximately line 847)
- **Cause**: `git fetch origin` is hardcoded. Fetch failure returns `(False, "Failed to fetch origin/...")` immediately — no fallback to local base.

Secondary location:
- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in _sync_branch_with_base()` (approximately line 999)
- **Cause**: Same hardcoded `"origin"`, though this one already falls back to local base on failure.

Root config gap:
- **File**: `scripts/little_loops/parallel/types.py`
- **Anchor**: `class ParallelConfig`
- **Cause**: No `remote_name` field exists; config loading ignores any `remote_name` in `ll-config.json`.

## Proposed Solution

**Step 1 — Add `remote_name` to `ParallelConfig`** (`types.py`):
```python
remote_name: str = "origin"  # Git remote name to use for fetching base branch
```

**Step 2 — Fix `worker_pool.py`** in `_sync_with_base()`:
```python
remote = self.parallel_config.remote_name
fetch_result = subprocess.run(["git", "fetch", remote, base], ...)
rebase_target = f"{remote}/{base}" if fetch_result.returncode == 0 else base
rebase_result = subprocess.run(["git", "rebase", rebase_target], ...)
if rebase_result.returncode != 0:
    subprocess.run(["git", "rebase", "--abort"], ...)
    return False, f"Failed to rebase onto {rebase_target}: {rebase_result.stderr}"
self.logger.info(f"[{issue_id}] Rebased branch onto {rebase_target}")
return True, ""
```

**Step 3 — Fix `merge_coordinator.py`** in `_sync_branch_with_base()`:
```python
remote = self.config.remote_name
fetch_result = subprocess.run(["git", "fetch", remote, base], ...)
rebase_target = f"{remote}/{base}" if fetch_result.returncode == 0 else base
```

**Step 4 — Document the new config field** in `ll-config.json` schema and `docs/reference/CLI.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/types.py` — add `remote_name` field to `ParallelConfig`
- `scripts/little_loops/parallel/worker_pool.py` — use config remote + add graceful fallback
- `scripts/little_loops/parallel/merge_coordinator.py` — use config remote

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — reads `ParallelConfig`
- `scripts/little_loops/parallel/merge_coordinator.py` — reads `ParallelConfig`
- `scripts/little_loops/parallel/coordinator.py` — constructs `ParallelConfig` from ll-config.json

### Similar Patterns
- `merge_coordinator.py` already has the fallback pattern; `worker_pool.py` should match it

### Tests
- `scripts/tests/test_worker_pool.py` (if exists) — add tests for non-"origin" remote name
- `scripts/tests/test_parallel_types.py` (if exists) — verify new field defaults

### Documentation
- `docs/reference/CLI.md` — document `parallel.remote_name` config option
- `config-schema.json` — add `remote_name` to `parallel` schema definition

### Configuration
- `config-schema.json` — `parallel` object needs `remote_name` string property

## Implementation Steps

1. Add `remote_name: str = "origin"` to `ParallelConfig` dataclass in `types.py`
2. Update `worker_pool.py` `_sync_with_base()` to read `self.parallel_config.remote_name` and fall back gracefully on fetch failure
3. Update `merge_coordinator.py` to read `self.config.remote_name` instead of `"origin"`
4. Add `remote_name` to `config-schema.json` under `parallel` properties
5. Update `docs/reference/CLI.md` to document the new config field
6. Add/update tests for the new behavior
7. Verify with `ll-sprint run` in a repo with a non-"origin" remote name

## Impact

- **Priority**: P2 — completely blocks all ll-sprint/ll-parallel runs for any repo with a non-"origin" remote; 0% success rate
- **Effort**: Small — config field addition + two function edits + docs; no new patterns needed
- **Risk**: Low — fallback behavior already exists in merge_coordinator; we're aligning worker_pool to the same pattern
- **Breaking Change**: No — default value `"origin"` preserves existing behavior

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Parallel processing architecture |
| `docs/reference/API.md` | ParallelConfig API reference |

## Labels

`bug`, `parallel`, `ll-sprint`, `ll-parallel`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b275638-5179-4c71-9525-1b50451e1ba7.jsonl`

---

**Open** | Created: 2026-03-20 | Priority: P2
