# BUG-007: Worktree isolation - files leak to main repo - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix
- **Status**: Reopened (2026-01-12)

## Current State Analysis

The previous fix implemented two changes to prevent file leaks from worktrees:
1. Copy `.claude/` directory to worktrees (`worker_pool.py:405-416`)
2. Set `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable (`subprocess_utils.py:84-87`)

Despite these fixes, leaks continue to occur (BUG-636 evidence from blender-agents repo).

### Key Discovery

The `_detect_worktree_model_via_api()` function at `worker_pool.py:440-475` invokes Claude CLI **without** the environment variable fix:

- **Line 454-466**: Uses `subprocess.run()` directly instead of shared `run_claude_command()`
- **Missing**: No `env` parameter with `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`
- **Impact**: First Claude CLI invocation in worktree may establish cached project root incorrectly

**Evidence from reopened issue**:
```
[12:31:27] BUG-636 leaked 1 file(s) to main repo: ['issues/bugs/P1-BUG-636-...']
```

The leaked file was an issue file (not source code), suggesting Claude Code established wrong project root during initial API call.

### Current Behavior
- `_detect_worktree_model_via_api()` (line 454): `subprocess.run()` - NO env var
- `run_claude_command()` (subprocess_utils.py:86): Sets env var correctly

## Desired End State

All Claude CLI invocations from worker worktrees should have the `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable set to ensure consistent project root detection.

### How to Verify
- Run parallel processing with `--show-model` flag enabled
- No files should leak to main repo during worktree operations
- Existing leak detection should report zero leaked files

## What We're NOT Doing

- Not changing the project root detection algorithm (external to this codebase)
- Not removing the existing leak detection/cleanup safety net (defense in depth)
- Not refactoring the entire subprocess handling architecture
- Not changing behavior for scenarios without worktrees

## Problem Analysis

### Root Cause
The `_detect_worktree_model_via_api()` function bypasses the shared `run_claude_command()` function in `subprocess_utils.py`, which is the centralized location for setting the BUG-007 environment variable fix. This creates an inconsistency where:

1. Model detection API call: No `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`
2. All subsequent Claude calls: Have the environment variable set

If Claude Code caches project root detection on first invocation, the model detection call could establish the wrong root before the proper environment is set.

### Contributing Factors
- The model detection function predates the environment variable fix
- It uses `subprocess.run()` for simplicity (one-shot call with timeout)
- The fix was added to `subprocess_utils.py` but not backported to all call sites

## Solution Approach

Add the `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable to the `_detect_worktree_model_via_api()` function's subprocess call. This ensures consistency across all Claude CLI invocations from worktrees.

The fix is minimal and surgical - just add the `env` parameter with the same pattern used in `subprocess_utils.py`.

## Implementation Phases

### Phase 1: Add Environment Variable to Model Detection

#### Overview
Add the environment variable to ensure the first Claude CLI invocation in each worktree has the same project root behavior as subsequent invocations.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Location**: Lines 452-466 in `_detect_worktree_model_via_api()`
**Changes**: Add `env` parameter to `subprocess.run()` call

```python
# Before (current code):
result = subprocess.run(
    [
        "claude",
        "-p",
        "reply with just 'ok'",
        "--output-format",
        "json",
    ],
    cwd=worktree_path,
    capture_output=True,
    text=True,
    timeout=30,
)

# After (fixed code):
# Set environment to keep Claude in the project working directory (BUG-007)
env = os.environ.copy()
env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"

result = subprocess.run(
    [
        "claude",
        "-p",
        "reply with just 'ok'",
        "--output-format",
        "json",
    ],
    cwd=worktree_path,
    capture_output=True,
    text=True,
    timeout=30,
    env=env,
)
```

#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification** (requires human judgment):
- [ ] Run `ll-parallel` with `--show-model` flag on a test repo with multiple issues
- [ ] Verify no files leak to main repo during parallel processing

---

### Phase 2: Update Issue Documentation

#### Overview
Update the BUG-007 issue file to document the additional fix applied.

#### Changes Required

**File**: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
**Changes**: Add resolution section documenting the fix

```markdown
---

## Resolution (Second Fix)

- **Action**: fix
- **Completed**: 2026-01-12
- **Status**: Completed

### Root Cause Identified
The `_detect_worktree_model_via_api()` function in `worker_pool.py` invoked Claude CLI without
the `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable that was added to
`subprocess_utils.py` as the BUG-007 fix. This meant the first Claude CLI invocation in each
worktree (model detection) could establish a cached project root incorrectly, causing subsequent
file operations to leak to the main repository.

### Changes Made
- `scripts/little_loops/parallel/worker_pool.py`: Added environment variable to
  `_detect_worktree_model_via_api()` function's subprocess call (lines ~452-466)

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS
```

#### Success Criteria

**Automated Verification**:
- [ ] Issue file is valid markdown
- [ ] Resolution section follows standard format

---

## Testing Strategy

### Unit Tests
The existing test suite covers worker pool functionality. No new tests are needed as this is a configuration fix, not a behavioral change.

### Integration Tests
The fix should be verified through actual parallel processing runs:
1. Run `ll-parallel` with `--show-model` enabled
2. Process multiple issues in parallel
3. Verify leak detection reports 0 leaked files
4. Check that worktree operations complete successfully

## References

- Original issue: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
- Existing fix in subprocess_utils: `scripts/little_loops/subprocess_utils.py:84-87`
- Model detection function: `scripts/little_loops/parallel/worker_pool.py:440-475`
- Related external issue: GitHub #8771 (Claude Code project root detection in worktrees)
