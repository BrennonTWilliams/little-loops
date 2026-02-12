---
discovered_commit: 5235bca
discovered_date: 2026-01-09
discovered_source: ll-auto-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# BUG-010: ll-auto manage_issue uses stale abstract ID after ready_issue path fallback

## Summary

When `ready_issue` fails to match the correct file using an abstract issue ID (e.g., `BUG-1`) and the fallback mechanism retries with an explicit file path, the subsequent `manage_issue` command still uses the original abstract ID instead of the validated path. This causes `manage_issue` to fail with "Issue not found".

## Evidence from Log

**Log File**: `ll-auto-blender-agents-debug.log`
**Log Type**: ll-auto
**External Repo**: `<external-repo>`
**Occurrences**: 1
**Affected External Issues**: BUG-1 (mapped to P1-DOC-001)

### Sample Log Output

```
Processing: BUG-1 - Fix layer count inconsistency in abstraction documentation
[21:18:46] Running: claude --dangerously-skip-permissions -p '/ll:ready_issue BUG-1'
  ## VALIDATED_FILE
  .issues/completed/P3-BUG-001-misleading-claude-cli-install-message.md  <-- WRONG FILE
[21:19:22] ready_issue verdict: CLOSE
[21:19:22] Path mismatch: ready_issue validated '.issues/completed/P3-BUG-001-...' but expected '.../P1-DOC-001-...'
[21:19:22] Attempting fallback: retrying ready_issue with explicit file path...
[21:19:22] Running: claude --dangerously-skip-permissions -p '/ll:ready_issue .issues/bugs/P1-DOC-001-fix-layer-count-inconsistency.md'
  ## VALIDATED_FILE
  `.issues/bugs/P1-DOC-001-fix-layer-count-inconsistency.md`  <-- CORRECT FILE
[21:21:33] Fallback succeeded: validated correct file
[21:21:33] Running: claude --dangerously-skip-permissions -p '/ll:manage_issue bug fix BUG-1'
  **Issue not found**: BUG-1 doesn't exist in the project.  <-- FAILURE: still using abstract ID
```

## Current Behavior

1. `ll-auto` queues issue with abstract ID `BUG-1` mapped to path `P1-DOC-001-*.md`
2. `ready_issue BUG-1` matches wrong file (completed `P3-BUG-001-*.md`)
3. Fallback retries with explicit path `.issues/bugs/P1-DOC-001-*.md` - succeeds
4. Code updates `info.path` to the validated path (line 380)
5. **BUG**: `manage_issue` command at line 535 still uses `info.issue_id` (`BUG-1`)
6. `manage_issue` cannot find `BUG-1` because the external repo uses `P1-DOC-001` naming

## Expected Behavior

After the ready_issue fallback succeeds with an explicit path:
1. Either update `info.issue_id` to match the actual file's ID pattern
2. Or pass the validated path to `manage_issue` instead of the abstract ID

## Root Cause

In `scripts/little_loops/issue_manager.py:535`:
```python
result = run_with_continuation(
    f"/ll:manage_issue {type_name} {action} {info.issue_id}",  # <-- Uses stale info.issue_id
```

When the fallback at lines 374-437 updates `info.path` to the validated file, it doesn't update `info.issue_id`. The external repository uses a different ID scheme (`P1-DOC-001-*`) than what `ll-auto` generated (`BUG-1`).

## Affected Files

- `scripts/little_loops/issue_manager.py:535` - manage_issue command construction
- `scripts/little_loops/issue_manager.py:374-437` - Fallback logic that updates path but not issue_id

## Reproduction Steps

1. Have an external repo with issue files named `P[0-5]-TYPE-NNN-*.md`
2. Create a queue entry with abstract ID like `BUG-1`
3. Have a completed issue whose filename could partially match the abstract ID
4. Run `ll-auto`
5. Observe ready_issue fallback works but manage_issue fails

## Proposed Fix

Option A: Pass the validated path instead of abstract ID:
```python
# After fallback, use path for manage_issue
issue_arg = str(info.path) if validated_via_fallback else info.issue_id
result = run_with_continuation(
    f"/ll:manage_issue {type_name} {action} {issue_arg}",
    ...
)
```

Option B: Extract issue ID from validated filename:
```python
# After fallback, extract ID from validated path
if validated_via_fallback:
    info.issue_id = extract_issue_id_from_path(info.path)
```

Option C: Use relative path for both commands consistently:
```python
relative_path = _compute_relative_path(info.path)
result = run_with_continuation(
    f"/ll:manage_issue {type_name} {action} {relative_path}",
    ...
)
```

## Impact

- **Severity**: Medium (P2) - Causes processing failures but doesn't corrupt data
- **Frequency**: Occurs when ready_issue fallback is triggered AND external repo uses different ID scheme
- **Data Risk**: Low - No data loss, just failed processing

---

## Status
**Open** | Created: 2026-01-09 | Priority: P2

## Related Issues

- [BUG-001](../completed/P0-BUG-001-ready-issue-glob-matching-wrong-files.md) - Fixed: loose glob matching (root cause of fallback being needed)
- [BUG-002](../completed/P1-BUG-002-ll-auto-no-validation-of-ready-issue-target.md) - Fixed: Added validated path tracking (enabled the fallback)

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-09
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_manager.py`: Added `validated_via_fallback` tracking (line 365-367) and set it to True when fallback succeeds (line 465). Modified manage_issue command construction (lines 565-571) to use relative path instead of stale issue_id when fallback was used.
- `scripts/tests/test_issue_manager.py`: Added `test_manage_issue_uses_path_after_fallback` test to verify the fix ensures manage_issue receives the path, not stale ID.

### Verification Results
- Tests: PASS (467 tests)
- Lint: PASS
- Types: PASS
