---
id: ENH-2307
title: "rn-remediate decide state degenerate gate \u2014 on_yes == on_no == re_assess\
  \ discards verdict"
type: ENH
priority: P3
status: done
discovered_date: 2026-06-26
completed_at: 2026-06-26 21:32:45+00:00
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: decide
affects: scripts/little_loops/loops/rn-remediate.yaml
labels:
- loops
- rn-remediate
- degenerate-gate
- decide
relates_to:
- BUG-2169
- BUG-2222
confidence_score: 100
outcome_confidence: 88
score_complexity: 21
score_ambiguity: 23
score_change_surface: 22
decision_needed: false
score_test_coverage: 22
---

# ENH-2307: `decide` state degenerate gate — verdict unused

## Summary

The `decide` state in `rn-remediate.yaml` calls `/ll:decide-issue ${context.issue_id} --auto` but routes both `on_yes` and `on_no` identically to `re_assess`. The decision verdict is fully discarded. When `/ll:decide-issue --auto` cannot resolve a decision (no viable options, ambiguous scoring), the loop silently re-assesses instead of surfacing a failure, adding wasteful iterations before `check_convergence` eventually stalls and routes to `MANUAL_REVIEW`.

## Current Behavior

```yaml
decide:
  action: /ll:decide-issue ${context.issue_id} --auto
  action_type: slash_command
  evaluate: {}
  on_yes: re_assess   # decision made → re-assess
  on_no: re_assess    # no decision made → also re-assess (verdict discarded)
```

## Expected Behavior

When `/ll:decide-issue --auto` succeeds (a decision is recorded), the loop routes to `re_assess` to re-evaluate scores. When it fails (no viable options or ambiguous scoring), the loop routes to `emit_implement_failed` immediately rather than silently re-assessing. The `on_yes` and `on_no` routes are distinct so the decision verdict is not discarded:

```yaml
decide:
  on_yes: re_assess              # decision recorded → re-assess scores
  on_no: emit_implement_failed   # no decision possible → surface failure
  on_error: emit_implement_failed
```

## Motivation

The degenerate gate wastes loop iterations and obscures failures:
- When `decide-issue --auto` returns no viable option, the loop silently re-assesses instead of surfacing a failure, consuming extra steps
- `check_convergence` must stall before routing to `MANUAL_REVIEW`, adding latency and masking the root cause
- BUG-2169 (done) fixed the MR-4 partial-verdict crash on this state; BUG-2222 (done) fixed the skip-after-refinement gap — this verdict-discard gap was left unaddressed in both fixes

## Proposed Solution

Distinguish the success and failure cases:

```yaml
decide:
  action: /ll:decide-issue ${context.issue_id} --auto
  action_type: slash_command
  evaluate: {}
  on_yes: re_assess              # decision recorded → re-assess scores
  on_no: emit_implement_failed   # no decision possible → surface failure immediately
  on_error: emit_implement_failed
```

> **Selected:** `on_no: emit_implement_failed` — matches the `assess`/`re_assess` hard-fail pattern exactly; surfaces failure immediately rather than wasting refine cycles when decide has no viable options to choose from.

Alternatively, if a softer fallback is preferred (e.g., route to refine to break the tie rather than failing):

