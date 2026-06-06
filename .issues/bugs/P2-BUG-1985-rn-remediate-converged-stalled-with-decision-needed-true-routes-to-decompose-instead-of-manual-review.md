---
id: BUG-1985
title: 'rn-remediate: CONVERGED_STALLED with decision_needed still true routes to
  NEEDS_DECOMPOSE instead of NEEDS_MANUAL_REVIEW'
type: BUG
priority: P2
status: open
captured_at: '2026-06-06T00:00:00Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
decision_needed: false
confidence_score: 96
outcome_confidence: 84
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 22
relates_to:
- BUG-1416
- BUG-1378
labels:
- rn-implement
- rn-remediate
- loop-defect
- routing
---

# BUG-1985: rn-remediate CONVERGED_STALLED + decision_needed still true routes to decompose

## Summary

When `rn-remediate`'s `decide` state runs `/ll:decide-issue --auto` and resolves a question, `re_assess` (a second confidence-check) can re-detect a *different* unresolved open question and re-set `decision_needed: true`. If pre/post scores are unchanged (delta=0), `check_convergence` emits `CONVERGED_STALLED`, which unconditionally routes to `emit_needs_decompose → NEEDS_DECOMPOSE`. The parent loop then sends the issue to `rn-decompose → run_size_review`, decomposing an issue whose only real blocker was an automated-unresolvable design question — not size.

Observed in run `2026-06-06T220136` on FEAT-1809:
- `decide` resolved the fork-vs-flag question (already marked `✅ RESOLVED`)
- `re_assess` re-set `decision_needed: true` for Q2 (combined `max_iterations × max_replans` cap, no formal option blocks)
- Convergence delta = 0 → `CONVERGED_STALLED`
- FEAT-1809 was decomposed into FEAT-1983 + FEAT-1984 — unnecessary, since the issue was implementation-ready (readiness=90) with a single unresolvable numeric design question

## Motivation

The `rn-implement` loop silently decomposes implementation-ready issues when the only blocker is a design question that automation cannot resolve. This wastes engineering effort (the decomposed child issues must be re-scoped, re-wired, and run through separate implementation cycles), creates unnecessary noise in the issue tracker, and discards the context of why the decision was unresolvable. FEAT-1809 was split into FEAT-1983 + FEAT-1984 due to this bug despite being at readiness=90. Any `rn-implement` run where `decision_needed: true` persists after a `decide` pass is vulnerable to this misclassification.

## Current Behavior

In `check_convergence` action (loops/rn-remediate.yaml):

```bash
elif [ "$TOTAL_DELTA" -le 2 ]; then
  echo "CONVERGED_STALLED"
```

No check on `decision_needed` in post-scores. A stall caused by an irresolvable decision looks identical to a stall caused by an issue that genuinely can't improve — both route to decomposition.

## Expected Behavior

When `check_convergence` detects `CONVERGED_STALLED` AND the post-scores JSON still has `decision_needed: true`, the issue is blocked by a human-required decision, not by size. The correct token is `NEEDS_MANUAL_REVIEW`, not `CONVERGED_STALLED`. The parent loop should route this to a `mark_blocked` or `escalate` state, not `rn-decompose`.

## Steps to Reproduce

1. Run `ll-loop run rn-implement FEAT-ID` on an issue where:
   - `decision_needed: true` with an open question that has no formal `### Option` blocks
   - readiness ≥ 85, outcome < 75
2. Observe: `check_decision_needed → decide → re_assess` cycle runs
3. `decide-issue` resolves only stale/already-answered questions; re_assess re-sets `decision_needed: true`
4. `check_convergence` emits `CONVERGED_STALLED` (delta=0)
5. Issue is decomposed rather than flagged for human review

## Root Cause

