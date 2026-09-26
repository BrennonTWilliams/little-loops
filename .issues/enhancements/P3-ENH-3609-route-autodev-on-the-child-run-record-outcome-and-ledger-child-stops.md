---
id: ENH-3609
type: ENH
title: Route autodev on the child run record outcome and ledger child stops
priority: P3
status: done
discovered_by: issue-size-review
discovered_date: '2026-09-26'
captured_at: '2026-09-26T03:47:26Z'
completed_at: '2026-09-26T05:29:26Z'
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
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3609: Route autodev on the child run record outcome and ledger child stops

## Summary

First of three children of ENH-3608. Route autodev's success path on the child's run record
and send the child's own ledgered stops to `ledger_child_stop` instead of relying on
`skip_inflight`'s marker greps. `skip_inflight` keeps those greps as the fallback for a
`MISSING` record; ENH-3600 deletes them together with the marker files. **Nothing is removed
from `autodev.yaml` here**: every existing decision/spike state stays reachable and behaves as
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
- Every child `ll-issues run-record write` call ends in `|| true`
  (`refine-to-ready-issue.yaml` `check_outcome`, `check_missing_artifacts`,
  `check_scores_from_file`, `write_broke_down`, `record_*`, `mark_*_infra`,
  `classify_terminal`), so a failed write leaves no record and the token reads `MISSING` even
  though the child reached a real terminal.

## Expected Behavior

Two router states, one per entry, each with an exhaustive table over ENH-3607's closed token
vocabulary (`RUN_RECORD_TOKENS`). Routes match tokens exactly (no wildcards), so every token is
listed.

### `route_refine_success` (new; entered from `copy_broke_down.next` and `.on_error`)

| Token | Route |
|---|---|
| `READY` | `check_decision_after_refine` |
| `BLOCKED` (unsuffixed: child reached `done` with thresholds unmet) | `check_decision_after_refine` |
| `MISSING`, `_`, `_error` | `check_decision_after_refine` (fail-open to today's path) |
| `DECOMPOSED` | `detect_children` |
| `CANCELLED` | `skip_cancelled` |
| any suffixed token | `skip_inflight` |

`READY` and unsuffixed `BLOCKED` both keep today's path (`check_decision_after_refine` →
`check_passed`, whose `on_no` still reaches the remediation ladder). Routing unsuffixed
`BLOCKED` to a ledger stop would bypass that whole ladder.

`MISSING`, `_` and `_error` also keep today's path. A child that reached `done` but whose
`|| true` record write failed must not be ledgered `refine_failed`; `check_passed` is itself the
readiness gate, so failing open to it cannot let an unready issue through.

A suffixed token on the success entry cannot occur by construction (every child `done` path
writes a no-class record), so it fails safe to `skip_inflight`.

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
keeps the evidenced exit-143 / `refine-terminal-class` handling (ENH-2727) and its three
marker greps, which now only matter when the record is `MISSING` (a child stop whose
`|| true` record write failed after its marker was written).

### `ledger_child_stop` (new)

Clears `autodev-inflight` and routes to `dequeue_next` **without** writing an
`autodev-skipped.txt` row. The child already ledgered the stop in its marker file, and
`finalize_done` keeps counting from those files until ENH-3600 moves the ledger to run records.
This is the same no-double-count rule `skip_inflight`'s greps implement, now keyed on the
record's routing token instead of a grep.

### `skip_cancelled` (new)

Reached when the child's record says the issue was cancelled during refinement (frontmatter
`status: cancelled`). Appends `ID  cancelled` to `autodev-skipped.txt`, clears
`autodev-inflight`, and routes to `dequeue_next`. Clearing in-flight matters: `dequeue_next`
only overwrites `autodev-inflight` when the queue is non-empty, so routing straight to
`dequeue_next` would leave a stale in-flight file on the last issue and `finalize_done` would
report it as `inflight_unresolved`. The row lands in `finalize_done`'s generic Skipped bucket
with its reason shown (ENH-2989 "ID (reason)" formatting). It does not reuse
`skip_already_resolved`: that state's `already_<status>` stem means "closed before refinement"
and reads its status from `captured.dequeue_status`, which is `PROCESS` on this path.

## Proposed Solution

1. Add `route_refine_success`, `ledger_child_stop` and `skip_cancelled` to `autodev.yaml`. The
   router action is `ll-issues run-record read ${captured.input.output:shell} --run-dir
   ${context.run_dir} --writer refine-to-ready-issue --format token` with
   `evaluate: type: classify`.
2. Set `copy_broke_down.next` and `.on_error` to `route_refine_success`.
   `check_decision_after_refine` stays, reachable from the router.
3. Extend `route_refine_outcome`'s `route:` table as above.
4. Leave `skip_inflight`'s three `grep -qxF` blocks in place; update its comment to say they
   are the `MISSING`-record fallback and that ENH-3600 removes them with the marker files.
