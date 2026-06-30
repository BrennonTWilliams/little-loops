---
id: BUG-2400
title: refine-to-ready-issue confidence_check references the verify-confidence-scores
  oracle without its oracles/ prefix, silently failing every refine
status: done
priority: P1
captured_at: '2026-06-30T16:06:47Z'
discovered_date: '2026-06-30'
discovered_by: audit
relates_to:
- BUG-2305
confidence_score: 100
outcome_confidence: 95
score_complexity: 12
score_test_coverage: 22
score_ambiguity: 10
score_change_surface: 14
completed_at: '2026-06-30T16:06:47Z'
labels:
- bug
- fsm
- loops
- validation
---

# BUG-2400: `refine-to-ready-issue.confidence_check` missing `oracles/` prefix

## Summary

`refine-to-ready-issue.yaml`'s `confidence_check` state referenced the oracle
sub-loop by the bare name `verify-confidence-scores`, but that loop lives at
`loops/oracles/verify-confidence-scores.yaml`. `resolve_loop_path` does not
recurse into `oracles/` — the established convention is to reference oracle
sub-loops *with* the prefix (e.g. `oracles/generator-evaluator`,
`oracles/enumerate-and-prove`). `confidence_check` was the only oracle reference
in the entire built-in loop set missing its prefix.

At runtime the executor's `resolve_loop_path` raised `FileNotFoundError`, which
the state's `on_error: diagnose` swallowed, routing every issue to the `failed`
terminal. The parent `autodev` loop treated this as "child did not reach done"
and skipped the issue. The net effect: every issue passed through refine + wire
(real, expensive work) and then dead-ended at the confidence gate, so the loop
implemented **nothing**.

Surfaced by two independent audits of `sprint-refine-and-implement` runs in
other projects on this machine (`2026-06-30T022939` audio-cue scope and
`2026-06-30T024644` EPIC-364 scope) — both 2–3 hour runs producing
`verdict: no-op` with zero closures despite ~950 lines of refinement work each.
The two audits disagreed on root cause; ground-truthing against the source
confirmed the unresolved-reference mechanism (one audit's `decision_needed`
theory was a hallucinated diagnosis from the `diagnose` prompt — a reference
that never resolves cannot return a verdict).

## Root Cause

**File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml:126`

Introduced in commit `fd6a1c78` (2026-06-13) when the confidence-check region
was extracted into `oracles/verify-confidence-scores.yaml` but referenced
without the `oracles/` prefix.

The defect persisted because two tests *ratcheted the broken value in*:

1. `test_builtin_loops.py:978` asserted `confidence_check.loop ==
   "verify-confidence-scores"` (the broken value).
2. BUG-2305's warning-ratchet ALLOWLIST (`test_builtin_loops.py:7718-7722`)
   suppressed the validator's "does not resolve" WARNING for this exact path,
   with a comment claiming it *"resolves correctly at runtime via the executor's
   loops_dir"* — which is false. `resolve_loop_path('verify-confidence-scores',
   builtin_dir)` raises `FileNotFoundError`, and the executor uses the same
   function.

The validator (added in BUG-2305) *did* detect the broken reference, but it was
WARNING-severity and got allowlisted away on a mistaken assumption.

## Fix

### P0 — the actual bug (one line + two test corrections)

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:126` —
  `loop: verify-confidence-scores` → `loop: oracles/verify-confidence-scores`.
- `scripts/tests/test_builtin_loops.py:978` — golden test now asserts the
  prefixed value.
- `scripts/tests/test_builtin_loops.py` — removed the stale
  `(refine-to-ready-issue, loop-reference)` ratchet allowlist entry. The
  existing `test_allowlist_entries_are_not_stale` guard forces removal once the
  warning is gone.

### P1 — prevent the class (the systemic fix)

