---
id: BUG-842
type: BUG
priority: P2
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected function names and exact line numbers:**
- Primary site: `_update_branch_base()` (not `_sync_with_base()`) in `worker_pool.py:830–877`
  - `worker_pool.py:847` — `["git", "fetch", "origin", base]` (hardcoded)
  - `worker_pool.py:855` — error string `f"Failed to fetch origin/{base}: ..."` (hardcoded)
  - `worker_pool.py:859` — `["git", "rebase", f"origin/{base}"]` (hardcoded)
  - `worker_pool.py:874` — error string `f"Failed to rebase onto origin/{base}: ..."` (hardcoded)
  - **Fetch failure**: immediately returns `(False, error)` at line 855 — no fallback
- Secondary site: `_handle_conflict()` (not `_sync_branch_with_base()`) in `merge_coordinator.py:997–1005`
  - `merge_coordinator.py:999` — `["git", "fetch", "origin", base]` (hardcoded)
  - Already has fetch-fail fallback: `rebase_target = f"origin/{base}" if fetch ok else base` (line 1005)
- **Two additional hardcoded "origin" sites** not mentioned above (in `_process_merge()`):
  - `merge_coordinator.py:794` — `["pull", "--rebase", "origin", base]` (hardcoded)
  - `merge_coordinator.py:818` — `["pull", "--no-rebase", "origin", base]` (hardcoded, merge-strategy fallback)
- **Config bridge gap**: `scripts/little_loops/config/automation.py:40–86` — `ParallelAutomationConfig` is the intermediate dataclass between `ll-config.json` and `ParallelConfig`. It must also receive `remote_name` for the field to be read from config.
- **`orchestrator.py`** confirmed zero git-remote "origin" hardcodings — all `origin` occurrences are Python variable names (`_original_sigint`, `_original_sigterm`, `original_path`). No changes needed.

## Proposed Solution

**Step 1 — Add `remote_name` to `ParallelConfig`** (`types.py`):
```python
remote_name: str = "origin"  # Git remote name to use for fetching base branch
```

**Step 2 — Fix `worker_pool.py`** in `_update_branch_base()`:
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

**Step 3 — Fix `merge_coordinator.py`** in `_handle_conflict()` and `_process_merge()`:
```python
remote = self.config.remote_name
# _handle_conflict(): replace hardcoded "origin" in fetch + rebase_target logic
fetch_result = subprocess.run(["git", "fetch", remote, base], ...)
rebase_target = f"{remote}/{base}" if fetch_result.returncode == 0 else base
# _process_merge(): replace "origin" in pull --rebase and pull --no-rebase commands
["git", "pull", "--rebase", remote, base]
["git", "pull", "--no-rebase", remote, base]
```

**Step 4 — Document the new config field** in `ll-config.json` schema and `docs/reference/CLI.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/types.py` — add `remote_name` field to `ParallelConfig` (after `base_branch` at line ~350); update `to_dict()` and `from_dict()` (lines ~382–450)
- `scripts/little_loops/parallel/worker_pool.py` — replace all `"origin"` literals in `_update_branch_base()`: git args at lines 847, 859; error messages at 855, 874; log message at 876; add fetch-fail fallback
- `scripts/little_loops/parallel/merge_coordinator.py` — replace `"origin"` in `_handle_conflict()` (line 999) and `_process_merge()` (lines 794, 818)
- `scripts/little_loops/config/automation.py` — add `remote_name` to `ParallelAutomationConfig` (lines ~40–86) and its `from_dict()` — **required to wire `ll-config.json` → `ParallelConfig`**
- `scripts/little_loops/config/core.py` — thread `self._parallel.remote_name` into `create_parallel_config()` (lines 253–327): add `remote_name: str = "origin"` parameter at line 272 (following `base_branch` pattern), forward to `ParallelConfig(remote_name=remote_name, ...)` at line 326
- `config-schema.json` — add `remote_name` string property to `parallel` block (before `additionalProperties: false` at line 249)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — confirmed zero git-remote `"origin"` hardcodings (lines 98, 99, 168, 169, 173, 175, 1058, 1060 are all Python variable names) — no changes needed
- `scripts/little_loops/cli/sprint/run.py` — invokes parallel module; no `"origin"` string literals found — no changes needed
- `scripts/little_loops/cli/sprint/create.py` / `edit.py` — no `"origin"` string literals found — no changes needed

### Similar Patterns
- `merge_coordinator.py:1005` already has the fetch-fail fallback pattern (`rebase_target = f"origin/{base}" if fetch ok else base`); `worker_pool.py:854–855` should match it
- All other `ParallelConfig` str fields use `field_name: str = "default"` syntax (no `field()` wrapper needed)
- `ParallelAutomationConfig.from_dict()` always uses `data.get("key", default)` for safe deserialization

### Tests
- `scripts/tests/test_worker_pool.py` — add test for non-`"origin"` remote name; see `default_parallel_config` fixture at lines 61–74
- `scripts/tests/test_parallel_types.py` — `TestParallelConfig` class at line 721; add to `test_default_values` (line 724), `test_from_dict` (line 878), and roundtrip serialization tests, following the `base_branch` field pattern
- `scripts/tests/test_merge_coordinator.py` — `default_config` fixture at lines 65–78; update if non-default remote needed for tests
- `scripts/tests/test_subprocess_mocks.py:644` — **NEW**: mock checks `cmd[:4] == ["git", "pull", "--rebase", "origin"]`; must be updated to match the configurable remote name or parameterized to accept any remote

### Documentation
- `docs/reference/CLI.md` — document `parallel.remote_name` config option
- `docs/development/MERGE-COORDINATOR.md` — directly references `_sync_with_base`, `_sync_branch_with_base`, and the `"origin"` hardcoding; update with corrected function names and new field

### Configuration
- `config-schema.json` — `parallel` object needs `remote_name` string property; example pattern from existing `command_prefix` property (around line 230)

## Implementation Steps

1. Add `remote_name: str = "origin"` to `ParallelConfig` (`types.py`) and `ParallelAutomationConfig` (`config/automation.py`); wire through `create_parallel_config()` in `config/core.py`
2. Replace all 4 hardcoded `"origin"` literals in `worker_pool.py` `_update_branch_base()` and add fetch-fail fallback
3. Replace all 3 hardcoded `"origin"` literals in `merge_coordinator.py` (`_handle_conflict()` + `_process_merge()`)
4. Add `remote_name` string property to `config-schema.json` under `parallel`; update `docs/reference/CLI.md`
5. Add tests: `test_parallel_types.py` roundtrip for `remote_name`, `test_worker_pool.py` non-`"origin"` remote test; update `test_subprocess_mocks.py:644` mock to use configurable remote
6. Verify end-to-end with `ll-sprint run` in a repo whose remote is not named `"origin"`

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
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36183605-dd79-41a4-9e6a-73bd76c04600.jsonl`
- `/ll:refine-issue` - 2026-03-20T20:25:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4b67db3c-3212-4208-a849-0257b4b7d161.jsonl`
- `/ll:format-issue` - 2026-03-20T20:13:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04d10017-26b1-49e5-af25-cfb58245ab95.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/594d1b83-cf85-4943-8fc1-ffa883e482c8.jsonl`
- `/ll:refine-issue` - 2026-03-20T19:30:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e8b60e0-04d0-42b9-8fe6-3dfdc7801672.jsonl`

- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b275638-5179-4c71-9525-1b50451e1ba7.jsonl`

---

**Open** | Created: 2026-03-20 | Priority: P2
