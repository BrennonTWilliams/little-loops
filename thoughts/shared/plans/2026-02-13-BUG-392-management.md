# BUG-392: Dependency validator false "nonexistent" for cross-type references - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-392-dependency-validator-false-nonexistent-cross-type-references.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `validate_dependencies()` at `dependency_mapper.py:528-578` builds `active_ids` from only the issues passed in (line 550), then checks `blocked_by` refs against `all_known = active_ids | completed` (line 551). When called from sprint context, this is sprint-only issues.
- `DependencyGraph.from_issues()` at `dependency_graph.py:50-100` builds `all_issue_ids` from only the issues passed in (line 86), and logs "blocked by unknown issue" for any ref not in that set (line 93-94).
- Sprint CLI (`cli/sprint.py`) calls both functions with only sprint-scoped issues at lines 409, 443, 739, 743.
- Neither call site passes `completed_ids`, and neither function has a way to know about issues that exist on disk but aren't in the working set.

### Patterns to Follow
- `find_issues()` in `issue_parser.py:469-521` already scans all category directories
- `SprintManager.validate_issues()` at `sprint.py:307-329` resolves issue IDs across all categories via glob
- `_load_issues()` in `dependency_mapper.py:902-944` already gathers `completed_ids` separately
- The existing three-way classification pattern: broken refs / stale completed refs / valid — needs a fourth: "exists but not in working set"

### Reusable Code
- `find_issues()` from `issue_parser.py` — can be used to get all active issue IDs, but is heavy (parses all files)
- `SprintManager.validate_issues()` — already does cross-category glob lookup, but returns paths not just IDs
- The `_load_issues()` completed ID scanning pattern (regex on filenames) — reuse for all-active-IDs scanning

## Desired End State

1. `validate_dependencies()` accepts an optional `all_active_ids` parameter — a set of all issue IDs that exist on disk (across all categories)
2. When a `blocked_by` ref is not in the working set but IS in `all_active_ids`, it is NOT reported as a broken ref — it's silently accepted (the issue exists, just isn't in this sprint)
3. `DependencyGraph.from_issues()` accepts the same parameter and does NOT log "blocked by unknown issue" for refs that exist in `all_active_ids`
4. Sprint CLI call sites gather `all_active_ids` and pass it through
5. Warning messages distinguish "truly nonexistent" from issues that exist elsewhere

### How to Verify
- Existing tests still pass (no regression)
- New test: BUG referencing ENH (both in issues list) — not flagged as broken
- New test: BUG referencing ENH (ENH not in issues list but in `all_active_ids`) — not flagged as broken
- New test: BUG referencing NONEXISTENT-999 (not anywhere) — still flagged as broken

## What We're NOT Doing

- Not changing how sprints load their issue sets
- Not adding "not in sprint" as a distinct warning category (that's just noise)
- Not modifying `_load_issues()` or `find_issues()` — we'll create a lightweight ID-scanning helper
- Not changing the `ll-deps` CLI behavior (it already handles completed IDs; the same pattern will apply)

## Problem Analysis

The root cause is that both `validate_dependencies()` and `DependencyGraph.from_issues()` treat their input `issues` list as the complete universe of known issues. Any `blocked_by` reference to an issue outside that set is flagged as nonexistent/unknown. When called from sprint context with only sprint issues, valid cross-type (or simply non-sprint) references produce false positives.

## Solution Approach

Add an `all_known_ids` parameter to both `validate_dependencies()` and `DependencyGraph.from_issues()`. This set represents all issue IDs that exist on disk (active + completed). The validation logic checks refs against this broader set before declaring them broken. Create a lightweight utility function to scan all issue directories for IDs without fully parsing files.

## Implementation Phases

### Phase 1: Add `gather_all_issue_ids()` utility

**File**: `scripts/little_loops/dependency_mapper.py`

Add a utility function that scans all issue category directories + completed directory for issue IDs by regex on filenames (same pattern used in `_load_issues()` for completed IDs).

```python
def gather_all_issue_ids(issues_dir: Path) -> set[str]:
    """Scan all issue directories for issue IDs (lightweight, filename-only)."""
    import re
    ids: set[str] = set()
    for subdir in ["bugs", "features", "enhancements", "completed"]:
        d = issues_dir / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            match = re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)
            if match:
                ids.add(f"{match.group(1)}-{match.group(2)}")
    return ids
```

### Phase 2: Update `validate_dependencies()`

**File**: `scripts/little_loops/dependency_mapper.py:528-578`

Add `all_known_ids` parameter. Change the broken ref check to only flag refs that are not in `all_known_ids` (when provided) or not in the original `all_known` set (backwards-compatible).

```python
def validate_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
) -> ValidationResult:
```

Change line 562:
```python
# Old: if ref_id not in all_known:
# New:
if ref_id not in all_known:
    if all_known_ids and ref_id in all_known_ids:
        pass  # Exists on disk but not in working set — not broken
    else:
        result.broken_refs.append((issue.issue_id, ref_id))
```

### Phase 3: Update `DependencyGraph.from_issues()`

**File**: `scripts/little_loops/dependency_graph.py:50-100`

Add `all_known_ids` parameter. Change the unknown issue check to only warn for truly nonexistent IDs.

```python
@classmethod
def from_issues(
    cls,
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
) -> DependencyGraph:
```

Change lines 92-95:
```python
if blocker_id not in all_issue_ids:
    if all_known_ids is None or blocker_id not in all_known_ids:
        logger.warning(f"Issue {issue.issue_id} blocked by unknown issue {blocker_id}")
    continue
```

### Phase 4: Update `analyze_dependencies()` to pass through

**File**: `scripts/little_loops/dependency_mapper.py:581-607`

Add `all_known_ids` parameter and pass it to `validate_dependencies()`.

### Phase 5: Update sprint CLI call sites

**File**: `scripts/little_loops/cli/sprint.py`

At the call sites in `_cmd_sprint_show()` and `_cmd_sprint_run()`, gather `all_known_ids` using the new utility and pass it through to both `analyze_dependencies()` and `DependencyGraph.from_issues()`.

### Phase 6: Add tests

**File**: `scripts/tests/test_dependency_mapper.py`
- Test: ref to issue not in working set but in `all_known_ids` → not broken
- Test: ref to truly nonexistent issue → still broken
- Test: `gather_all_issue_ids()` returns IDs from all category dirs

**File**: `scripts/tests/test_dependency_graph.py`
- Test: blocker not in issues list but in `all_known_ids` → no warning logged
- Test: blocker truly nonexistent → warning still logged

## Success Criteria

- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- `validate_dependencies()` with `all_known_ids` containing out-of-set refs
- `DependencyGraph.from_issues()` with `all_known_ids` containing out-of-set blockers
- `gather_all_issue_ids()` with tmp_path fixture
- Backward compatibility: all existing tests pass without providing `all_known_ids`

## References
- Original issue: `.issues/bugs/P3-BUG-392-dependency-validator-false-nonexistent-cross-type-references.md`
- Key pattern: `dependency_mapper.py:938-940` (completed ID regex scanning)
- Test fixture: `test_dependency_mapper.py:916-953` (`_setup_sprint_project`)
