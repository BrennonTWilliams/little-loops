# ENH-352: Batch git log calls in _get_files_modified_since_commit

## Summary

Replace per-file `git log` subprocess calls with a single batched call in `_get_files_modified_since_commit`.

## Research Findings

- **Blocking dependency**: ENH-349 (consolidate duplicated file path extraction) is **completed** - unblocked.
- **Function location**: `scripts/little_loops/issue_discovery.py:439-473`
- **Single caller**: `detect_regression_or_duplicate()` at line 523
- **No direct unit tests**: Tested indirectly through `TestDetectRegressionOrDuplicate`
- **Return contract**: `tuple[list[str], list[str]]` → `(modified_files, related_commits)`
- **No existing batching patterns** in the codebase to follow

## Implementation Plan

### Phase 1: Refactor `_get_files_modified_since_commit`

**File**: `scripts/little_loops/issue_discovery.py` (lines 439-473)

Replace the per-file loop with a single batched `git log` call:

```python
def _get_files_modified_since_commit(
    since_commit: str,
    target_files: list[str],
) -> tuple[list[str], list[str]]:
    if not target_files:
        return [], []

    # Single batched git log call with all file paths
    result = subprocess.run(
        ["git", "log", "--pretty=format:%H", "--name-only",
         f"{since_commit}..HEAD", "--"] + target_files,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return [], []

    # Parse output: alternating commit SHAs and file names separated by blank lines
    target_set = set(target_files)
    modified_set: set[str] = set()
    related_commits: set[str] = set()

    for block in result.stdout.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if not lines:
            continue
        commit_sha = lines[0]
        related_commits.add(commit_sha[:8])
        for file_name in lines[1:]:
            file_name = file_name.strip()
            if file_name in target_set:
                modified_set.add(file_name)

    # Preserve original order from target_files
    modified_files = [f for f in target_files if f in modified_set]
    return modified_files, list(related_commits)
```

**Key design decisions**:
- `--name-only` added to identify which files each commit touched
- Output format: blocks separated by blank lines, each block = SHA + file names
- Use a `set` for target files for O(1) lookup
- Preserve original ordering of `modified_files` (match by filtering `target_files`)
- Related commits include ALL commits in the range that touched any target file (same as before)

### Phase 2: Verify

- [ ] `python -m pytest scripts/tests/test_issue_discovery.py -v`
- [ ] `ruff check scripts/`
- [ ] `python -m mypy scripts/little_loops/`

## Success Criteria

- [ ] Single subprocess call instead of N calls
- [ ] Return contract unchanged: `tuple[list[str], list[str]]`
- [ ] All existing tests pass
- [ ] Lint/type checks pass
