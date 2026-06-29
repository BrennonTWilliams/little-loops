---
id: ENH-2397
priority: P3
type: ENH
status: done
captured_at: '2026-06-29T17:37:00Z'
completed_at: '2026-06-29T17:37:00Z'
discovered_date: 2026-06-29
discovered_by: audit-loop-run
relates_to:
- BUG-2383
labels:
- testing
- loops
- regression-guard
confidence_score: 100
outcome_confidence: 95
---

# ENH-2397: Regression test for the sub-loop → parent outcome-channel sidecar contract

## Summary

Add a `pytest` regression guard (`TestSubloopSidecarContract` in
`scripts/tests/test_builtin_loops.py`) that pins the load-bearing assumption
behind the `rn-implement` → `rn-remediate`/`rn-decompose` outcome channel:
**every sub-loop state that transitions into a terminal (`done` or `failed`)
must first write its outcome token to `${run_dir}/subloop_outcome_<ID>.txt`.**

This was Recommendation #4 of the `rn-implement` loop audit
(`rn-implement-audit-2026-06-29.md`), which observed the sidecar contract has
held across two separate runs (2026-06-27 and 2026-06-29) but is enforced only
by convention — a new `next: failed` / `on_error: failed` path added without a
paired sidecar write would silently corrupt parent classification at runtime
with no error, no log, and no non-zero exit (the BUG-2383 silent-failure class).

## Current Behavior (before this change)

`rn-implement`'s `classify_remediation` / `classify_decomposition` states read
the child loop's real outcome from `${run_dir}/subloop_outcome_<ID>.txt` rather
than from the child's terminal verdict (which collapses every non-`done` exit
into a bare `failed`). The read uses a `cat … 2>/dev/null || echo "IMPLEMENT_FAILED"`
fallback. If a sub-loop ever reaches a terminal *without* writing the sidecar,
the parent silently classifies the outcome as `IMPLEMENT_FAILED` — losing the
true outcome (e.g. `MANUAL_REVIEW_NEEDED`, `NEEDS_DECOMPOSE`) with no diagnostic
signal. Nothing in the test suite guarded this invariant.

## What Was Done

Added `TestSubloopSidecarContract` to `scripts/tests/test_builtin_loops.py`:

- Iterates the two sub-loops the parent reads through the sidecar channel:
  `rn-remediate` and `rn-decompose`.
- Runs `resolve_fragments(...)` on each so the shared
  `subloop_rate_limit_diagnostic` fragment (defined in `loops/lib/common.yaml`,
  referenced by both loops' `rate_limit_diagnostic` state) is checked rather
  than skipped.
- For each state, computes its transition targets across `next`, all `on_*`
  routes, and the `route:` verdict table. Any state that can reach a terminal
  (`done`/`failed`) must contain `subloop_outcome_` in its action.
- Includes a vacuous-pass guard (matching the existing
  `test_all_failure_terminals_have_diagnostic_action` style) so a structural
  change that removes every terminal-routing state fails loudly instead of
  passing having checked nothing.

The guard is intentionally **stronger than the audit asked for**: the audit
called out only the `next: failed` paths, but inspection showed every path to
`done` also writes the sidecar (`emit_implemented`, `finalize_parent`,
`emit_no_children`), so the test pins both terminals — catching a broader class
of regression.

## Acceptance Criteria

- [x] `TestSubloopSidecarContract::test_terminal_routing_states_write_sidecar`
      passes against the current `rn-remediate` and `rn-decompose` loops.
- [x] Test fails with a clear, actionable message when a sidecar write is
      removed from a terminal-routing state (verified by temporarily stripping
      the write from `emit_needs_manual_review`).
- [x] Fragment-based terminal states (`rate_limit_diagnostic` via
      `subloop_rate_limit_diagnostic`) are covered, not skipped.
- [x] `ruff check` and `ruff format --check` clean on the test file.
- [x] Full `test_builtin_loops.py` suite green (944 passed).

## Files Changed

- `scripts/tests/test_builtin_loops.py` — added `resolve_fragments` import and
  the `TestSubloopSidecarContract` class.

## Notes

Session also reviewed the full `rn-implement-audit-2026-06-29.md` and decided
*against* the audit's other proposals as little-loops work: Proposals #1/#2 are
spec fixes for ENH-399 in a *different* project (`cards`) and already captured
by that issue's own `decision_needed: true` escalation; Proposal #3 (surface
block reasons in the issue file) rests on a partly-false premise (re_assess
already writes most reasoning into the issue) and would require a brittle new
cross-loop artifact contract — deferred, capture separately if desired. This
issue implements only the high-value, repo-local Recommendation #4.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-29T17:37:51 - `e7d74289-f32b-48e5-b1fc-0dc56410799b.jsonl`
