---
id: ENH-3609
type: ENH
title: Route autodev on the child run record outcome and ledger child stops
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
captured_at: '2026-09-26T03:47:26Z'
parent: EPIC-3565
decision_needed: false
blocked_by:
- ENH-3607
blocks:
- ENH-3610
relates_to:
- ENH-3608
- ENH-3597
- ENH-3599
- ENH-3600
---

# ENH-3609: Route autodev on the child run record outcome and ledger child stops

## Summary

First of three children of ENH-3608. Route autodev's success path on the child's run record
and replace `skip_inflight`'s marker greps with `ledger_child_stop`. **Nothing is removed from
`autodev.yaml` here**: every existing decision/spike state stays reachable and behaves as
before. This child only changes how autodev reads the child's verdict.

## Current Behavior

- `copy_broke_down` → `check_decision_after_refine` → `check_passed` decides the success path
  from frontmatter flags and scores; it never reads the child's run record.
- After ENH-3607, `route_refine_outcome` handles only `refine_current.on_failure`, routing
  `RETRYABLE_ERROR:rate_limited` to `finalize_rate_limited` and everything else to
  `skip_inflight`.
- `skip_inflight` avoids double-counting sub-loop stops by grepping three child-written marker
  files (`autodev-decision-unresolved.txt`, `autodev-spike-inconclusive.txt`,
  `autodev-proposal-unsound.txt`) for the in-flight ID.

## Expected Behavior

Two router states, one per entry, each with an exhaustive table over ENH-3607's closed token
vocabulary (`RUN_RECORD_TOKENS`). Routes match tokens exactly (no wildcards), so every token is
listed.

### `route_refine_success` (new; entered from `copy_broke_down.next` and `.on_error`)

| Token | Route |
|---|---|
| `READY` | `check_decision_after_refine` |
| `BLOCKED` (unsuffixed: child reached `done` with thresholds unmet) | `check_decision_after_refine` |
| `DECOMPOSED` | `detect_children` |
| `CANCELLED` | `dequeue_next` |
| any suffixed token, `MISSING`, `_`, `_error` | `skip_inflight` |

`READY` and unsuffixed `BLOCKED` both keep today's path (`check_decision_after_refine` →
`check_passed`, whose `on_no` still reaches the remediation ladder). Routing unsuffixed
`BLOCKED` to a ledger stop would bypass that whole ladder. A suffixed token on the success
entry cannot occur by construction (every child `done` path writes a no-class record), so it
fails safe to `skip_inflight`.

### `route_refine_outcome` (extended; entered from `refine_current.on_failure`)

| Token | Route |
|---|---|
| `RETRYABLE_ERROR:rate_limited` | `finalize_rate_limited` (ENH-3607) |
| `RETRYABLE_ERROR:infra` | `skip_inflight_infra` |
| `BLOCKED:decision_unresolved`, `BLOCKED:proposal_unsound`, `DEFERRED:spike_inconclusive` | `ledger_child_stop` |
| `BLOCKED:quality`, `DEFERRED:gate_unmet` | `skip_inflight` (ledgered `refine_failed`, unchanged) |
| `READY`, `BLOCKED`, `DECOMPOSED`, `CANCELLED`, `MISSING`, `_`, `_error` | `skip_inflight` |

The failure router has no edge to `check_decision_after_refine`, `check_passed` or
`detect_children`: a failed child never reuses the success path (ENH-1679). `skip_inflight`
keeps the evidenced exit-143 / `refine-terminal-class` handling (ENH-2727).

### `ledger_child_stop` (new)

Clears `autodev-inflight` and routes to `dequeue_next` **without** writing an
`autodev-skipped.txt` row. The child already ledgered the stop in its marker file, and
`finalize_done` keeps counting from those files until ENH-3600 moves the ledger to run records.
This is the same no-double-count rule `skip_inflight`'s greps implement today, now keyed on the
record's `legacy_class` instead of a grep.

## Proposed Solution

1. Add `route_refine_success` and `ledger_child_stop` to `autodev.yaml`. The router action is
   `ll-issues run-record read ${captured.input.output:shell} --run-dir ${context.run_dir}
   --writer refine-to-ready-issue --format token` with `evaluate: type: classify`.
2. Set `copy_broke_down.next` and `.on_error` to `route_refine_success`.
   `check_decision_after_refine` stays, reachable only from the router.
3. Extend `route_refine_outcome`'s `route:` table as above.
4. Delete the three `grep -qxF` blocks from `skip_inflight`. They become dead because those
   stops now reach `ledger_child_stop`. Keep the `refine-terminal-class` read.
