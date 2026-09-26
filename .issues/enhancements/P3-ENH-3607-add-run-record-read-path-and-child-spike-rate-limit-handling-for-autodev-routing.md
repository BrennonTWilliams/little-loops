---
id: ENH-3607
type: ENH
title: Add run-record read path and child spike rate-limit handling for autodev routing
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
captured_at: '2026-09-26T03:19:50Z'
decision_needed: false
blocks:
- ENH-3608
relates_to:
- ENH-3577
- ENH-3597
- ENH-3599
parent: EPIC-3565
---

# ENH-3607: Add run-record read path and child spike rate-limit handling for autodev routing

## Summary

First, additive half of ENH-3599. Add the `ll-issues run-record read` token path, give the
child's `run_spike` the rate-limit handling autodev's copy has, make a rate-limit-exhausted
child run distinguishable in its run record, and route that case in autodev to
`finalize_rate_limited`. No autodev spike/decision state is removed here; that is ENH-3608.

## Parent Issue

Decomposed from ENH-3599: Move spike and decision repair routing from autodev into
refine-to-ready-issue. See the parent for the full design (*Run-record read path*,
*Outcome routing table*, *Rate-limit exhaustion*), Codebase Research Findings and
wiring/test/doc inventories; the items below are this child's share.

## Current Behavior

- `ll-issues run-record` has only a `write` subcommand (`cmd_run_record_write` in
  `little_loops.cli.issues.run_record`). No loop reads a run record.
- The child's `run_spike` (`refine-to-ready-issue.yaml`) has no
  `with_rate_limit_handling`; autodev's copy has `rate_limit_max_wait_seconds: 14400` and
  `on_rate_limit_exhausted: finalize_rate_limited`.
- The child's `mark_rate_limit_infra` writes `legacy_class: infra` with no other marker, so
  its record is indistinguishable from `mark_evidence_absent_infra` and
  `mark_spike_no_verdict_infra`.
- When the child ends at `failed` after an exhausted rate limit (e.g. `resolve_decision_*`
  → `check_decide_rate_limited` → `mark_rate_limit_infra`), autodev's
  `refine_current.on_failure` → `skip_inflight` skips the issue and hands the next issue
  straight into the same rate limit. Autodev's own spike/decide routes halt the run instead.

## Expected Behavior

- `ll-issues run-record read <ID> --run-dir <dir> --writer refine-to-ready-issue --format
  token` prints one token: `<OUTCOME>` or `<OUTCOME>:<legacy_class>` (outcome upper-cased:
  `READY`, `DECOMPOSED`, `CANCELLED`, `BLOCKED`, `DEFERRED`, `RETRYABLE_ERROR`),
  `RETRYABLE_ERROR:rate_limited` when `evidence_refs` contains `rate_limit_exhausted`, and
  `MISSING` when `read_run_record` returns `None`. Exit code 0 in all those cases.
- The child's `run_spike` waits out rate limits (`fragment: with_rate_limit_handling`,
  `rate_limit_max_wait_seconds: 14400`, `on_rate_limit_exhausted: mark_rate_limit_infra`).
- `mark_rate_limit_infra` writes `--evidence-refs rate_limit_exhausted` (keeps
  `legacy_class: infra`, so `outcome_from_legacy_class` is unchanged).
- Autodev gains `route_refine_outcome` on `refine_current.on_failure` only:
  `RETRYABLE_ERROR:rate_limited` → `finalize_rate_limited`; every other token (and `_`,
  `_error`) → `skip_inflight`, so all other failure behavior is unchanged.

## Scope Boundaries

- **In scope**: the read subcommand, the child's `run_spike` rate-limit handling, the
  `rate_limit_exhausted` evidence ref, and `route_refine_outcome` on the failure path with
  the two routes above.
- **Out of scope** (ENH-3608): the success-path outcome routing, `ledger_child_stop`,
  `select_obligation`, and removing any autodev spike/decision state or marker.

## Proposed Solution

