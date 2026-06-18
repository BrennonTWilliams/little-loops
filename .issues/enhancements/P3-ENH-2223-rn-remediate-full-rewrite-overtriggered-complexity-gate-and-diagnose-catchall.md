---
id: ENH-2223
title: "rn-remediate over-triggers --full-rewrite via complexity gate and diagnose catch-all"
type: ENH
status: done
priority: P3
confidence_score: 72
outcome_confidence: 78
score_complexity: 12
score_ambiguity: 8
score_change_surface: 10
captured_at: "2026-06-18T20:37:28Z"
discovered_date: "2026-06-18"
discovered_by: capture-issue
labels:
  - loops
  - rn-remediate
  - refinement
---

# ENH-2223: rn-remediate over-triggers --full-rewrite via complexity gate and diagnose catch-all

## Summary

`rn-remediate` uses `--full-rewrite` unconditionally in its `refine` state, but two routing paths trigger that state in cases where a full rewrite is likely unnecessary or destructive:

1. **`check_complexity_pre_implement` (line ~140)**: An issue that *already passes* the readiness gate (confidence ≥ 85 AND outcome ≥ 75) still gets routed to `--full-rewrite` if its complexity score is ≥ 15 (`require_refine_and_wire: true` default). This treats "complex" as a proxy for "needs rewriting" rather than checking actual content deficiency — and risks overwriting well-specified implementation plans.

2. **`diagnose` catch-all `else: REFINE` (line ~268)**: Any issue that doesn't match IMPLEMENT / DECIDE / WIRE / DECOMPOSE silently triggers `--full-rewrite`. Minor score gaps that don't fit the priority routing rules get the most destructive remediation action with no narrower fallback.

## Current Behavior

`rn-remediate` triggers `--full-rewrite` via `/ll:refine-issue` in two unintended paths:

1. **`check_complexity_pre_implement`**: Issues with complexity score ≥ 15 route to `refine` with `--full-rewrite` even when they already pass the readiness gate (confidence ≥ 85, outcome ≥ 75). Complexity is treated as a proxy for content deficiency.
2. **`diagnose` catch-all**: Issues that do not match IMPLEMENT / DECIDE / WIRE / DECOMPOSE fall through to `else: REFINE` with `--full-rewrite`, silently applying the most destructive remediation for minor or unclassified score gaps.

## Expected Behavior

- A high-complexity issue (complexity ≥ 15) that already passes the readiness gate routes to `wire` (if `change_surface > 0`) or directly to `gate_implement`, not through `--full-rewrite`.
- The `diagnose` catch-all applies a lighter action (e.g., `/ll:refine-issue --auto` without `--full-rewrite`) for residual unmatched conditions.
- `--full-rewrite` is reserved for paths where content is known deficient: `assess → on_no` and `wire → on_error`.

## Motivation

The `--full-rewrite` flag on `/ll:refine-issue` is the heaviest remediation action available — it replaces the entire issue body rather than augmenting it. Using it when an issue is already well-specified wastes tokens and risks destroying content the author intended to preserve. The two paths above are the most common sources of unintentional rewrites observed in practice.

## Implementation Steps

1. **Fix `check_complexity_pre_implement`**: Change the routing so that an issue passing the readiness gate (`check_readiness → on_yes`) with high complexity routes to `wire` (if change_surface is 0) or directly to `gate_implement` rather than unconditionally to `refine`. Alternatively, use a lighter `--auto` pass (no `--full-rewrite`) for complexity-only deficiencies on already-ready issues.

2. **Fix `diagnose` catch-all**: Replace the bare `else: REFINE` with a narrower action — e.g., a targeted `/ll:refine-issue --auto` (no `--full-rewrite`) for residual low-confidence cases that don't warrant full content replacement. Reserve `--full-rewrite` for the `assess → on_no` (outright failure) and `wire → on_error` (wiring failed) paths where the content is known deficient.

3. **Tests / verification**: Confirm via `ll-loop run rn-remediate` on a high-complexity, readiness-passing issue that the complexity gate no longer routes through `refine` with `--full-rewrite`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_complexity_pre_implement` state (line 133): `on_yes` redirected from `refine` to `check_wire_pre_implement`; `diagnose` state (line 258): catch-all `else` outputs `REFINE_LIGHT` and new route entry added; new `refine_light` state added after `refine`
- `scripts/tests/test_rn_remediate.py` — stale `re_assess` marker assertions updated (BUG-2155 fix); new tests for `check_complexity_pre_implement` routing, `refine_light` state, and `REFINE_LIGHT` diagnose token

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — parent loop that delegates to `rn-remediate` via `loop:` sub-loop invocation
- `scripts/little_loops/loops/rn-refine.yaml` — standalone sibling loop (not affected)

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml:63` — only other loop that calls `/ll:refine-issue --auto` without `--full-rewrite`; models the `refine_light` state shape
- `scripts/little_loops/loops/autodev.yaml:151` — `check_passed` state demonstrates "already-ready → skip expensive action" short-circuit pattern used by `check_complexity_pre_implement` fix

### Tests
- `scripts/tests/test_rn_remediate.py` — primary test suite; run with `python -m pytest scripts/tests/test_rn_remediate.py`
- `ll-loop validate rn-remediate` — structural validation

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [ ] A high-complexity issue (complexity ≥ 15) that passes `check_readiness` (confidence ≥ 85, outcome ≥ 75) does NOT trigger `--full-rewrite` in `rn-remediate`.
- [ ] The `diagnose` catch-all no longer uses `--full-rewrite`; unmatched conditions use a lighter refinement action.
- [ ] All existing rn-remediate routing tests still pass (`ll-loop validate rn-remediate`).

## Scope Boundaries

- Changes confined to `scripts/little_loops/loops/rn-remediate.yaml`.
- Does not affect `refine-to-ready-issue.yaml`, `autodev.yaml`, or other loops that also use `--full-rewrite`.

## Impact

- **Priority**: P3 — Reduces unintentional content destruction in `rn-remediate`; correctness issue but non-blocking
- **Effort**: Small — Single YAML file change, confined to routing in two states
- **Risk**: Low — No API changes; `ll-loop validate rn-remediate` serves as regression guard
- **Breaking Change**: No

## Status

**Done** | Created: 2026-06-18 | Completed: 2026-06-18 | Priority: P3

---

## Session Log
- `/ll:refine-issue` - 2026-06-18T20:53:37 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:format-issue` - 2026-06-18T20:46:24 - `eb8abe2d-ca34-4c1a-9837-71d4833fee99.jsonl`
- `/ll:capture-issue` - 2026-06-18T20:37:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef0b05a4-a7e0-47d6-afa2-5f2b99558da6.jsonl`