- `scripts/little_loops/fsm/validation.py` `_validate_loop_references` —
  unresolvable *static* (non-`${...}`) `loop:` references promoted from WARNING
  to **ERROR**. A reachable static reference that fails resolution at definition
  time fails identically at runtime, so it now fails the load:
  `ll-loop validate` exits non-zero and CI fails, instead of deferring to an
  opaque runtime `on_error` route. `cmd_validate` already degrades gracefully on
  the now-raising `load_and_validate` (non-zero exit + clear message in both
  JSON and non-JSON modes).
- `scripts/tests/test_builtin_loops.py` — added
  `TestBuiltinLoopReferencesResolve`, an explicit CI gate asserting every static
  `loop:` reference in every built-in loop resolves.
- `scripts/tests/test_fsm_validation.py` /
  `scripts/tests/test_ll_loop_commands.py` — updated the two BUG-2305 tests that
  asserted WARNING semantics to assert ERROR.

This corrects BUG-2305's deliberate-but-mistaken WARNING choice: its stated
rationale ("intentionally-optional references") does not hold, because dynamic
`${...}` names are already skipped and a static name either resolves or fails
identically at runtime.

## Files Changed

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (production fix)
- `scripts/little_loops/fsm/validation.py` (WARNING → ERROR)
- `scripts/tests/test_builtin_loops.py` (golden assertion, allowlist removal,
  new integrity test)
- `scripts/tests/test_fsm_validation.py` (WARNING → ERROR test)
- `scripts/tests/test_ll_loop_commands.py` (WARNING → ERROR test)

## Verification

- Targeted classes (`TestRefineToReadyIssueSubLoop`, `TestValidatorWarningBudget`,
  `TestBuiltinLoopReferencesResolve`, `TestLoopReferenceValidation`,
  `TestCmdValidate`): 61 passed.
- Broader suite (`test_builtin_loops`, `test_fsm_validation`,
  `test_ll_loop_commands`, `test_audit_loop_run_skill`, `test_fsm_executor`):
  1733 passed.
- `ruff check` clean, `ruff format` clean, `mypy scripts/little_loops/fsm/validation.py` clean.
- Confirmed empirically: `refine-to-ready-issue` now loads with 0 warnings and
  `confidence_check.loop` resolves to
  `loops/oracles/verify-confidence-scores.yaml`.

## Impact

- **Priority**: P1 — a built-in loop's core gate never opened; two multi-hour
  sprint runs produced zero implementations.
- **Effort**: Small — one-line production fix plus a severity promotion and test
  updates.
- **Risk**: Low — the ERROR promotion only fires on genuinely unresolvable
  static references, which already fail at runtime; blast radius was two
  contained test updates.
- **Breaking change**: Loops with a pre-existing unresolvable static `loop:`
  reference now fail to load instead of warning. This is intended (fail fast,
  fail loud) and matches runtime behavior.

## Follow-ups (deferred, out of scope for this fix)

- **Verdict honesty (P2)**: `auto-refine-and-implement.finalize` reports `no-op`
  when only skips occurred (closed 0, skip > 0). Attempting and skipping every
  issue is not a no-op. Skip *tracking* already exists (`autodev.skip_inflight`
  → `autodev-skipped.txt`); only the verdict mapping needs a branch.
- **`depends_on` validator**: a secondary audit finding — `depends_on` warnings
  fire for issues that exist under a `P3-` prefix (bare-ID vs prefixed-ID match).
  Independent minor item to confirm.
- With P0 in place, the parent's existing `check_decision_needed` routing
  (`refine-to-ready-issue.yaml:197`) is finally reachable, so the second audit's
  `decision_needed` concern is likely now moot — confirmable with one real run.

## References

- Audits: `audit-sprint-refine-and-implement-2026-06-30.md`,
  `.loops/audits/2026-06-30T024644-sprint-refine-and-implement-audit.md`
- Regressing commit: `fd6a1c78` (oracle extraction)
- Related: BUG-2305 (definition-time `loop:` reference validation)
</content>
</invoke>


## Session Log
- `hook:posttooluse-status-done` - 2026-06-30T16:07:56 - `4abc6ccf-b534-41d9-b436-ca3362b14d56.jsonl`
