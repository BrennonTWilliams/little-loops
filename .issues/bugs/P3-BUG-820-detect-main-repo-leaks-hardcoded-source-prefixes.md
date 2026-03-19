---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 90
outcome_confidence: 93
---

# BUG-820: `_detect_main_repo_leaks` hardcoded source prefixes miss project-specific layouts

## Summary

The leak detection logic in `WorkerPool._detect_main_repo_leaks` uses hardcoded directory prefixes (`"backend/"`, `"src/"`, `"lib/"`, `"tests/"`) to identify files that were accidentally written to the main repo instead of the worktree. Projects using different source layouts (including this project's own `"scripts/"`) will not have leaked source files detected.

## Location

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Line(s)**: 1003-1017 (at scan commit: 8c6cf90)
- **Anchor**: `in method WorkerPool._detect_main_repo_leaks`
- **Code**:
```python
elif file_path.startswith(("backend/", "src/", "lib/", "tests/")):
    leaked_files.append(file_path)
```

## Current Behavior

Only files in `backend/`, `src/`, `lib/`, or `tests/` directories are detected as leaked source files. Files in project-specific directories like `scripts/`, `app/`, or `packages/` are not caught.

## Expected Behavior

The leak detection should use the project's configured `src_dir` from `ll-config.json` (and possibly `test_cmd` path) to determine which directories to check, rather than a hardcoded list.

## Steps to Reproduce

1. Run `ll-parallel` in a project where source lives in `scripts/` (like this project)
2. Have a worker accidentally write a file to `scripts/` in the main repo instead of the worktree
3. The file is not detected by `_detect_main_repo_leaks` and persists

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `in method WorkerPool._detect_main_repo_leaks`
- **Cause**: The source directory prefixes are hardcoded as string literals rather than derived from project configuration.

## Proposed Solution

Read `src_dir` from the project config (available via `self.config`) and include it in the prefix list. Fall back to the existing hardcoded list when `src_dir` is not configured. Example:

```python
source_prefixes = ["backend/", "src/", "lib/", "tests/"]
if self.config.project.src_dir:
    configured = self.config.project.src_dir.rstrip("/") + "/"
    if configured not in source_prefixes:
        source_prefixes.append(configured)
```

## Impact

- **Priority**: P3 - Affects any project not using the hardcoded directory names, including this project itself
- **Effort**: Small - Add config-based prefix to the existing list
- **Risk**: Low - Additive change, existing hardcoded prefixes still work
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `leak-detection`

## Status

**Open** | Created: 2026-03-19 | Priority: P3


## Verification Notes

**Verified**: 2026-03-19 | **Verdict**: VALID

- File `scripts/little_loops/parallel/worker_pool.py` exists ✅
- Method `WorkerPool._detect_main_repo_leaks` exists at line 950 (shifted from stated 1003 due to code growth)
- Code snippet (`elif file_path.startswith(("backend/", "src/", "lib/", "tests/"))`) matches at line 1006 ✅
- Bug confirmed: `scripts/` is not in the hardcoded prefix list; source files in this project's own `scripts/` directory would not be detected as leaks
- No dependency references to validate

**Line number update**: Key `elif` is now at line 1006–1007; method definition at line 950.

## Session Log
- `/ll:verify-issues` - 2026-03-19T22:44:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc051ae-f218-443d-ad6a-bad1a1757fb1.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
