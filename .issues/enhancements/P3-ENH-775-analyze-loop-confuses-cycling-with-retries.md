---
discovered_date: 2026-03-16
discovered_by: scan-codebase
source_loop: issue-refinement
source_state: check_commit
---

# ENH-775: analyze-loop conflates intentional state cycling with stuck retries

## Summary

The `analyze-loop` skill's "ENH — Retry flood" heuristic triggers whenever the same state appears in `state_enter` events 5 or more times, regardless of whether those re-entries are intentional design or actual retry failures. In the `issue-refinement` loop this produced two false positive signals: `check_commit` flagged as "retried 8x" and `route_format` flagged as "retried 9x". Neither state uses a retry counter — both use normal `on_no` routing as part of their designed control flow. True retries (which increment a retry counter and eventually hit `on_retry_exhausted`) are fundamentally different from intentional cycling via `on_yes`/`on_no` routing.

## Root Cause

- **File**: `skills/analyze-loop/SKILL.md` — Signal Rules, "ENH — Retry flood" section
- **Cause**: The heuristic counts raw `state_enter` events without distinguishing how the state was re-entered. States with `on_no` routing that cycle back through the FSM as a designed pattern look identical in the event log to states that are genuinely stuck retrying. The signal title even uses the word "retried", which is inaccurate for cycling states.

## False Signals Generated

**Signal 3** — `check_commit` "retried 8x":
- `check_commit` outputs `COMMIT` only when `N % 5 == 0`, otherwise outputs `SKIP`
- `on_no: evaluate` when SKIP — this is the designed looping behavior
- 8 visits is expected for 8 completed prompt actions over the session
- No retry counter involved; this is pure `on_no` cycling

**Signal 4** — `route_format` "retried 9x":
- `route_format` is a pure routing state with no action, only `evaluate: type: output_contains`
- When the current issue doesn't need formatting, `on_no: route_score` proceeds down the pipeline
- When it does need formatting, `on_yes: format_issues` processes it
- 9 visits means 9 issues were evaluated — entirely correct behavior

## Distinction: True Retries vs. Intentional Cycling

| Property | True retry | Intentional cycling |
|----------|-----------|---------------------|
| Re-entry mechanism | `on_retry` transition | `on_no` or `on_yes` routing |
| Counter incremented | Yes (`retry_count`) | No |
| Has `max_retries` limit | Usually | No |
| Has `on_retry_exhausted` | Usually | No |
| Progress indicator | Same state, no progress | Different state visited between cycles |

## Proposed Fix

Update `skills/analyze-loop/SKILL.md`, Signal Rules, "ENH — Retry flood" section to distinguish true retries from intentional cycling:

**True retry detection** (existing behavior, refined):
- State re-entered via `on_retry` transition (retry counter incremented)
- Flag when retry count is approaching `max_retries` (>= 80% of limit) or has hit `on_retry_exhausted`
- Priority: P3

**Intentional cycling detection** (new, non-alarming):
- State re-entered via `on_no`/`on_yes` routing with no retry counter
- Note the frequency in analysis output, but do **not** generate an issue signal
- Only escalate to a signal if the same state is visited **>20x** with no other states visited in between (true stuck-in-place loop with no progress)
- If escalated: Priority P4, title: `"<state> cycling without progress (>20 consecutive re-entries) in <loop_name> loop"`

**How to detect**: Check whether the state configuration has `on_retry:` or `max_retries:` fields. If absent, any re-entry is cycling, not retrying.

## Files to Modify

- `skills/analyze-loop/SKILL.md` — update "ENH — Retry flood" signal rule to distinguish true retries (via `on_retry`) from intentional cycling (via `on_no`/`on_yes`)

## Acceptance Criteria

- [ ] `analyze-loop` does not flag states that use `on_no` cycling as "retry floods" when they have no `on_retry`/`max_retries` configuration
- [ ] `analyze-loop` still correctly flags states with `on_retry` that are approaching `max_retries`
- [ ] `analyze-loop` flags cycling states only if >20 consecutive re-entries with no intervening state (true stuck loop)
- [ ] Re-running `analyze-loop` over `issue-refinement` history does not produce false positive signals on `check_commit` or `route_format`
- [ ] Analysis output notes high-frequency cycling states as informational (not as issues)

## Labels

`enhancement`, `loops`, `analyze-loop`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P3
