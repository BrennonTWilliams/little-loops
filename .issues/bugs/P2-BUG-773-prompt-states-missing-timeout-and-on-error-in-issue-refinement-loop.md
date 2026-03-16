---
discovered_date: 2026-03-16
discovered_by: analyze-loop
source_loop: issue-refinement
source_state: format_issues
confidence_score: 100
outcome_confidence: 93
---

# BUG-773: prompt states missing timeout and on_error in issue-refinement loop

## Summary

Three `action_type: prompt` states in `loops/issue-refinement.yaml` — `format_issues`, `score_issues`, and `refine_issues` — have no `on_error:` handler. When a prompt process is SIGKILL'd (exit_code < 0), `executor.py` at the `exit_code < 0` path routes to `on_error` — if absent, it calls `request_shutdown()` and the loop dies instead of recovering. *(Note: `default_timeout: 3600` is already present at the loop level; the timeout sub-issue is resolved. The remaining bug is solely the missing `on_error` handlers.)*

## Current Behavior

Three `action_type: prompt` states in `loops/issue-refinement.yaml` (`format_issues`, `score_issues`, `refine_issues`) have no `on_error:` handler. When a prompt is SIGKILL'd (exit code < 0), `executor.py` checks for `on_error` in the state config (`executor.py:580–584`). Since none of the three states define `on_error`, `executor.py` calls `request_shutdown()` and the entire loop terminates instead of transitioning to a recovery state. In-progress work is lost and the loop must be restarted manually.

> **Verified 2026-03-16**: `default_timeout: 3600` is already present at the loop level in `loops/issue-refinement.yaml` (line 112) and `default_timeout` is already supported in `schema.py` and `executor.py`. The timeout sub-issue is resolved. Bug scope is narrowed to missing `on_error` handlers only.

## Motivation

The `issue-refinement` loop dies silently when a prompt state is SIGKILL'd, losing all in-progress work and requiring a manual restart. Given that `/ll:format-issue` + `/ll:verify-issues` routinely runs 200–300s, this is not an edge case — the default 120s timeout makes SIGKILL the normal failure mode for `format_issues`. A targeted `on_error` handler restores recoverability with a YAML-only change and no schema impact.

## Loop Context

