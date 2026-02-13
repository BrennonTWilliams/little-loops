# BUG-235: ll-sync pull --labels flag accepted but never used - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-235-sync-pull-labels-flag-not-used.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `pull_issues()` method at `scripts/little_loops/sync.py:555` accepts a `labels` parameter but never uses it. The `gh issue list` command at line 574-577 is constructed with a static argument list that never includes `--label` flags regardless of the `labels` parameter value.

### Key Discoveries
- `sync.py:574-577`: `gh issue list` command is built without label filtering
- `sync.py:555`: Method signature accepts `labels: list[str] | None` but it's unused
- `cli.py:2184-2188`: CLI correctly parses `--labels` and passes to `pull_issues()`
- `sync.py:489-491`: Push operations already use the pattern `args.extend(["--label", label])` for label flags

## Desired End State

When `--labels` is provided, only GitHub issues with those labels should be pulled. The `gh issue list` command should include `--label` flags for each specified label.

### How to Verify
- `ll-sync pull --labels bug` should only pull issues labeled "bug"
- `ll-sync pull` (no labels) should continue pulling all issues as before
- Tests verify that `--label` flags are appended to the `gh` command when labels are provided

## What We're NOT Doing

- Not changing push label behavior
- Not adding label filtering to `get_status()`
- Not modifying the CLI argument parsing (it already works correctly)

## Problem Analysis

The `labels` parameter is accepted in `pull_issues()` but the method body never references it. The `gh issue list` command at line 574-577 uses a hardcoded static list of arguments.

## Solution Approach

Follow the existing pattern from `_create_github_issue()` at `sync.py:489-491` which uses `args.extend(["--label", label])` to append label flags. Apply the same pattern to the `gh issue list` command in `pull_issues()`.

## Implementation Phases

### Phase 1: Fix label filtering in `pull_issues()`

#### Overview
Modify the `gh issue list` command construction to conditionally include `--label` flags when `labels` is provided.

#### Changes Required

**File**: `scripts/little_loops/sync.py`
**Changes**: Build the `gh issue list` args list dynamically, appending `--label` for each label when provided.

```python
# Build gh issue list command
gh_args = ["issue", "list", "--json", "number,title,body,labels,state,url", "--limit", "100"]
if labels:
    for label in labels:
        gh_args.extend(["--label", label])

cmd_result = _run_gh_command(gh_args, self.logger)
```

### Phase 2: Add tests for label filtering

#### Overview
Add tests that verify `--label` flags are included in the `gh` command when `labels` are provided, and not included when `labels` is None.

#### Changes Required

**File**: `scripts/tests/test_sync.py`
**Changes**: Add two test methods to `TestGitHubSyncManager`:

1. `test_pull_with_labels_filters_gh_command` - Verify `--label` flags are passed to `_run_gh_command` when labels are provided
2. `test_pull_without_labels_no_filter` - Verify no `--label` flags when labels is None

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Test that `pull_issues(["bug"])` includes `--label bug` in the `gh` command args
- Test that `pull_issues(["bug", "enhancement"])` includes both `--label bug` and `--label enhancement`
- Test that `pull_issues(None)` does not include any `--label` flags
- Test that `pull_issues()` (no args) does not include any `--label` flags

## References

- Original issue: `.issues/bugs/P2-BUG-235-sync-pull-labels-flag-not-used.md`
- Label flag pattern: `scripts/little_loops/sync.py:489-491` (`_create_github_issue`)
- Pull method: `scripts/little_loops/sync.py:555-616`
- CLI parsing: `scripts/little_loops/cli.py:2184-2188`
