---
discovered_date: 2026-01-24
discovered_by: capture_issue
discovered_source: argobots-ll-parallel-debug.log
---

# ENH-143: Detect and handle overlapping file modifications in parallel processing

## Summary

When multiple issues modify the same files, merge conflicts are inevitable. The system should detect potential overlaps upfront and either warn, serialize, or provide better conflict resolution.

## Context

Identified from conversation analyzing `argobots-ll-parallel-debug.log`:

**Evidence from log:**
- ENH-011 modified: `sidebar/index.tsx`, `sidebar/user-profile-menu.tsx`, + 3 others
- ENH-012 modified: `sidebar/index.tsx`, `sidebar/user-profile-menu.tsx`
- Both touched the same sidebar files
- ENH-012 merged first; ENH-011 failed with rebase conflict

```
error: could not apply 6fdbc5bc... feat(sidebar): add desktop sidebar resize with drag handle
```

## Current Behavior

1. Issues are dispatched to parallel workers without checking for file overlap
2. First completion merges successfully
3. Subsequent completions hit merge conflicts
4. Retry logic attempts rebase, but manual conflict resolution is often needed
5. Work is lost or requires manual intervention

## Proposed Solutions

### Option A: Pre-flight overlap detection
Analyze issue descriptions/scopes before dispatch to identify potential conflicts:
- Parse file paths mentioned in issues
- Check for common component/module references
- Warn or serialize issues with high overlap probability

### Option B: Scope-based serialization
If issues share the same "scope" (e.g., `sidebar`, `auth`, `api`), serialize them rather than parallelize.

### Option C: Improved conflict resolution
- Capture the conflicting diff
- Provide context to Claude about what the other branch changed
- Attempt intelligent merge resolution

### Option D: Dependency inference
If issue B modifies files that issue A also modifies, automatically infer a dependency (B blocked-by A).

## Impact

- **Priority**: P3 (Improves success rate, not critical)
- **Effort**: Medium-High (requires file analysis infrastructure)
- **Risk**: Low (additive enhancement)

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`enhancement`, `ll-parallel`, `merge-conflict`, `file-analysis`

---

## Verification Notes

**Verified: 2026-01-28**

- ll-parallel has no overlap detection mechanism; issue description remains accurate
- Removed external repo path from frontmatter (not relevant to little-loops project)
- Issue applies to ll-parallel behavior generally

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/file_hints.py`: New module for extracting file path hints from issue content using regex patterns
- `scripts/little_loops/parallel/overlap_detector.py`: New module for detecting overlapping file modifications between parallel issues
- `scripts/little_loops/parallel/orchestrator.py`: Integrated overlap detection into dispatch logic with deferral and re-queuing
- `scripts/little_loops/parallel/types.py`: Added `overlap_detection` and `serialize_overlapping` config options
- `scripts/little_loops/parallel/__init__.py`: Exported new modules
- `scripts/little_loops/config.py`: Added overlap detection parameters to `create_parallel_config`
- `scripts/little_loops/cli.py`: Added `--overlap-detection` and `--warn-only` CLI flags
- `scripts/tests/test_file_hints.py`: Comprehensive tests for file hint extraction
- `scripts/tests/test_overlap_detector.py`: Comprehensive tests for overlap detection

### Implementation
Implemented Option A (Pre-flight overlap detection) combined with Option D (Dependency inference for serialization):

1. **FileHintExtractor** extracts file paths, directories, and scopes from issue content
2. **OverlapDetector** tracks active issue scopes and detects conflicts before dispatch
3. When overlap is detected with `--overlap-detection`:
   - If `serialize_overlapping=True` (default): Issue is deferred and re-queued after overlapping issues complete
   - If `--warn-only`: Just logs a warning and continues

### Usage
```bash
# Enable overlap detection (defer overlapping issues)
ll-parallel --overlap-detection

# Enable overlap detection but only warn (don't defer)
ll-parallel --overlap-detection --warn-only
```

### Verification Results
- Tests: PASS (48/48 new tests pass, 1983/1984 total)
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-01-24 | Priority: P3