5. `DECOMPOSED` → `detect_children` is an intentional behavior change. Today a decomposed
   parent (status `done` after `/ll:issue-size-review`) goes through
   `check_decision_after_refine` → `check_passed`, where `check-readiness` on the closed parent
   usually exits 0 or 1 rather than reaching `check_passed.on_error` → `detect_children`.
   Routing on the record sends it straight to child detection; `detect_children`'s existing
   no-children fallback (`size_review_snap` → `check_broke_down` → `check_parent_resolved`)
   still covers a breakdown that produced no files. `check_passed.on_error` itself is
   unchanged.
6. `CANCELLED` → `skip_cancelled` is also an intentional behavior change: today a cancelled
   issue goes through `check_passed` and can enter the remediation ladder.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`: the two routers, `ledger_child_stop`,
  `skip_cancelled`, `copy_broke_down`, `skip_inflight` (comment only)

### Tests
- `scripts/tests/test_builtin_loops.py`:
  - one structural test per token for each router, asserting both tables cover every
    member of `RUN_RECORD_TOKENS` plus `_` and `_error`;
  - the failure router has no edge to `check_decision_after_refine` / `check_passed` /
    `detect_children`;
  - `route_refine_success` routes `MISSING`, `_` and `_error` to `check_decision_after_refine`;
  - `skip_cancelled` writes `ID  cancelled`, clears `autodev-inflight`, routes to
    `dequeue_next`;
  - update `test_copy_broke_down_routes_to_check_decision_after_refine` (~line 8406, pins
    `copy_broke_down.next == check_decision_after_refine`) to expect `route_refine_success`;
  - update the ENH-3607 route-table assertions in
    `test_refine_current_failure_routes_to_skip_inflight` (~lines 6815-6828,
    `route_refine_outcome` default-only table) for the extended table;
  - the BUG-3390 `_run_skip_inflight` grep tests
    (`test_skip_inflight_skips_refine_failed_when_decision_unresolved_ledgered` ~7986,
    `test_skip_inflight_decision_ledger_match_is_whole_line` ~7998) stay valid (greps kept);
    add their missing spike-inconclusive (BUG-3593) and proposal-unsound (BUG-3574) siblings
    so the `MISSING` fallback is pinned for all three markers;
  - update the `test_record_decision_unresolved_writes_refine_terminal_class` docstring
    (~3054), which describes skip_inflight's grep as the primary suppression.
- `scripts/tests/test_run_record.py` (~lines 866-868): ENH-3607 assertions on the
  `route_refine_outcome` table — update for the extended table.
- `scripts/tests/test_spike_verdict_routing.py`: `test_autodev_routing_table` (~107-108) and
  `test_autodev_ledgers_proposal_unsound_stop_not_as_refine_failed` (~229) pin the greps in
  `skip_inflight`; they stay valid because the greps are kept (ENH-3600 rewrites them).
- `scripts/tests/test_autodev_loop.py:474`
  (`test_refine_current_routes_through_counter_before_copy_broke_down`): still valid
  (`count_repair_cycle_refine.next` stays `copy_broke_down`); confirm it passes unchanged.
- New real-FSM tests:
  - a child ending in `record_decision_unresolved` is ledgered once (in the marker
    file) and never as `refine_failed`;
  - the same stop with the record write failing (no record → `MISSING`) is still ledgered once,
    via `skip_inflight`'s grep fallback;
  - a child reaching `done` below threshold (unsuffixed `BLOCKED`) still reaches the
    remediation ladder through `check_passed.on_no`;
  - a child reaching `done` with no record (`MISSING`) reaches `check_passed`, not
    `skip_inflight`;
  - a `DECOMPOSED` child reaches `detect_children` → `enqueue_children`;
  - a `CANCELLED` child as the last queue entry ledgers `cancelled` and `finalize_done`
    reports no `inflight_unresolved`;
  - a child run with a non-canonical input ID (`NNNN`) routes the same as a canonical one.
- `scripts/tests/test_fsm_topology.py`: `test_autodev_topology` count 107 → 110 (+3:
  `route_refine_success`, `ledger_child_stop`, `skip_cancelled`) with a history comment
  (~line 239).

### Documentation
- `docs/guides/LOOPS_REFERENCE.md:158` ("Typed run record (ENH-3597)" paragraph): extend the
  autodev consumer sentences to cover success and failure routing on the run record,
  `ledger_child_stop`, and `skip_cancelled`, rather than adding a new paragraph.

## Program Design

### Types

- No new types; consumes `RUN_RECORD_TOKENS` / `record_token` from ENH-3607

### Signatures

- `cmd_run_record_read(config: BRConfig, args: argparse.Namespace) -> int` — from ENH-3607; both routers route on its token
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` — existing; `check_passed` still re-verifies scores on the `READY` / `BLOCKED` / `MISSING` path

### Call Path

`autodev.yaml:route_refine_success` -> `cmd_run_record_read` -> `autodev.yaml:check_decision_after_refine` -> `autodev.yaml:check_passed` -> `cmd_check_readiness`

`autodev.yaml:route_refine_outcome` -> `cmd_run_record_read` -> `autodev.yaml:ledger_child_stop` -> `autodev.yaml:dequeue_next`

