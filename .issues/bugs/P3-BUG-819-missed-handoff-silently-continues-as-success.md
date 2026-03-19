---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 85
---

# BUG-819: Missed handoff (no prompt file) silently continues as success

## Summary

In `WorkerPool._run_with_continuation`, when `detect_context_handoff` returns `True` but `prompt_content` is falsy (no prompt file exists), the loop breaks and returns a result with the last run's exit code. Since handoff is signaled via output content (not exit code), `returncode=0` is returned. The caller in `_process_issue` checks `manage_result.returncode != 0`, so a missed continuation silently passes as successful processing.

## Location

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Line(s)**: 776-780 (at scan commit: 8c6cf90)
- **Anchor**: `in method WorkerPool._run_with_continuation`
- **Code**:
```python
if detect_context_handoff(result.stdout):
    prompt_content = read_continuation_prompt(working_dir)
    if not prompt_content:
        break  # Silently exits loop — result.returncode is 0
```

## Current Behavior

When a context handoff is detected but no prompt file exists, the loop exits silently. The returned `CompletedProcess` has `returncode=0`, causing the caller to treat it as a successful completion.

## Expected Behavior

When a handoff is detected but no prompt file is found, this should be treated as a continuation failure — either log a warning and set a non-zero return code, or retry without the handoff.

## Steps to Reproduce

1. Run `ll-parallel` on an issue that triggers a context handoff
2. Ensure the handoff prompt file is not written (e.g., disk full, permission issue)
3. Observe that the issue is reported as successfully processed despite incomplete work

## Proposed Solution

When `prompt_content` is falsy after a detected handoff, log a warning and set `result = subprocess.CompletedProcess(args=result.args, returncode=1, stdout=result.stdout, stderr=result.stderr + "\nHandoff detected but no prompt file found")` before breaking, so the caller correctly identifies this as a failure.

## Impact

- **Priority**: P3 - Can cause issues to appear completed when they're not, requiring manual re-processing
- **Effort**: Small - Add a warning log and set non-zero return code
- **Risk**: Low - Only changes behavior for an edge case that currently silently fails
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `continuation`

## Status

**Open** | Created: 2026-03-19 | Priority: P3


## Verification Notes

**Verdict**: NEEDS_UPDATE (bug confirmed valid, minor snippet inaccuracy corrected)
**Verified**: 2026-03-19 by `/ll:verify-issues`

- File exists at `scripts/little_loops/parallel/worker_pool.py` ✓
- Method `_run_with_continuation` exists at line 731 ✓
- Core bug confirmed: `if not prompt_content: break` at lines 776–780; the returned `result.returncode` is 0 from the prior successful Claude run; caller at line 437 checks `if manage_result.returncode != 0:` and treats 0 as success ✓
- **Corrected**: Code snippet used `read_handoff_prompt(...)` — actual function is `read_continuation_prompt(working_dir)` (line 775). Updated in snippet above.
- **Confidence**: High — bug logic and location are accurate

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T22:48:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
