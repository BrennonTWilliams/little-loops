---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# BUG-928: `confidence_check` timeout skips `verify_issue` in refine-to-ready loop

## Summary

In `refine-to-ready-issue.yaml`, when the `confidence_check` state's LLM structured evaluation times out, the sub-loop routes directly to the `failed` terminal state, bypassing `verify_issue`. The issue never gets `/ll:verify-issues` recorded in its session log, causing `ll-issues next-action` to return `NEEDS_VERIFY` for that issue on every subsequent parent loop iteration — creating an infinite re-processing cycle.

## Context

**Conversation mode**: Identified while reviewing a bug report (plan `keen-whistling-spring.md`) about the `issue-refinement` loop being stuck on a single issue across 15+ iterations. The root cause analysis confirmed this is one of two interacting bugs causing the loop to starve all other issues.

Confirmed via code inspection:
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:44` — `confidence_check.on_error: failed`
- `scripts/little_loops/cli/issues/next_action.py:38` — `if "/ll:verify-issues" not in issue.session_commands` → returns `NEEDS_VERIFY`

## Current Behavior

When the `confidence_check` state's LLM structured evaluation times out in `refine-to-ready-issue.yaml`, the FSM routes directly to the `failed` terminal state via `on_error: failed`. The `verify_issue` state is never reached, leaving no `/ll:verify-issues` entry in the issue's session log. On subsequent parent loop iterations, `ll-issues next-action` returns `NEEDS_VERIFY` because the session log lacks the verify command — causing the loop to re-queue the issue indefinitely.

## Expected Behavior

On `confidence_check` timeout, the FSM should inspect the issue's frontmatter for existing `confidence_score` and `outcome_confidence` values. If both values meet the configured thresholds, the FSM should proceed to `verify_issue`. Only if scores are absent or below threshold should it fall back to `failed`.

## Motivation

This bug causes the `issue-refinement` parent loop to starve all other issues by infinitely re-processing the stuck issue. Confirmed to cause 15+ iterations on a single issue (observed in sprint run analysis, plan `keen-whistling-spring.md`). Without this fix, any LLM eval timeout in `confidence_check` permanently blocks loop progress.

## Steps to Reproduce

1. Run the `refine-to-ready` loop on an issue that has `confidence_score` and `outcome_confidence` in its frontmatter
2. Simulate or wait for a timeout in the `confidence_check` LLM evaluation
3. Observe the loop routes to `failed` without visiting `verify_issue`
4. Check the issue's session log: `/ll:verify-issues` is absent
5. Run `ll-issues next-action <issue-id>`: it returns `NEEDS_VERIFY`
6. Observe the parent loop re-queues the same issue on every subsequent iteration

## Root Cause

**File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
**State**: `confidence_check` (lines 31–44)
**Function**: FSM state transition on LLM eval error

When `evaluate.type: llm_structured` times out:
1. `on_error: failed` routes to the `failed` terminal state
2. `verify_issue` is never reached
3. The issue accumulates no `/ll:verify-issues` session log entry
4. `next-action` perpetually re-queues it as `NEEDS_VERIFY`

The correct behavior on timeout should be: check whether frontmatter already contains `confidence_score` and `outcome_confidence` values above thresholds. If so, proceed to `verify_issue`; only fall back to `failed` if scores are absent or insufficient.

## Proposed Solution

Change `confidence_check.on_error` from `failed` to a new `check_scores_from_file` state:

```yaml
confidence_check:
  action: "/ll:confidence-check ${captured.issue_id.output}"
  action_type: slash_command
  evaluate:
    type: llm_structured
    ...
  on_yes: verify_issue
  on_no: refine_issue
  on_error: check_scores_from_file   # <-- was: failed

check_scores_from_file:
  action: |
    ll-issues show ${captured.issue_id.output} --field confidence_score --field outcome_confidence
  action_type: shell
  evaluate:
    type: output_contains
    pattern: "..."  # both scores above threshold
  on_yes: verify_issue
  on_no: failed
```

## Implementation Steps

1. Add `check_scores_from_file` state to `refine-to-ready-issue.yaml` that reads `confidence_score` and `outcome_confidence` from the issue frontmatter via `ll-issues show` or direct YAML parsing
2. Change `confidence_check.on_error: failed` → `on_error: check_scores_from_file`
3. In `check_scores_from_file`, compare scores against `context.readiness_threshold` and `context.outcome_threshold`; route to `verify_issue` if both pass, else `failed`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add `check_scores_from_file` state; change `confidence_check.on_error`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/next_action.py` — reads session log to determine `NEEDS_VERIFY`; behavior fixed indirectly when `verify_issue` is reached

### Similar Patterns
- TBD — check other FSM loop YAMLs for `on_error: failed` patterns that bypass required states

### Tests
- TBD — identify or add tests for `refine-to-ready-issue.yaml` timeout handling

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Causes infinite re-processing loop starvation; confirmed blocking issue in sprint runs
- **Effort**: Small — Add one new YAML state (`check_scores_from_file`) and change one `on_error` transition
- **Risk**: Low — Change is isolated to the FSM loop YAML; does not affect other states or external systems
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop state machine design |
| guidelines | .claude/CLAUDE.md | Loop YAML conventions and `ll-issues` CLI |

## Labels

`bug`, `loops`, `issue-refinement`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P2

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` line 44: `on_error: failed` confirmed on `confidence_check` state ✓
- `scripts/little_loops/cli/issues/next_action.py:38`: `if "/ll:verify-issues" not in issue.session_commands` → returns `NEEDS_VERIFY` confirmed ✓
- No `check_scores_from_file` state exists in `refine-to-ready-issue.yaml` ✓
- Bug accurately describes the infinite re-processing cycle

## Session Log
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:format-issue` - 2026-04-03T04:47:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f43418ef-b4eb-43f5-b9ea-6b5a4a440f1c.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d10376d2-598f-4355-a0dc-b5100fe5afca.jsonl`