`check_convergence` in `loops/rn-remediate.yaml` reads pre/post score deltas from JSON files but does not read `decision_needed` from the post-scores snapshot. The stall branch emits `CONVERGED_STALLED` unconditionally, so a "stalled because a human-required decision is unresolvable by automation" case is indistinguishable from a genuine "scores cannot be improved, issue is too large" case.

## Proposed Solution

In `check_convergence`'s shell action, after computing `TOTAL_DELTA`, check `decision_needed` from the post-scores JSON:

```bash
elif [ "$TOTAL_DELTA" -le 2 ]; then
  # Distinguish: stalled because unresolvable decision vs genuinely too large
  POST_DECISION=$(jq -r '.decision_needed // "false"' "$POST" 2>/dev/null)
  if [ "$POST_DECISION" = "true" ]; then
    echo "NEEDS_MANUAL_REVIEW"
  else
    echo "CONVERGED_STALLED"
  fi
```

Add `route_conv_manual_review` state after `route_conv_improved`:

```yaml
route_conv_manual_review:
  evaluate:
    type: output_contains
    pattern: "NEEDS_MANUAL_REVIEW"
    source: "${captured.convergence_result.output}"   # capture key is convergence_result, not convergence
  on_yes: emit_needs_manual_review
  on_no: emit_needs_decompose
  on_error: emit_needs_decompose

emit_needs_manual_review:
  action: |
    echo "MANUAL_REVIEW_NEEDED" > "${context.run_dir}/subloop_outcome_${context.issue_id}.txt"
  action_type: shell
  next: failed
```

The parent (`rn-implement`) `classify_remediation` routing chain then needs a `route_rem_manual_review` state before falling through to `route_rem_decompose`.

## Implementation Steps

1. Edit `check_convergence` action in `scripts/little_loops/loops/rn-remediate.yaml` (stall branch at line 364-365): add `POST_DECISION=$(jq -r '.decision_needed // "false"' "$POST" 2>/dev/null)` check; emit `NEEDS_MANUAL_REVIEW` when true, `CONVERGED_STALLED` otherwise.
2. Change `route_conv_improved` `on_no` (line 388) from `emit_needs_decompose` to `route_conv_manual_review`.
3. Add `route_conv_manual_review` and `emit_needs_manual_review` states to `rn-remediate.yaml` using `${captured.convergence_result.output}` as source (not `convergence.output` — capture key is `convergence_result`). Update the token comment block (lines 408-415) to include `NEEDS_MANUAL_REVIEW`.
4. Change `route_rem_decompose` `on_no` (line 195 in `rn-implement.yaml`) from `route_rem_rate_limited` to `route_rem_manual_review`. Add `route_rem_manual_review` (matches `MANUAL_REVIEW_NEEDED`) and `mark_blocked` (writes to `skipped.txt`, `next: dequeue_next`) states to `rn-implement.yaml`.
5. Update three breaking tests:
   - `test_rn_remediate.py:TestReassessAndConvergence.test_convergence_router_chain_is_correct` (line 437): change `rci["on_no"] == "emit_needs_decompose"` → `"route_conv_manual_review"`
   - `test_rn_remediate.py:TestOutcomeTokenChannel.test_needs_decompose_only_on_stall_paths` (line 763): same assertion, same change
   - `test_rn_implement.py:TestParentClassifier.test_classifier_states_exist` (lines 556-566): add `route_rem_manual_review` and `mark_blocked` to the state name list
   - Add new token test: `emit_needs_manual_review` → `MANUAL_REVIEW_NEEDED` in `subloop_outcome_` (model after `test_emit_tokens_written_to_run_dir` dict, line 737-749)
