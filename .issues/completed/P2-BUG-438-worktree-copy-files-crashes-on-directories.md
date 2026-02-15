---
discovered_date: "2026-02-15"
discovered_by: capture-issue
---

# BUG-438: worktree_copy_files crashes on directory entries with IsADirectoryError

## Summary

`_setup_worktree()` in `worker_pool.py` uses `shutil.copy2()` to copy entries from `worktree_copy_files` config into worktrees. When a user configures a directory (e.g., `node_modules`) in this list, `shutil.copy2()` raises `IsADirectoryError: [Errno 21] Is a directory` because it only handles files. This causes the entire sprint/parallel run to fail immediately for every issue in the wave.

## Steps to Reproduce

1. Configure `worktree_copy_files` in project `ll-config.json` to include a directory entry:
   ```json
   {
     "parallel": {
       "worktree_copy_files": ["node_modules", ".env*"]
     }
   }
   ```
2. Run `ll-sprint run <sprint-name>` or `ll-parallel`
3. Observe both/all issues in the wave fail instantly with:
   ```
   [Errno 21] Is a directory: '/path/to/repo/node_modules'
   ```

## Actual Behavior

`shutil.copy2(src, dest)` at `worker_pool.py` in `_setup_worktree()` raises `IsADirectoryError` when `src` is a directory. The exception is caught by the broad `except Exception` handler in `_process_issue()`, which returns a `WorkerResult(success=False, error=str(e))`. Every issue in the wave fails instantly without any useful diagnostic message.

## Expected Behavior

`_setup_worktree()` should handle directory entries gracefully:
- Validate that entries in `worktree_copy_files` are files, not directories
- Provide a clear warning message like `"Skipping 'node_modules' in worktree_copy_files: is a directory (use worktree_link_dirs for directories)"`
- Ideally, support a `worktree_link_dirs` config option to **symlink** directories into worktrees (common need for `node_modules`, `.venv`, etc.)

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `in _setup_worktree()`, the `worktree_copy_files` loop
- **Cause**: `shutil.copy2(src, dest)` only handles files. When `src.exists()` returns True for a directory, the code proceeds to `shutil.copy2()` which raises `IsADirectoryError`. There is no `src.is_file()` guard or directory-aware fallback.

## Error Messages

```
[Errno 21] Is a directory: '/Users/brennon/AIProjects/ai-workspaces/headstorm/maw-demo-ui/node_modules'
```

Logged as: `BUG-005 failed: [Errno 21] Is a directory: '/path/to/repo/node_modules'`

## Proposed Solution

**Approach 1 (minimal fix)**: Add `is_file()` guard with clear warning:

```python
# In _setup_worktree(), worktree_copy_files loop
for file_path in self.parallel_config.worktree_copy_files:
    if file_path.startswith(".claude/"):
        continue
    src = self.repo_path / file_path
    if src.exists():
        if src.is_dir():
            self.logger.warning(
                f"Skipping '{file_path}' in worktree_copy_files: "
                "is a directory (use worktree_link_dirs for directories)"
            )
            continue
        dest = worktree_path / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        self.logger.info(f"Copied {file_path} to worktree")
    else:
        self.logger.debug(f"Skipped {file_path} (not found in main repo)")
```

**Approach 2 (full feature)**: Also add `worktree_link_dirs` config option to symlink directories:

```python
# New config field in ParallelConfig
worktree_link_dirs: list[str] = field(default_factory=list)

# In _setup_worktree(), after worktree_copy_files loop
for dir_path in self.parallel_config.worktree_link_dirs:
    src = self.repo_path / dir_path
    if src.exists() and src.is_dir():
        dest = worktree_path / dir_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(src, dest)
        self.logger.info(f"Linked {dir_path} to worktree")
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py` - Add `is_file()` guard in `_setup_worktree()`
- `scripts/little_loops/parallel/types.py` - Add `worktree_link_dirs` field to `ParallelConfig` (Approach 2)
- `scripts/little_loops/config.py` - Add `worktree_link_dirs` to `ParallelAutomationConfig` and `create_parallel_config()` (Approach 2)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` - Creates `WorkerPool`, passes `ParallelConfig`
- `scripts/little_loops/cli/sprint.py` - Creates `ParallelConfig` via `config.create_parallel_config()`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_parallel_types.py` - Add test for directory entries in `worktree_copy_files`
- `scripts/tests/test_worker_pool.py` (if exists) - Test `_setup_worktree` with directory entries

### Documentation
- `config-schema.json` - Add `worktree_link_dirs` property (Approach 2)
- `docs/TROUBLESHOOTING.md` - Add note about directory entries in `worktree_copy_files`

### Configuration
- `config-schema.json` - Schema for new `worktree_link_dirs` field

## Implementation Steps

1. Add `src.is_file()` guard in `_setup_worktree()` worktree_copy_files loop with warning log
2. Add `worktree_link_dirs` field to `ParallelConfig` and `ParallelAutomationConfig`
3. Add symlink logic in `_setup_worktree()` after the copy_files loop
4. Update `config.create_parallel_config()` to pass through the new field
5. Add tests for both the guard and the symlink feature
6. Update config schema

## Impact

- **Priority**: P2 - Blocks all parallel/sprint execution when user configures a directory in worktree_copy_files
- **Effort**: Small - Core fix is a 5-line guard; symlink feature is ~20 lines across 3 files
- **Risk**: Low - Additive change, existing behavior preserved for file entries
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `worktree`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-02-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a259c9d-a95d-43c9-b74a-d743f4341654.jsonl`

---

## Resolution

**Fixed** - Added `src.is_dir()` guard in `_setup_worktree()` worktree_copy_files loop. Directory entries are now skipped with a warning log instead of crashing with `IsADirectoryError`.

### Changes
- `scripts/little_loops/parallel/worker_pool.py` - Added directory check before `shutil.copy2()` with warning message
- `scripts/tests/test_worker_pool.py` - Added test verifying directory entries are skipped

---

## Status

**Resolved** | Created: 2026-02-15 | Resolved: 2026-02-15 | Priority: P2