## Impact

- **Priority**: P3, child of ENH-3608 (EPIC-3565 consolidation)
- **Effort**: Medium: three new states, one extended router, one retarget
- **Risk**: Medium: changes how every refined issue leaves the child. `READY`, unsuffixed
  `BLOCKED`, `MISSING` and every failure-path token keep today's destination. Two routes
  change on purpose: `DECOMPOSED` goes straight to `detect_children`, and `CANCELLED` is
  ledgered by `skip_cancelled` instead of entering `check_passed`.
- **Breaking Change**: No (loop-internal)

## Parent Issue

Decomposed from ENH-3608: Remove autodev spike and decision routes and route on the child run
record. ENH-3608 split into this issue (outcome routing, no removals), ENH-3610 (move decision repair
into the child, add the selector) and ENH-3611 (move spike and proof-gate repair into the
child). ENH-3599 holds the original design rationale.

## Scope Boundaries

- **In scope**: `route_refine_success`, the extended `route_refine_outcome` table,
  `ledger_child_stop`, `skip_cancelled`, retargeting `copy_broke_down`, tests and docs.
- **Out of scope**: removing any state (ENH-3610, ENH-3611); deleting `skip_inflight`'s three
  marker greps, `finalize_done` counting from run records and retiring the child-written
  marker files (all ENH-3600); `auto-refine-and-implement` (ENH-3600).
- **Known, unchanged**: on the failure path `DECOMPOSED` still reaches `skip_inflight` and is
  ledgered `refine_failed`, leaving any children it created unenqueued. This matches today's
  behavior; ENH-3600 should address it when the ledger moves to run records.

## Acceptance Criteria

- [ ] `copy_broke_down.next`/`.on_error` go to `route_refine_success`; `refine_current.on_failure`
  still goes to `route_refine_outcome`; `refine_current` has no explicit `on_no` (BUG-2611)
- [ ] Both routers route every token in `RUN_RECORD_TOKENS` explicitly, plus `_` and `_error`
  (structural test per token)
- [ ] `MISSING`, `_` and `_error` on the success entry reach `check_decision_after_refine`;
  a child `done` with no record reaches `check_passed` (real-FSM test)
- [ ] Unsuffixed `BLOCKED` on the success entry reaches `check_passed` → `on_no` (real-FSM test)
- [ ] A `BLOCKED:decision_unresolved`, `BLOCKED:proposal_unsound` or `DEFERRED:spike_inconclusive`
  stop is counted exactly once by `finalize_done` and never as `refine_failed`, both with a
  record (via `ledger_child_stop`) and without one (via `skip_inflight`'s grep fallback)
  (real-FSM tests for `decision_unresolved`)
- [ ] `DECOMPOSED` on the success entry reaches `detect_children` (real-FSM test)
- [ ] `CANCELLED` on the success entry ledgers `ID  cancelled`, clears `autodev-inflight`, and
  an emptied queue yields no `inflight_unresolved` (real-FSM test)
- [ ] `skip_inflight` keeps its three marker greps; `finalize_done` output is unchanged for
  every existing ledger fixture
- [ ] No state is removed from `autodev.yaml`; `ll-loop validate autodev` passes; the full
  suite passes
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

### Review 2026-09-25

Design review before implementation; all findings applied above:

- Success-entry `MISSING`/`_`/`_error` retargeted from `skip_inflight` to
  `check_decision_after_refine`: every child record write is `|| true`, so a failed write
  would have ledgered a ready issue as `refine_failed`.
- `skip_inflight` grep deletion moved to ENH-3600: with a failed record write, a child stop
  reads `MISSING`, and without the greps it would be double-counted. ENH-3600 already owns
  the marker files and the tests pinning these greps (`test_spike_verdict_routing.py`).
- `CANCELLED` retargeted from `dequeue_next` to new `skip_cancelled`: `dequeue_next` leaves a
  stale `autodev-inflight` when the queue is empty, and the issue vanished from the summary.
- Risk line corrected: `DECOMPOSED` and `CANCELLED` are intentional behavior changes, not
  preserved destinations; Proposed Solution step 5 reworded accordingly.
- Test/doc anchors added (`test_builtin_loops.py` ~7986/~7998/~3054,
  `test_spike_verdict_routing.py`, `test_fsm_topology.py:239`, `LOOPS_REFERENCE.md:158`);
  `ll-loop validate autodev` added to ACs.

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-26T05:29:26 - `828fb0a9-c564-47c7-ba14-651529ec51a0.jsonl`
- `/ll:ready-issue` - 2026-09-26T05:16:59 - `fefeebf9-94c0-4290-827d-16f43267d7b9.jsonl`
- `/ll:confidence-check` - 2026-09-26T04:53:16 - `7eed8935-b54f-432a-8611-fa62522272e9.jsonl`
- `/ll:verify-issues` - 2026-09-26T04:42:56 - `4d8f5d10-1720-42e8-a014-431353de1c43.jsonl`
