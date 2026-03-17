# ENH-775: analyze-loop conflates intentional state cycling with stuck retries

**Date**: 2026-03-17
**Issue**: ENH-775
**Action**: improve
**Confidence**: 100/100

## Problem

The `analyze-loop` skill flags any state appearing 5+ times in `state_enter` events as a "retry flood" ENH signal. This produces false positives for states that use `on_no`/`on_yes` routing as designed control flow (e.g., `check_commit` in `issue-refinement` loop, visited 8x intentionally).

True retries (via `on_retry`/`max_retries` config) are fundamentally different from intentional cycling.

## Solution

Use the loop config already loaded in Step 2 (`ll-loop show <loop_name> --json`) to check whether a flagged state has `on_retry` or `max_retries` configuration. If absent, all re-entries are intentional cycling — report informally, no issue signal.

Also add `retry_exhausted` event type to the event parsing table (currently missing; emitted by executor when retry limit exceeded).

## Files to Modify

1. `skills/analyze-loop/SKILL.md:84-91` — add `retry_exhausted` to event parsing table
2. `skills/analyze-loop/SKILL.md:124-128` — replace "ENH — Retry flood" with two rules:
   - True retry flood (has `on_retry`/`max_retries`): ENH P3 signal
   - Intentional cycling (no retry config): informational note only; escalate to ENH P4 only if >20 consecutive same-state re-entries
3. `docs/reference/COMMANDS.md:380` — update signal detection summary line

## Implementation Steps

- [x] Read issue file and target files
- [ ] Add `retry_exhausted` to event parsing table
- [ ] Replace retry flood signal rule with disambiguated version
- [ ] Update COMMANDS.md summary line
- [ ] Verify logic is consistent with issue acceptance criteria
- [ ] Complete issue lifecycle

## No Open Questions

- Detection approach: YAML-based (state config already loaded in Step 2) — cleanest
- Consecutive re-entries for stuck-loop detection: use sequence scan of `state_enter` events checking for runs ≥20 with no intervening different state