- **Loop**: `issue-refinement`
- **State**: `format_issues`, `score_issues`, `refine_issues`
- **Signal type**: sigkill
- **Occurrences**: 1 confirmed (format_issues ran 243s and was SIGKILL'd)
- **Last observed**: 2026-03-16

## Root Cause

- **File**: `loops/issue-refinement.yaml` — `format_issues` (~line 70), `score_issues` (~line 78), `refine_issues` (~line 85)
- ~~**Cause 1 — Missing timeout on format_issues and score_issues**~~: *(Resolved — `default_timeout: 3600` is already present at the loop level in `loops/issue-refinement.yaml:112` and is supported by `schema.py` and `executor.py`. No per-state timeouts needed.)*
- **Cause 2 — Missing on_error on all three states**: When a prompt is SIGKILL'd (exit_code < 0), `executor.py` at the `exit_code < 0` check path (around line 580) checks for an `on_error` transition. If `on_error` is absent, the executor calls `request_shutdown()` and terminates the loop entirely. There is no recovery path; progress is lost and the loop must be manually restarted.

## Evidence

`format_issues` state in the loop YAML:
```yaml
format_issues:
  action_type: prompt
  action: |
    Run these commands in order for issue ${captured.issue_id.output}:
    1. /ll:format-issue ${captured.issue_id.output} --auto
    2. /ll:verify-issues ${captured.issue_id.output} --auto
  next: check_commit
```

No `on_error:` → loop terminates on SIGKILL. *(Loop-level `default_timeout: 3600` at `loops/issue-refinement.yaml:112` already covers the timeout concern.)*

No per-state `timeout:` exists on any of the three states; all rely on the loop-level `default_timeout: 3600`.

Executor shutdown path (`executor.py` around line 580):
```python
if exit_code < 0:  # SIGKILL or signal
    on_error = state_config.get("on_error")
    if on_error:
        return self._transition(on_error)
    else:
        self.request_shutdown()  # loop dies here
```

## Steps to Reproduce

1. Start the `issue-refinement` loop: `ll-loop run loops/issue-refinement.yaml`
2. Wait for the loop to reach the `format_issues` state and invoke `/ll:format-issue` + `/ll:verify-issues` on an issue
3. Observe the prompt encountering an error or being SIGKILL'd (running beyond the OS process limit or killed externally)
4. **Observe**: The OS sends SIGKILL; `executor.py` calls `request_shutdown()` and the loop terminates entirely
5. **Expected**: The loop transitions to `check_commit` and continues processing

## Expected Behavior

When a prompt state is SIGKILL'd or otherwise errors, the loop should route to a recovery state (e.g., `check_commit`) rather than terminating. Prompt states that invoke multi-step skills should have timeouts generous enough to accommodate realistic runtimes.

## Proposed Solution

Add `on_error: check_commit` to all three prompt states (`format_issues`, `score_issues`, `refine_issues`) in `loops/issue-refinement.yaml`. Routing to `check_commit` mirrors the `next:` behavior of successful states and ensures SIGKILL'd prompts count toward the periodic commit cadence before re-evaluating.

`default_timeout: 3600` is already present at the loop level — no per-state timeout changes needed.

```yaml
format_issues:
  action_type: prompt
  on_error: check_commit   # add this
  action: |
    ...

score_issues:
  action_type: prompt
  on_error: check_commit   # add this
  action: |
    ...

refine_issues:
  action_type: prompt
  on_error: check_commit   # add this
  action: |
    ...
```

## Integration Map

### Files to Modify
- `loops/issue-refinement.yaml` — add `on_error: check_commit` to `format_issues`, `score_issues`, `refine_issues` (3-line YAML-only change)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — contains the `on_error` routing logic at the `exit_code < 0` path (read-only reference; no changes needed)

### Similar Patterns
- Other loop YAML files in `loops/` — audit for prompt states missing `on_error`

### Tests
- TBD — verify loop recovery behavior: SIGKILL'd prompt state should transition to `check_commit` not terminate

### Documentation
- N/A

### Configuration
- N/A (`default_timeout: 3600` already in `loops/issue-refinement.yaml:112`; `schema.py` and `executor.py` already support it)

## Implementation Steps

1. Add `on_error: check_commit` to `format_issues`, `score_issues`, and `refine_issues` in `loops/issue-refinement.yaml`
2. Audit remaining prompt states in `loops/issue-refinement.yaml` for missing `on_error`
3. Verify loop routes to `check_commit` on SIGKILL instead of terminating

## Acceptance Criteria

- [ ] `format_issues` has `on_error: check_commit` in `loops/issue-refinement.yaml`
- [ ] `score_issues` has `on_error: check_commit` in `loops/issue-refinement.yaml`
- [ ] `refine_issues` has `on_error: check_commit` in `loops/issue-refinement.yaml`
- [ ] A SIGKILL'd prompt state routes to `check_commit` rather than terminating the loop

## Impact

- **Priority**: P2 — Loop stability regression; SIGKILL is the normal failure mode for `format_issues` given the 120s default vs 200–300s actual runtime; in-progress work is lost on every occurrence
- **Effort**: Small — YAML-only change for the immediate fix; 3 fields in 1 file; no schema or executor changes required
- **Risk**: Low — `on_error` and `timeout` are additive config fields; no effect on the happy path; no schema changes in the immediate fix
- **Breaking Change**: No

## Verification Notes

**Verified 2026-03-16** — Verdict: NEEDS_UPDATE (corrected in this pass)

**Still valid:**
- `format_issues`, `score_issues`, `refine_issues` in `loops/issue-refinement.yaml` confirmed to have no `on_error:` field (lines 70, 77, 83)
- `executor.py` SIGKILL routing at `exit_code < 0` path (around line 580) confirmed accurate

**Stale claims corrected:**
- `default_timeout: 3600` is already present at `loops/issue-refinement.yaml:112` — timeout sub-issue is resolved; no per-state timeouts are needed
- `default_timeout` already supported in `scripts/little_loops/fsm/schema.py:407` and `executor.py:640,644`
- Claim "`refine_issues` already has `timeout: 600`" was false — no per-state timeout exists on any of the three states; all rely on the loop-level `default_timeout: 3600`
- Removed "Preferred fix (depends on ENH-776)" and "Interim fix" sections from Proposed Solution — `default_timeout` is already implemented
- Simplified Implementation Steps (removed timeout-related step, removed ENH-776 deferral)
- Simplified Acceptance Criteria (removed "Once ENH-776 lands" section)

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-03-16T18:57:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T18:53:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
