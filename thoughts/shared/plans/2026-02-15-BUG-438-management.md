# BUG-438: worktree_copy_files crashes on directories

## Summary

Add `is_dir()` guard in `_setup_worktree()` to skip directory entries in `worktree_copy_files` with a clear warning instead of crashing with `IsADirectoryError`.

## Approach

**Approach 1 (minimal fix)**: Add `src.is_dir()` check before `shutil.copy2()` with a warning log. This is the correct scope for a bug fix - the `worktree_link_dirs` feature (Approach 2) is a separate enhancement.

## Changes

### 1. `scripts/little_loops/parallel/worker_pool.py` (lines 528-539)

Add `src.is_dir()` guard before `shutil.copy2()`:

```python
if src.exists():
    if src.is_dir():
        self.logger.warning(
            f"Skipping '{file_path}' in worktree_copy_files: "
            "is a directory (use symlinks or copytree for directories)"
        )
        continue
    dest = worktree_path / file_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    self.logger.info(f"Copied {file_path} to worktree")
```

### 2. `scripts/tests/test_worker_pool.py`

Add test in `TestWorkerPoolWorktreeManagement` class verifying:
- Directory entries in `worktree_copy_files` are skipped (no crash)
- Warning is logged for skipped directories
- File entries still copied normally

## Success Criteria

- [x] `_setup_worktree()` skips directory entries without crashing
- [x] Warning logged for directory entries
- [x] Existing file copy behavior unchanged
- [x] Tests pass
- [x] Lint/type checks pass