6. Run `ll-loop validate scripts/little_loops/loops/rn-remediate.yaml scripts/little_loops/loops/rn-implement.yaml` and confirm no new MR-* errors. New states use `output_contains` evaluator (non-LLM), so MR-4 does not fire; both loops already declare `partial_route_ok: true` which also suppresses MR-4 loop-wide.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_rn_remediate.py:TestOutcomeTokenChannel.test_emit_states_exist` (line 727) — add `"emit_needs_manual_review"` to the state-name tuple alongside `"emit_needs_decompose"` etc.
8. Update `scripts/tests/test_rn_remediate.py:TestOutcomeTokenChannel.test_emit_tokens_written_to_run_dir` (line 737) — add `"emit_needs_manual_review": "MANUAL_REVIEW_NEEDED"` entry to the `expected` dict (do not create a separate new test function; update this existing one)
9. Update `docs/guides/LOOPS_GUIDE.md` line 733 — revise convergence rule description to distinguish `decision_needed=true` stall (→ `NEEDS_MANUAL_REVIEW`) from genuine stall (→ `CONVERGED_STALLED`)
10. Update `docs/guides/LOOPS_GUIDE.md` line 756 — add `route_conv_manual_review` to the FSM flow diagram for the stall path
11. Update `test_rn_remediate.py:test_convergence_routers_use_output_contains_with_source` (line 439) — add `"route_conv_manual_review"` to the state-name loop
12. Add new tests in `test_rn_remediate.py`: `check_convergence` action contains `POST_DECISION` and `NEEDS_MANUAL_REVIEW` check
13. Add new tests in `test_rn_implement.py`: `route_rem_manual_review.on_yes == "mark_blocked"`; `mark_blocked` writes to a file and `next: dequeue_next`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_convergence` shell action: add `NEEDS_MANUAL_REVIEW` branch; new `route_conv_manual_review` and `emit_needs_manual_review` states
- `scripts/little_loops/loops/rn-implement.yaml` — `classify_remediation` routing chain: add `route_rem_manual_review` state before `route_rem_decompose`; add `mark_blocked` state writing `MANUAL_REVIEW_NEEDED` to skipped file

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — invokes `rn-remediate` as a subloop; reads `subloop_outcome_*.txt` from `context.run_dir`
- `scripts/little_loops/loop_runner.py` — orchestrates subloop invocation via `ll-loop run`

### Similar Patterns
- Existing `route_conv_improved` / `route_conv_stalled` states in `rn-remediate.yaml` — new `route_conv_manual_review` follows the same `output_contains` evaluator pattern
- Existing `classify_remediation` chain in `rn-implement.yaml` — new `route_rem_manual_review` extends the chain consistently before `route_rem_decompose`

