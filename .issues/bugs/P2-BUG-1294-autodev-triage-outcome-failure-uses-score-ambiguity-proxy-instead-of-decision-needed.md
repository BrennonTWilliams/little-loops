---
id: "1294"
type: BUG
priority: P2
title: "autodev triage_outcome_failure uses score_ambiguity proxy instead of decision_needed flag"
status: done
captured_at: "2026-04-26T20:35:25Z"
completed_at: "2026-04-26T20:49:02Z"
discovered_date: "2026-04-26"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1294: autodev triage_outcome_failure uses score_ambiguity proxy instead of decision_needed flag

## Summary

In `scripts/little_loops/loops/autodev.yaml`, the `triage_outcome_failure` state routes to `run_decide` only when `score_ambiguity <= 10`, treating a low ambiguity score as a proxy for `decision_needed=true`. Issues with `decision_needed=true` but `score_ambiguity > 10` are not fast-pathed to `run_decide`; in the worst case (when `missing_artifacts=true` is also set), they are silently skipped from the pipeline without `/ll:decide-issue` ever being called.

## Current Behavior

In `scripts/little_loops/loops/autodev.yaml`, the `triage_outcome_failure` state uses `score_ambiguity <= 10` as the sole condition for routing to `run_decide`. The `decision_needed` field from the issue frontmatter is never read. When `score_ambiguity > 10` and `decision_needed: true`, the issue is routed to `check_missing_artifacts`. If `missing_artifacts: true` is also set, the subsequent `run_wire` → `recheck_after_size_review` path drops the issue via `on_no: dequeue_next` — without ever invoking `/ll:decide-issue`.

## Root Cause

**File**: `scripts/little_loops/loops/autodev.yaml`
**State**: `triage_outcome_failure` (line ~407–433)
**Function**: The Python snippet exits 0 (→ `run_decide`) when `score_ambiguity <= 10`, and exits 1 (→ `check_missing_artifacts`) otherwise.

The condition never reads the `decision_needed` field. Three distinct routing scenarios result:

| `score_ambiguity` | `decision_needed` | `missing_artifacts` | Outcome |
|---|---|---|---|
| ≤ 10 | any | any | Fast path → `run_decide` ✓ |
| > 10 | true | false | Long path (6 extra states) → `check_decision_before_size_review` → `run_decide` ✓ |
| > 10 | true | **true** | `check_missing_artifacts` → `run_wire` → `enqueue_or_skip` → `recheck_after_size_review` (on_no) → **`dequeue_next`** — issue silently dropped ✗ |

In Case 3, wiring doesn't resolve the decision ambiguity, so `recheck_after_size_review` sees scores still below threshold and routes `on_no: dequeue_next` — skipping the issue entirely and never calling `/ll:decide-issue`.

## Steps to Reproduce

1. Create an issue with `decision_needed: true`, `score_ambiguity` in the 15–30 range, and `missing_artifacts: true`.
2. Run `ll-loop run autodev "<issue-id>"`.
3. Observe: `triage_outcome_failure` routes to `check_missing_artifacts` → `run_wire` rather than `run_decide`. After wiring (which doesn't clear the decision question), `recheck_after_size_review` drops the issue.

## Expected Behavior

`triage_outcome_failure` should route to `run_decide` when `decision_needed=true` OR when `score_ambiguity <= 10`. The `decision_needed` flag is the authoritative signal; `score_ambiguity` is only a proxy.

## Motivation

Issues with unresolved design decisions (`decision_needed: true`) are a recurring category in this project. The silent drop in Case 3 means these issues disappear from the autodev queue with no log entry or user notification — requiring a manual audit to discover which issues were skipped. In the non-worst-case path, the 6-state detour wastes pipeline cycles and complicates flow debugging for a condition that has an explicit, authoritative flag.

## Proposed Solution

Change the exit condition in `triage_outcome_failure` to check both signals:

```python
d = json.loads(r.stdout)
ambiguity_low = int(d.get('score_ambiguity') or 25) <= 10
decision_needed = d.get('decision_needed') == 'true'
sys.exit(0 if (ambiguity_low or decision_needed) else 1)
```

This makes all three cases fast-path to `run_decide` when the `decision_needed` flag is set, regardless of `score_ambiguity` or `missing_artifacts`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — update `triage_outcome_failure` state exit condition (Python snippet)

### Dependent Files (Callers/Importers)
- N/A — `autodev.yaml` is a standalone FSM loop config; no Python imports of this state

### Similar Patterns
- Other score-based routing conditions in `autodev.yaml` — verify no similar `decision_needed` blind spots in `recheck_after_size_review` or `check_decision_before_size_review`

### Tests
- `scripts/tests/` — add test case covering `triage_outcome_failure` routing with `decision_needed: true` and `score_ambiguity: 20` (per Implementation Steps)

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Silent data loss for a specific but important issue category (`decision_needed: true` + `missing_artifacts: true`); not triggered on every run but high consequence when it occurs
- **Effort**: Small — Single-condition change in one YAML state; fix is one line of Python
- **Risk**: Low — Change is purely additive (OR logic); existing routing for `score_ambiguity <= 10` is unchanged
- **Breaking Change**: No

- **Data loss risk**: Issues with unresolved design decisions and missing artifacts are silently dropped from the autodev pipeline.
- **Incorrect routing**: Even in non-worst-case scenarios, `decision_needed=true` issues take 6 unnecessary extra states before reaching `run_decide`.

## Implementation Steps

1. Edit `triage_outcome_failure` action in `scripts/little_loops/loops/autodev.yaml` to include `decision_needed` in the exit condition (see Proposed Fix above).
2. Verify `check_missing_artifacts`'s comment is updated if it referenced this routing assumption.
3. Add a test case in `scripts/tests/` covering `triage_outcome_failure` routing with `decision_needed=true` and `score_ambiguity=20`.

## Labels

`bug`, `routing`, `autodev`, `triage`, `decision_needed`, `captured`

## Resolution

Fixed in `scripts/little_loops/loops/autodev.yaml` `triage_outcome_failure` state. The exit condition now checks both `decision_needed=true` (authoritative flag) and `score_ambiguity <= 10` (proxy), using OR logic. Issues with `decision_needed=true` are now always fast-pathed to `run_decide` regardless of `score_ambiguity` or `missing_artifacts`, eliminating the silent drop in Case 3.

## Status

**Completed** | Created: 2026-04-26 | Resolved: 2026-04-26 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-04-26T20:45:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8737d3b4-7f4b-441c-9a1b-ed0e7167d434.jsonl`
- `/ll:confidence-check` - 2026-04-26T20:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9415f2ec-a628-4e20-bce0-66c7cf4228f2.jsonl`
- `/ll:format-issue` - 2026-04-26T20:40:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/412ee35d-5b5b-4449-ba52-3eb93c29860a.jsonl`
- `/ll:manage-issue` - 2026-04-26T20:49:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8737d3b4-7f4b-441c-9a1b-ed0e7167d434.jsonl`
- `/ll:capture-issue` - 2026-04-26T20:35:25Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52be9e23-3914-464f-97ac-e73aca9d145b.jsonl`
