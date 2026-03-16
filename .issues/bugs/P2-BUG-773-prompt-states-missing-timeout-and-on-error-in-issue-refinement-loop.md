---
discovered_date: 2026-03-16
discovered_by: analyze-loop
source_loop: issue-refinement
source_state: format_issues
---

# BUG-773: prompt states missing timeout and on_error in issue-refinement loop

## Summary

Three `action_type: prompt` states in `loops/issue-refinement.yaml` — `format_issues`, `score_issues`, and `refine_issues` — are vulnerable to silent termination when Claude takes longer than expected or is killed by the OS. `format_issues` and `score_issues` have no `timeout:` configured (defaulting to 120s), but running `/ll:format-issue` + `/ll:verify-issues` routinely takes 200–300s. None of the three states has an `on_error:` handler. When a prompt process is SIGKILL'd (exit_code < 0), `executor.py:580-585` routes to `on_error` — if absent, it calls `request_shutdown()` and the loop dies instead of recovering.

## Loop Context

- **Loop**: `issue-refinement`
- **State**: `format_issues`, `score_issues`, `refine_issues`
- **Signal type**: sigkill
- **Occurrences**: 1 confirmed (format_issues ran 243s and was SIGKILL'd)
- **Last observed**: 2026-03-16

## Root Cause

- **File**: `loops/issue-refinement.yaml` — `format_issues` (~line 70), `score_issues` (~line 78), `refine_issues` (~line 85)
- **Cause 1 — Missing timeout on format_issues and score_issues**: Both states default to the executor's 120s prompt timeout. Running `/ll:format-issue` + `/ll:verify-issues` together regularly takes 200–300s, causing SIGKILL before completion. (`refine_issues` already has `timeout: 600` and is not affected by this sub-issue.)
- **Cause 2 — Missing on_error on all three states**: When a prompt is SIGKILL'd (exit_code < 0), `executor.py:580-585` checks for an `on_error` transition. If `on_error` is absent, the executor calls `request_shutdown()` and terminates the loop entirely. There is no recovery path; progress is lost and the loop must be manually restarted.

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

No `timeout:` → defaults to 120s. No `on_error:` → loop terminates on SIGKILL.

`refine_issues` already has `timeout: 600` but also lacks `on_error`.

Executor shutdown path (`executor.py:580-585`):
```python
if exit_code < 0:  # SIGKILL or signal
    on_error = state_config.get("on_error")
    if on_error:
        return self._transition(on_error)
    else:
        self.request_shutdown()  # loop dies here
```

## Expected Behavior

When a prompt state is SIGKILL'd or otherwise errors, the loop should route to a recovery state (e.g., `check_commit` or `evaluate`) rather than terminating. Prompt states that invoke multi-step skills should have timeouts generous enough to accommodate realistic runtimes.

## Proposed Fix

In `loops/issue-refinement.yaml`, add `timeout:` and `on_error:` to all three prompt states:

```yaml
format_issues:
  action_type: prompt
  timeout: 360
  on_error: check_commit
  action: |
    Run these commands in order for issue ${captured.issue_id.output}:
    1. /ll:format-issue ${captured.issue_id.output} --auto
    2. /ll:verify-issues ${captured.issue_id.output} --auto
  next: check_commit

score_issues:
  action_type: prompt
  timeout: 360
  on_error: check_commit
  action: |
    Run this command for issue ${captured.issue_id.output}:
    /ll:confidence-check ${captured.issue_id.output} --auto
  next: check_commit

refine_issues:
  action_type: prompt
  timeout: 600      # already present; keep as-is
  on_error: check_commit
  action: |
    Run these commands in order for issue ${captured.issue_id.output}:
    1. /ll:refine-issue ${captured.issue_id.output} --auto
    2. /ll:confidence-check ${captured.issue_id.output} --auto
  next: check_commit
```

Routing `on_error` to `check_commit` (instead of `evaluate`) means the iteration still counts toward the periodic commit cadence before the loop re-evaluates. This mirrors the `next:` behavior of successful prompt states.

## Files to Modify

- `loops/issue-refinement.yaml` — add `timeout: 360` to `format_issues` and `score_issues`; add `on_error: check_commit` to all three prompt states
- `scripts/little_loops/fsm/executor.py:580-585` — reference only (SIGKILL routing logic; no change needed)

## Acceptance Criteria

- [ ] `format_issues` has `timeout: 360` (or higher) set in `loops/issue-refinement.yaml`
- [ ] `score_issues` has `timeout: 360` (or higher) set in `loops/issue-refinement.yaml`
- [ ] All three prompt states (`format_issues`, `score_issues`, `refine_issues`) have `on_error: check_commit`
- [ ] A SIGKILL'd prompt state routes to `check_commit` rather than terminating the loop
- [ ] Loop survives a simulated SIGKILL on a prompt state and continues to the next iteration

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P2