### Tests
- `ll-loop validate scripts/little_loops/loops/rn-remediate.yaml scripts/little_loops/loops/rn-implement.yaml` — MR-4 partial route compliance
- New unit test: convergence stall with `decision_needed: true` in post-scores JSON emits `NEEDS_MANUAL_REVIEW` (not `CONVERGED_STALLED`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py:TestOutcomeTokenChannel.test_emit_states_exist` (line 727) — existing test; add `"emit_needs_manual_review"` to the state-name tuple [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py:TestOutcomeTokenChannel.test_emit_tokens_written_to_run_dir` (line 737) — existing test; add `"emit_needs_manual_review": "MANUAL_REVIEW_NEEDED"` to the `expected` dict (this is the existing pattern test, not a new function; the issue's "new token test" note was ambiguous) [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py:TestReassessAndConvergence.test_convergence_routers_use_output_contains_with_source` (line 439) — existing test; add `"route_conv_manual_review"` to the `for state_name in (...)` loop alongside `"route_conv_pass"` and `"route_conv_improved"` [Agent 3 finding]
- New tests needed in `test_rn_remediate.py`: (a) `check_convergence` action contains `NEEDS_MANUAL_REVIEW` branch (asserts `POST_DECISION` and `NEEDS_MANUAL_REVIEW` in action); (b) `route_rem_manual_review.on_yes == "mark_blocked"` in `test_rn_implement.py` (model after `test_rate_limited_routes_to_diagnostic`); (c) `mark_blocked` writes a file and routes `next: dequeue_next` (model after `test_record_failure_appends_and_dequeues`) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` line 733 — explicitly documents `total_delta ≤ 2 → CONVERGED_STALLED → failed` as the convergence rule; must be updated to reflect the `decision_needed` branch: `total_delta ≤ 2 + decision_needed=true → NEEDS_MANUAL_REVIEW → failed; total_delta ≤ 2 + decision_needed=false → CONVERGED_STALLED → failed` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` line 756 — FSM flow diagram `check_convergence → route_conv_pass → route_conv_improved → check_remediation_budget` must show `route_conv_manual_review` in the stall path [Agent 2 finding]

### Configuration
- N/A — no config file changes needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct codebase analysis:_

**Exact change points in `rn-remediate.yaml`:**
- `check_convergence` stall branch at line 364-365 — change `echo "CONVERGED_STALLED"` to the `POST_DECISION` check block
- `route_conv_improved` at line 382-389: `on_no: emit_needs_decompose` (line 388) must change to `on_no: route_conv_manual_review` so the new routing state is inserted before the decompose emitter
- Token comment block at lines 408-415 lists outcome tokens — add `NEEDS_MANUAL_REVIEW` to the list (`IMPLEMENTED | NEEDS_DECOMPOSE | NEEDS_MANUAL_REVIEW | IMPLEMENT_FAILED | SCORES_MISSING | RATE_LIMITED`)
- The `convergence_${ID}.json` log (lines 355-360) does not include `decision_needed` — consider adding it for observability (`"post_decision_needed":"%s"` using `POST_DECISION`) so future audit runs can correlate stall causes

**Exact change points in `rn-implement.yaml`:**
- `route_rem_decompose` at line 189-196: `on_no: route_rem_rate_limited` (line 195) must change to `on_no: route_rem_manual_review`
- New `route_rem_manual_review` state goes between `route_rem_decompose` and `route_rem_rate_limited`
- New `mark_blocked` state goes after `route_rem_manual_review` — modeled on `skip_issue` (line 267-273)
- `init` state (line 42-97) initializes `skipped.txt` but not `blocked.txt`; `report` state (line 287-317) counts skipped but not blocked — if `mark_blocked` writes to a separate `blocked.txt`, both `init` (add `: > "$RUN_DIR/blocked.txt"`) and `report` (add `BLOCKED=$(wc -l ...)` counter and output line) need updating

**`decision_needed` JSON serialization:**
- `scripts/little_loops/cli/issues/show.py:274` outputs `decision_needed` as a lowercase string (`"true"` or `"false"`) via `str(decision_needed_raw).lower()`
- The proposed `jq -r '.decision_needed // "false"' "$POST"` returns the string `"true"` or `"false"`, which matches the `[ "$POST_DECISION" = "true" ]` comparison — the approach is correct
- No existing `mark_blocked` state exists in any `rn-*` loop — this is a new pattern to introduce

## Impact

- **Priority**: P2 — causes implementation-ready issues blocked by an unresolvable automated decision to be incorrectly decomposed, splitting work that doesn't need splitting
- **Effort**: Medium — 3 YAML files, 1 new state per loop, new routing chain entry
- **Risk**: Low — additive path; existing `CONVERGED_STALLED` path is unchanged when `decision_needed` is false
- **Breaking Change**: No
- **Blast radius**: Any `rn-implement` run where the issue has an open question with no formal option blocks and scores stall after a `decide` pass

## Session Log
- `/ll:wire-issue` - 2026-06-06T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-06-06T22:39:32 - `0ca21a34-10fe-4584-bba4-cf168e9b3350.jsonl`
- `/ll:format-issue` - 2026-06-06T22:29:15 - `e0f0d6fe-d848-4276-84db-9f4b881a2d8b.jsonl`
- `/ll:audit-loop-run` - 2026-06-06 - from run 2026-06-06T220136 (FEAT-1809)