```yaml
  on_no: refine_first   # fallback: refine to resolve ambiguity, then re-assess
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: `on_no: emit_implement_failed` (hard fail)

**Reasoning**: The `assess` (line 81) and `re_assess` states already establish that LLM-evaluated states route `on_error: emit_implement_failed` — `decide` should match this pattern. When `/ll:decide-issue --auto` cannot resolve (no viable options or ambiguous scoring), routing to `refine_first` would be semantically mismatched: `refine_first` addresses content-quality gaps, not decision-ambiguity. Hard-failing immediately surfaces the root cause and ensures `emit_implement_failed` writes the outcome token so the parent's `classify_remediation` doesn't misroute on an empty file.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| `on_no: emit_implement_failed` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| `on_no: refine_first` | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- `on_no: emit_implement_failed`: Matches `assess`/`re_assess` pattern exactly; `emit_implement_failed` writes the outcome token preventing parent misroute; Expected Behavior section explicitly targets this route
- `on_no: refine_first`: Scoped for content/quality gaps in the codebase (see lines 399–403 comment); a failed decide is not a content gap — routing through refine adds wasted iterations before the inevitable `emit_implement_failed` via `refine_first`'s own `on_no`

## Implementation Steps

1. Open `scripts/little_loops/loops/rn-remediate.yaml` and locate the `decide` state at **lines 345–352**
2. Update routing on **line 350** (`on_no: re_assess` → `on_no: emit_implement_failed`) — or `on_no: refine_first` for the softer fallback; see Proposed Solution options
3. Add `on_error: emit_implement_failed` after `on_partial` (mirror the pattern in `assess` at **line 81** — same fragment, same `on_error` target)
4. Run `ll-loop validate rn-remediate` to confirm MR-4 compliance (no partial-route dead-ends)
5. Run `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_builtin_loops.py -v` to verify no routing assertions break

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_rn_remediate.py:318` — in `TestRemediationActions.test_decide_routes_to_re_assess`, change `dec["on_no"] == "re_assess"` to `"emit_implement_failed"` and add assertion for `dec["on_error"] == "emit_implement_failed"`
7. Update `scripts/tests/test_builtin_loops.py:7142` — in `TestRnRemediateAssessRouting.test_decide_on_no_routes_to_re_assess`, change assertion to `"emit_implement_failed"` and rename method to `test_decide_on_no_routes_to_emit_implement_failed`; add new sibling `test_decide_on_error_routes_to_emit_implement_failed` in the same class
8. Update `docs/guides/LOOPS_REFERENCE.md:554` — change the `decide → re_assess` single-arrow notation to reflect both routes: `on_yes → re_assess` and `on_no/on_error → emit_implement_failed`

## Impact

- **Priority**: P3 — reduces wasteful iterations and improves failure observability; less urgent than P2 correctness bugs
- **Effort**: Small — single YAML routing change, no Python code changes
- **Risk**: Low — isolated to `rn-remediate.yaml`; aligns with the existing `emit_implement_failed` terminal state already defined in the loop
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — update `decide` state: add `on_no` and `on_error` routes

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-implement.yaml` — parent orchestrator; invokes `rn-remediate` as a sub-loop at state `run_remediation` (`loop: rn-remediate`, line 524); its `classify_remediation` state (lines 535–541) reads the `subloop_outcome_<ID>.txt` token that `emit_implement_failed` must write — the fix ensures a failed `decide` produces the token rather than letting the sub-loop terminate without one [Agent 1 finding]

### Similar Patterns
- `run_remediation` and `run_decomposition` states in `rn-remediate.yaml` use `on_yes == on_no` intentionally (side-channel file routing) — that pattern is correct there; the `decide` state is different because there is no side-channel and verdict represents a genuinely distinct outcome

### Tests
- Run `ll-loop validate rn-remediate` after the change to confirm no MR-4 violations remain
- Manual test: exercise a scenario where `decide-issue --auto` cannot resolve (no viable options) and confirm the loop routes to `emit_implement_failed` rather than re-assessing

_Wiring pass added by `/ll:wire-issue`:_

**Tests to UPDATE (will break after the change):**
- `scripts/tests/test_rn_remediate.py:318` — `TestRemediationActions.test_decide_routes_to_re_assess` asserts `dec["on_no"] == "re_assess"` (line 327); must be updated to `"emit_implement_failed"` and `on_error: emit_implement_failed` assertion added [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:7142` — `TestRnRemediateAssessRouting.test_decide_on_no_routes_to_re_assess` asserts `state.get("on_no") == "re_assess"`; must be updated to `"emit_implement_failed"` and method renamed [Agent 3 finding]