5. `DECOMPOSED` → `detect_children` replaces reaching `detect_children` through
   `check_passed.on_error` for a broken-down issue. `check_passed.on_error` itself is
   unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`: the two routers, `ledger_child_stop`,
  `copy_broke_down`, `skip_inflight`

### Tests
- `scripts/tests/test_builtin_loops.py`:
  - one structural test per token for each router, asserting both tables cover every
    member of `RUN_RECORD_TOKENS`;
  - the failure router has no edge to `check_decision_after_refine` / `check_passed` /
    `detect_children`;
  - rewrite the skip-ledger tests that pin `skip_inflight`'s greps to pin
    `ledger_child_stop` instead;
  - update `test_copy_broke_down_routes_to_check_decision_after_refine` (~line 8406, pins
    `copy_broke_down.next == check_decision_after_refine`) to expect `route_refine_success`;
  - update the ENH-3607 route-table assertions at ~lines 6816-6826 (`route_refine_outcome`
    default-only table) for the extended table.
- `scripts/tests/test_run_record.py` (~lines 866-868): ENH-3607 assertions on the
  `route_refine_outcome` table — update for the extended table.
- `scripts/tests/test_autodev_loop.py:474`
  (`test_refine_current_routes_through_counter_before_copy_broke_down`): still valid
  (`count_repair_cycle_refine.next` stays `copy_broke_down`); confirm it passes unchanged.
- New real-FSM tests:
  - a child ending in `record_decision_unresolved` is ledgered once (in the marker
    file) and never as `refine_failed`;
  - a child reaching `done` below threshold (unsuffixed `BLOCKED`) still reaches the
    remediation ladder through `check_passed.on_no`;
  - a child run with a non-canonical input ID (`NNNN`) routes the same as a canonical one.
- `scripts/tests/test_fsm_topology.py`: `test_autodev_topology` +2 with a history comment.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md`, autodev section: success and failure routing on the
  child run record.

## Program Design

### Types

- No new types; consumes `RUN_RECORD_TOKENS` / `record_token` from ENH-3607

### Signatures

- `cmd_run_record_read(config: BRConfig, args: argparse.Namespace) -> int` — from ENH-3607; both routers route on its token
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` — existing; `check_passed` still re-verifies scores on the `READY` / `BLOCKED` path

### Call Path

`autodev.yaml:route_refine_success` -> `cmd_run_record_read` -> `autodev.yaml:check_decision_after_refine` -> `autodev.yaml:check_passed` -> `cmd_check_readiness`

`autodev.yaml:route_refine_outcome` -> `cmd_run_record_read` -> `autodev.yaml:ledger_child_stop` -> `autodev.yaml:dequeue_next`

## Impact

- **Priority**: P3, child of ENH-3608 (EPIC-3565 consolidation)
- **Effort**: Medium: two new states, one extended router, one retarget, one simplification
- **Risk**: Medium: changes how every refined issue leaves the child, but preserves each route's
  destination
- **Breaking Change**: No (loop-internal)

## Parent Issue

Decomposed from ENH-3608: Remove autodev spike and decision routes and route on the child run
record. ENH-3608 split into this issue (outcome routing, no removals), ENH-3610 (move decision repair
into the child, add the selector) and ENH-3611 (move spike and proof-gate repair into the
child). ENH-3599 holds the original design rationale.

## Scope Boundaries

- **In scope**: `route_refine_success`, the extended `route_refine_outcome` table,
  `ledger_child_stop`, retargeting `copy_broke_down`, deleting `skip_inflight`'s three marker
  greps, tests and docs.
- **Out of scope**: removing any state (ENH-3610, ENH-3611); `finalize_done`
  counting from run records and retiring the child-written marker files (ENH-3600);
  `auto-refine-and-implement` (ENH-3600).

## Acceptance Criteria

- [ ] `copy_broke_down.next`/`.on_error` go to `route_refine_success`; `refine_current.on_failure`
  still goes to `route_refine_outcome`; `refine_current` has no explicit `on_no` (BUG-2611)
- [ ] Both routers route every token in `RUN_RECORD_TOKENS` explicitly, plus `_` and `_error`
  (structural test per token)
- [ ] Unsuffixed `BLOCKED` on the success entry reaches `check_passed` → `on_no` (real-FSM test)
- [ ] A `BLOCKED:decision_unresolved`, `BLOCKED:proposal_unsound` or `DEFERRED:spike_inconclusive`
  stop is counted exactly once by `finalize_done` and never as `refine_failed`
  (real-FSM test for `decision_unresolved`)
- [ ] `skip_inflight` no longer greps any marker file; `finalize_done` output is unchanged for
  every existing ledger fixture
- [ ] No state is removed from `autodev.yaml`; the full suite passes
- [ ] Existing tests pinning the old routing (`test_builtin_loops.py` copy_broke_down /
  route_refine_outcome assertions, `test_run_record.py` route-table assertions) are updated
  to the new topology

## Verification Notes

Verified 2026-09-25 (graph: provider=`codegraph` freshness=`fresh`; not needed for verdict).

Verdict at time of check: **DIRECTIVE_DRIFT** (the Tests / Acceptance Criteria corrections
below were applied in the same pass, so the issue as it now reads is up to date — this
section is a record of what was wrong and fixed, not an outstanding action item)

- Claims about current state hold: `route_refine_outcome` (autodev.yaml:554) has only the
  `rate_limited` route + `_`/`_error`; `skip_inflight` (570) has the three marker greps
  (604/611/617); `copy_broke_down` (662) → `check_decision_after_refine`; `check_passed.on_error`
  → `detect_children` (709); `RUN_RECORD_TOKENS` matches the 12 tokens listed; child writes
  run records with `legacy_class` `decision_unresolved`/`spike_inconclusive`/`proposal_unsound`/
  `gate_unmet`/`infra`. ENH-3607 (blocker) is done. No required decision rules; no unverifiable
  evidence quotes.
- Fixed: Integration Map / ACs omitted existing tests that pin the old routing
  (`test_builtin_loops.py` ~6816-6826 and ~8406, `test_run_record.py` ~866-868).

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-26T04:42:56 - `4d8f5d10-1720-42e8-a014-431353de1c43.jsonl`