1. Add `read` to the `run-record` subparser in `little_loops.cli.issues.run_record`
   (`cmd_run_record_read`), calling `read_run_record(run_dir, writer, issue_id)`. Only the
   `token` format is required.
2. In `refine-to-ready-issue.yaml`, add the three rate-limit keys to `run_spike` and
   `--evidence-refs rate_limit_exhausted` to `mark_rate_limit_infra`'s `run-record write`.
3. In `autodev.yaml`, add `route_refine_outcome` (shell action running the read path,
   `evaluate: type: classify`, `route:` table) and set `refine_current.on_failure:
   route_refine_outcome`. Do **not** add `on_no` to `refine_current` (BUG-2611).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/run_record.py` — `read` subcommand
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `run_spike`, `mark_rate_limit_infra`
- `scripts/little_loops/loops/autodev.yaml` — `route_refine_outcome`, `refine_current.on_failure`

### Tests
- `scripts/tests/test_run_record.py` — read-path unit tests: each outcome token, the
  `legacy_class` suffix, `rate_limited`, and `MISSING` for no file / bad JSON / writer
  mismatch / ID mismatch
- `scripts/tests/test_builtin_loops.py` — rewrite `test_refine_current_failure_routes_to_skip_inflight`
  and `test_refine_current_compiled_on_no_resolves_to_skip_inflight` (~`:6815`, `:6851`)
  to assert `route_refine_outcome`, keeping their ENH-1679 / BUG-2611 intent (failure never
  reuses the success path; the default route still reaches `skip_inflight`);
  `test_refine_current_has_no_explicit_on_no` stays unchanged
- `scripts/tests/test_fsm_topology.py` — `test_autodev_topology` 106 → 107 with a history comment
- New real-FSM tests: a rate-limited child `run_spike` waits rather than failing; a child
  run ending in `mark_rate_limit_infra` routes autodev to `finalize_rate_limited`

### Documentation
- `docs/reference/CLI.md` — document `ll-issues run-record read`
- `docs/guides/LOOPS_REFERENCE.md` — autodev section: rate-limit exhaustion in the child
  now halts the run

## Acceptance Criteria

- [ ] `ll-issues run-record read --format token` prints the tokens above; a missing,
  unparsable or writer/ID-mismatched record prints `MISSING`, never `READY` (unit tests)
- [ ] The child's `run_spike` has `with_rate_limit_handling`,
  `rate_limit_max_wait_seconds: 14400` and `on_rate_limit_exhausted: mark_rate_limit_infra`
  (real-FSM test: a rate-limited spike still waits rather than failing)
- [ ] `mark_rate_limit_infra`'s record carries `rate_limit_exhausted` in `evidence_refs`
  and still has `legacy_class: infra` / `outcome: retryable_error`
- [ ] Autodev routes `RETRYABLE_ERROR:rate_limited` from `refine_current.on_failure` to
  `finalize_rate_limited`; every other failure still reaches `skip_inflight` (real-FSM test
  plus structural test)
- [ ] `refine_current` has no explicit `on_no`; `on_success` and `on_error` are unchanged
- [ ] No autodev spike/decision state or marker is removed; the full suite passes

## Impact

- **Priority**: P3 - child of ENH-3599 (EPIC-3565 consolidation); unblocks ENH-3608
- **Effort**: Medium - one CLI subcommand, three YAML edits, one new autodev state
- **Risk**: Low - additive; the only autodev behavior change is halting on child
  rate-limit exhaustion instead of skipping
- **Breaking Change**: No

## Program Design

### Types

- No new types; consumes `RunRecord` from ENH-3597

### Signatures

- `cmd_run_record_read(config: BRConfig, args: argparse.Namespace) -> int` — new; prints the outcome token and returns 0
- `read_run_record(run_dir: Path, writer: str, issue_id: str) -> RunRecord | None` — existing (ENH-3597)

### Call Path

`autodev.yaml:route_refine_outcome` -> `cmd_run_record_read` -> `read_run_record` -> `autodev.yaml:finalize_rate_limited`

## Status

**Open** | Created: 2026-09-26 | Priority: P3
