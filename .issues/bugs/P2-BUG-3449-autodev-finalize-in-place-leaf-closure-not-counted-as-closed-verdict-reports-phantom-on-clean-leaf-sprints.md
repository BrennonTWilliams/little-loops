---
id: BUG-3449
type: BUG
title: 'Autodev finalize: in-place leaf closure not counted as closed; verdict reports
  phantom on clean leaf sprints'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-12'
captured_at: '2026-09-12T00:15:37Z'
labels:
- issues
- gates
- autodev
---

# BUG-3449: Autodev finalize: in-place leaf closure not counted as closed; verdict reports phantom on clean leaf sprints

## Summary

`TestAutoRefineAndImplementLoop::test_finalize_counts_done_in_place_leaf_as_closed` (test_builtin_loops.py:4932) has been failing on `main` since at least 2026-09-06. The test asserts that a leaf issue which reaches `status: done` IN PLACE (no move to `completed/`, per ENH-1418) must count as CLOSED and yield a non-phantom verdict. The actual outcome is `verdict: 'phantom'`, `closed: 0`, `not_closed: 1`.

This blocks `main` CI from ever going green and is unrelated to the BUG-3439 / evidence-gate fixes in PR #24.

## Context

Reproduced on `6351ac658` (v1.163.0 changelog commit) and verified to fail identically on pristine HEAD via `git stash`:

```
$ pytest scripts/tests/test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_finalize_counts_done_in_place_leaf_as_closed
AssertionError: in-place leaf closure must count, got
  {'verdict': 'phantom', 'closed': 0, 'not_closed': 1, 'skipped': 0,
   'errored': 0, 'skipped_breakdown': {}, 'closed_via_recovery': 0,
   'gate_blocked': 0, 'decision_unresolved': 0, 'inflight_unresolved': 0,
   'abandoned': 0, 'parked_rate': 0.0, 'verify_verdict': 'not_run',
   'verify_returncode': None, 'epic_merge_verdict': 'not_run',
   'epic_branch_stale_action': 'none'}
assert 0 == 1
```

Per `gh run list --limit 20 --repo BrennonTWilliams/little-loops`, every CI run on `main` since `34047955201` (2026-09-06T17:14:02Z, `docs(release): add changelog for v1.161.0`) has failed. Likely candidates: BUG-3439 oversized-spawn tests (now fixed by PR #24), the evidence gate (now fixed by PR #24), and this `done_in_place` finalize test.

The test docstring traces this back to BUG-2403 (a leaf that reaches `status: done` IN PLACE must count as CLOSED). The fix expected to live somewhere in the `finalize` machinery that the test exercises via `_run_finalize`.

## Current Behavior

`TestAutoRefineAndImplementLoop._run_finalize(data, run_dir, passed=("FEAT-1",), done_in_place=("FEAT-1",))` returns:

- `closed: 0`
- `not_closed: 1`
- `verdict: 'phantom'`

But the test (and BUG-2403's contract) expect:

- `closed: 1`
- `not_closed: 0`
- `verdict` in `("success", "partial")`

## Expected Behavior

The `done_in_place` leaf set must be merged into the closure count when the leaf passed verification. The phantom verdict must not fire on a clean in-place leaf closure.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P2 — blocks `main` CI from being green, but no user-facing impact (test-only failure).
- **Effort**: Small to medium — likely a 10-30 line change in the finalize closure-count logic, plus regression tests.
- **Risk**: Low — affects a finalize-time accounting path, not core loop routing or capture logic.

## Likely Root Cause

`_run_finalize` (test_builtin_loops.py:4254+ around the `finalize` autodev state) probably computes `closed` from a `completed/`-directory diff alone, never consulting `done_in_place` for leaves that didn't move. The companion test `test_finalize_excludes_pre_existing_done_baseline_from_closed` (test_builtin_loops.py:4952) exercises the negative case (an issue that was already done before the run must not be double-counted), so the fix needs to:

1. Treat `done_in_place` as newly closed for any leaf in `passed` cap `done_in_place`.
2. Exclude any leaf that was in the `done_baseline` (pre-existing done).

These are presumably the two cases `BUG-2403` originally wired; regression appears to be a recent refactor that dropped the `done_in_place` arm.

## Acceptance Criteria

- [ ] `test_finalize_counts_done_in_place_leaf_as_closed` passes.
- [ ] `test_finalize_excludes_pre_existing_done_baseline_from_closed` still passes (no double-counting regression).
- [ ] `main` CI flips green after PR #24 lands and this card is fixed.
- [ ] No new phantom verdicts on clean in-place leaf closures.

## Files Likely Touched

- `scripts/tests/test_builtin_loops.py` — likely no test changes; this is a source bug, not a test bug.
- `scripts/little_loops/loops/autodev.yaml` or equivalent `finalize` state — closure-count logic.
- Possibly `scripts/little_loops/issue_lifecycle.py` if the done_in_place arm lives there.

## Workarounds

PR #24 (`fix/ci-red-v1.163.0`, currently open) deselects this test in its local verification run but does NOT modify CI. The Actions `CI` workflow will continue to fail on this test after PR #24 merges until this card is fixed. Per the QA review of PR #24: "Don't merge this PR with that test still red on main without it being tracked."

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-12 | Priority: P2