**New tests to write (currently no coverage):**
- `scripts/tests/test_rn_remediate.py` — add `TestRemediationActions.test_decide_on_error_routes_to_emit_implement_failed`; follow the pattern of `test_implement_failure_routes_to_failed` at line 297 (asserts `on_no` and `on_error` together) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — add `TestRnRemediateAssessRouting.test_decide_on_error_routes_to_emit_implement_failed`; follow the fixture-based style of the surrounding methods in that class [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:554` — FSM flow diagram for `rn-remediate` documents `decide → re_assess` as a single-target arrow; after the fix there are two routes (`on_yes → re_assess`, `on_no/on_error → emit_implement_failed`); the notation will be factually stale and needs updating [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact location of decide state:**
- `scripts/little_loops/loops/rn-remediate.yaml` lines 345–352 — the full current `decide` state

**Terminal states confirmed present:**
- `emit_implement_failed` at lines 662–666 — writes `IMPLEMENT_FAILED` to `subloop_outcome_<id>.txt`, then `next: failed` ✓
- `refine_first` at lines 398–410 — uses `--auto` only (no `--full-rewrite`), on_yes: mark_refined, on_no: emit_implement_failed ✓
- `re_assess` at lines 460–471 — routes on_success/on_partial to verify_re_assess_scores, on_no to refine_followup ✓

**`on_error` is NOT provided by `with_rate_limit_handling` fragment:**
- `scripts/little_loops/loops/lib/common.yaml` — `with_rate_limit_handling` only sets `max_rate_limit_retries`, `rate_limit_backoff_base_seconds`, `rate_limit_max_wait_seconds`, `rate_limit_long_wait_ladder`. It does NOT supply `on_error`. The fix must add `on_error: emit_implement_failed` explicitly.
- **Severity of missing `on_error`**: When `evaluate_llm_structured()` returns `"error"`, `_route()` in `scripts/little_loops/fsm/executor.py` finds no match (`on_error` is `None`) and returns `None`. The main `run()` loop then calls `_finish("error", "No valid transition")` — the entire sub-loop terminates as an unhandled error with **no outcome token written** to `subloop_outcome_<ID>.txt`. The parent's `classify_remediation` then reads an empty/missing token and may misroute. This makes the missing `on_error` a harder failure than the on_no degenerate gate.

**Established pattern (the template to follow):**
- `assess` (lines 74–82): uses `fragment: with_rate_limit_handling` AND explicit `on_error: emit_implement_failed` — this is the exact pattern `decide` should match
- `re_assess` (lines 460–471): same shape — `on_error: emit_implement_failed` alongside the fragment

**`on_partial: re_assess` stays unchanged:**
- Current `on_partial: re_assess` is not addressed by the fix. Partial decision = some deliberation occurred → re-assess scores is reasonable. Leave it.

**Alternative `next:`-based decide routing exists in autodev.yaml:**
- `autodev.yaml run_decide` (lines 183–194) uses `next: mark_decide_ran` + `on_error: recheck_after_decide` instead of `on_yes`/`on_no`. This is a third structural approach but is not applicable here — `rn-remediate` needs to distinguish success from failure, which requires `on_yes` / `on_no`.

**Test files to run after the change:**
- `scripts/tests/test_rn_remediate.py` — routing tests for rn-remediate states
- `scripts/tests/test_builtin_loops.py` — loop-level compliance checks including MR-4
- `scripts/tests/test_fsm_validation.py` — FSM validator unit tests (MR-4 enforcement in `scripts/little_loops/fsm/validation.py`)

## Notes

- BUG-2169 (done) fixed the MR-4 partial verdict crash on this state; the degenerate `on_yes == on_no` routing was not addressed as part of that fix.
- BUG-2222 (done) fixed a separate gap where decide was skipped after refinement; the verdict-discard issue is distinct.
- The `on_yes == on_no` pattern is intentional in `run_remediation`/`run_decomposition` (side-channel file routing), but in `decide` there is no side-channel — the decision verdict represents genuine distinct outcomes.


## Resolution

- Fixed `decide` state in `rn-remediate.yaml`: `on_no` changed from `re_assess` to `emit_implement_failed`; `on_error: emit_implement_failed` added
- Updated `test_rn_remediate.py`: renamed `test_decide_routes_to_re_assess` → split into `test_decide_routes_to_re_assess_on_yes` + `test_decide_failure_routes_to_emit_implement_failed`
- Updated `test_builtin_loops.py`: renamed `test_decide_on_no_routes_to_re_assess` → `test_decide_on_no_routes_to_emit_implement_failed`; added `test_decide_on_error_routes_to_emit_implement_failed`
- Updated `docs/guides/LOOPS_REFERENCE.md` line 554: reflects both routes
- `ll-loop validate rn-remediate` passes; 1046 tests pass

## Session Log
- `/ll:ready-issue` - 2026-06-26T21:29:53 - `18c50c57-72c7-4a5c-86f2-814bb3179600.jsonl`
- `/ll:confidence-check` - 2026-06-26T20:10:00 - `3e2e5b14-7243-4e79-aea2-444e191dcd41.jsonl`
- `/ll:wire-issue` - 2026-06-26T19:54:14 - `7c383e45-909b-4fa2-882f-ad3719e1906b.jsonl`
- `/ll:decide-issue` - 2026-06-26T19:47:10 - `791a40e3-5254-431e-92c4-9f6e1d0bdc0a.jsonl`
- `/ll:refine-issue` - 2026-06-26T19:42:36 - `d2cfe14e-bfb2-45e8-9709-2ac170c906cc.jsonl`
- `/ll:format-issue` - 2026-06-26T19:37:27 - `d2cfe14e-bfb2-45e8-9709-2ac170c906cc.jsonl`
