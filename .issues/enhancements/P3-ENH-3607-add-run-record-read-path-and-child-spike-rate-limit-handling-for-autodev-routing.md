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
- ENH-3609
relates_to:
- ENH-3577
- ENH-3597
- ENH-3599
parent: EPIC-3565
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3607: Add run-record read path and child spike rate-limit handling for autodev routing

## Summary

First, additive half of ENH-3599. Add the `ll-issues run-record read` token path, give the
child's `run_spike` the rate-limit handling autodev's copy has, make a rate-limit-exhausted
child run distinguishable in its run record, and route that case in autodev to
`finalize_rate_limited`. No autodev spike/decision state is removed here; that is ENH-3610 and ENH-3611.

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
- The record is keyed on the canonical frontmatter `id` (`cmd_run_record_write` stores
  `canonical_id` and `write_run_record` names the file after it), but autodev's queue holds
  the user's input verbatim (`ll-loop run autodev "3607,P3-ENH-3608"`). `read_run_record`
  requires an exact filename and stored-`issue_id` match, so a naive read with
  `captured.input.output` returns `None` for any non-canonical input.
- The child's `resolve_issue` clears the previous record with
  `rm -f .../run-records/refine-to-ready-issue/$${ID}.json` using the raw input ID, so for
  non-canonical input the stale record from an earlier entry of the same issue survives.
- The child's four no-class writes (`check_outcome`, `check_missing_artifacts`,
  `check_scores_from_file`, `write_broke_down`) omit `--readiness-threshold` /
  `--outcome-threshold`, so `ready` vs `blocked` is computed against config thresholds while
  the child's own gates use the loop's `readiness_threshold` / `outcome_threshold` context
  values (overridable per run, BUG-2767).

## Expected Behavior

- `ll-issues run-record read <ID> --run-dir <dir> --writer refine-to-ready-issue --format
  token` resolves `<ID>` to the canonical frontmatter `id` exactly as the writer does
  (`_resolve_issue_id` → frontmatter `id`, falling back to the raw argument), then prints
  exactly one token from this closed vocabulary (`RUN_RECORD_TOKENS`), exit code 0 in every
  case:

  | Token | When |
  |---|---|
  | `READY` | outcome `ready` |
  | `BLOCKED` | outcome `blocked`, `legacy_class` null (child reached `done` with thresholds unmet) |
  | `BLOCKED:decision_unresolved` / `BLOCKED:proposal_unsound` / `BLOCKED:quality` | outcome `blocked` with that class |
  | `DEFERRED:spike_inconclusive` / `DEFERRED:gate_unmet` | outcome `deferred` with that class |
  | `RETRYABLE_ERROR:rate_limited` | outcome `retryable_error` and `evidence_refs` contains `rate_limit_exhausted` |
  | `RETRYABLE_ERROR:infra` | any other `retryable_error` |
  | `DECOMPOSED` / `CANCELLED` | those outcomes — never suffixed, even when `legacy_class` is set |
  | `MISSING` | `read_run_record` returns `None`, or the ID cannot be resolved |

  FSM `route:` tables match tokens exactly (`FSMExecutor._route`: `verdict in routes`; no
  glob or prefix matching), so the vocabulary is closed and every consumer enumerates it.
- `ll-issues run-record clear <ID> --run-dir <dir> --writer <writer>` resolves the canonical
  ID the same way and deletes that record (exit 0 whether or not it existed). The child's
  `resolve_issue` uses it instead of the raw-ID `rm -f`.
- The child's four no-class `run-record write` calls pass
  `--readiness-threshold ${context.readiness_threshold}` and
  `--outcome-threshold ${context.outcome_threshold}`, so the record's `ready`/`blocked`
  matches the thresholds the child actually gated on.
- The child's `run_spike` waits out rate limits (`fragment: with_rate_limit_handling`,
  `rate_limit_max_wait_seconds: 14400`, `on_rate_limit_exhausted: mark_rate_limit_infra`).
- `mark_rate_limit_infra` writes `--evidence-refs rate_limit_exhausted` (keeps
  `legacy_class: infra`, so `outcome_from_legacy_class` is unchanged).
- Autodev gains `route_refine_outcome` on `refine_current.on_failure` only:
  `RETRYABLE_ERROR:rate_limited` → `finalize_rate_limited`; every other token (and `_`,
  `_error`) → `skip_inflight`, so all other failure behavior is unchanged.

## Scope Boundaries

- **In scope**: the `read` and `clear` subcommands with canonical ID resolution, the closed
  token vocabulary, the child's `run_spike` rate-limit handling, the `rate_limit_exhausted`
  evidence ref, threshold pass-through on the child's no-class writes, and
  `route_refine_outcome` on the failure path with the two routes above.
- **Out of scope**: the success-path outcome routing and `ledger_child_stop` (ENH-3609);
  the selector and removing any autodev spike/decision state or marker (ENH-3610,
  ENH-3611). Rate-limit handling for the child's other slash-command
  states (`refine_issue`, `refine_followup`, `wire_issue`, `reconcile_issue`,
  `format_issue_*`): a 429 exhausted there still ends in `diagnose` → `classify_terminal`
  and skips the issue rather than halting autodev. Only `run_spike` and the
  `oracles/resolve-decision` path (`check_decide_rate_limited`) halt the run after this
  issue.

## Proposed Solution

1. In `little_loops.run_record`, add `RUN_RECORD_TOKENS` (the twelve tokens above) and
   `record_token(record: RunRecord | None) -> str`, which maps a record (or `None`) to its
   token. Keeping the mapping next to `outcome_from_legacy_class` lets ENH-3600 reuse it.
2. In `little_loops.cli.issues.run_record`, add `canonical_record_id(config, issue_id)`
   (`_resolve_issue_id` → frontmatter `id`, else the raw argument) and use it in
   `cmd_run_record_write` too, so both sides share one ID rule. Add `read`
   (`cmd_run_record_read`, `--format token` only) and `clear` (`cmd_run_record_clear`)
   sub-subcommands; update `cmd_run_record`'s dispatch, its "requires a subcommand (write)"
   error text and the `run-record` parser help.
3. In `refine-to-ready-issue.yaml`:
   - add `fragment: with_rate_limit_handling`, `rate_limit_max_wait_seconds: 14400` and
     `on_rate_limit_exhausted: mark_rate_limit_infra` to `run_spike`;
   - add `--evidence-refs rate_limit_exhausted` to `mark_rate_limit_infra`'s
     `run-record write`;
   - replace `resolve_issue`'s raw-ID `rm -f` of the record with
     `ll-issues run-record clear "$${ID}" --run-dir ${context.run_dir} --writer refine-to-ready-issue || true`;
   - add `--readiness-threshold ${context.readiness_threshold:shell}
     --outcome-threshold ${context.outcome_threshold:shell}` to the four no-class writes;
   - update the now-stale comments at `check_spike_needed` ("deliberately not carried
     here") and `reconcile_issue` ("0/5 sibling slash-command states in this file carry
     them" — `run_spike` becomes the one exception, justified because it is the only child
     state that can wait out a long spike 429).
4. In `autodev.yaml`, add `route_refine_outcome` (shell action running the read path with
   `${captured.input.output:shell}`, `evaluate: type: classify`, `route:` table) and set
   `refine_current.on_failure: route_refine_outcome`. Do **not** add `on_no` to
   `refine_current` (BUG-2611). Update the `refine_current` BUG-3390 / ENH-2727 comments
   and `skip_inflight`'s "refine_current.on_failure/on_error stay `skip_inflight`" comment.
   `finalize_rate_limited` leaves `autodev-inflight` set, matching autodev's own
   `run_spike` exhaustion route, so `finalize_done` reports the issue as in flight.

## Integration Map

### Files to Modify
- `scripts/little_loops/run_record.py` — `RUN_RECORD_TOKENS`, `record_token`
- `scripts/little_loops/cli/issues/run_record.py` — `canonical_record_id`, `read` and
  `clear` subcommands, dispatch/help text
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `run_spike`,
  `mark_rate_limit_infra`, `resolve_issue`, the four no-class writes, two stale comments
- `scripts/little_loops/loops/autodev.yaml` — `route_refine_outcome`,
  `refine_current.on_failure`, `refine_current` / `skip_inflight` comments

### Tests
- `scripts/tests/test_run_record.py` — `record_token` for all twelve tokens (assert the
  set equals `RUN_RECORD_TOKENS`); `DECOMPOSED`/`CANCELLED` stay unsuffixed with a
  `legacy_class` set; read-path CLI tests: `MISSING` for no file / bad JSON / writer
  mismatch / ID mismatch / unresolvable ID; the same record read back via `3607`,
  `ENH-3607` and `P3-ENH-3607`; `clear` deletes the canonical file for a numeric ID and
  exits 0 when absent
- `scripts/tests/test_builtin_loops.py` — structural: the four no-class writes pass both
  threshold flags; `resolve_issue` uses `run-record clear`
- `scripts/tests/test_builtin_loops.py` — rewrite `test_refine_current_failure_routes_to_skip_inflight`
  and `test_refine_current_compiled_on_no_resolves_to_skip_inflight` (~`:6815`, `:6851`)
  to assert `route_refine_outcome`, keeping their ENH-1679 / BUG-2611 intent (failure never
  reuses the success path; the default route still reaches `skip_inflight`);
  `test_refine_current_has_no_explicit_on_no` stays unchanged
- `scripts/tests/test_fsm_topology.py` — `test_autodev_topology` 106 → 107 with a history comment
- New real-FSM tests: a rate-limited child `run_spike` waits rather than failing; a child
  run ending in `mark_rate_limit_infra` routes autodev to `finalize_rate_limited`

### Documentation
- `docs/reference/CLI.md` — document `ll-issues run-record read` (with the token table) and
  `run-record clear`
- `docs/reference/API.md` — `little_loops.run_record`: `RUN_RECORD_TOKENS`, `record_token`
- `docs/guides/LOOPS_REFERENCE.md` — autodev section: rate-limit exhaustion in the child's
  spike or decision path now halts the run

## Acceptance Criteria

- [ ] `ll-issues run-record read --format token` prints only tokens in `RUN_RECORD_TOKENS`;
  a missing, unparsable or writer/ID-mismatched record, or an unresolvable ID, prints
  `MISSING`, never `READY` (unit tests)
- [ ] A record written for an issue reads back as the same token whether the ID is passed as
  `NNNN`, `TYPE-NNNN` or `PN-TYPE-NNNN`; `run-record clear` removes it for any of those forms
- [ ] The child's four no-class writes pass `--readiness-threshold` / `--outcome-threshold`
  from context (structural test)
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

- **Priority**: P3 - child of ENH-3599 (EPIC-3565 consolidation); unblocks ENH-3609
- **Effort**: Medium - two CLI subcommands and a token mapper, child YAML edits across
  seven states, one new autodev state
- **Risk**: Low - additive; the only autodev behavior change is halting on child
  rate-limit exhaustion instead of skipping
- **Breaking Change**: No

## Program Design

### Types

- No new types; consumes `RunRecord` from ENH-3597
- `RUN_RECORD_TOKENS: tuple[str, ...]` — new module constant in `little_loops.run_record`

### Signatures

- `record_token(record: RunRecord | None) -> str` — new; maps a record to its routing token, `MISSING` for `None`
- `canonical_record_id(config: BRConfig, issue_id: str) -> str` — new; the frontmatter `id` of the resolved issue, else `issue_id`
- `cmd_run_record_read(config: BRConfig, args: argparse.Namespace) -> int` — new; prints the outcome token and returns 0
- `cmd_run_record_clear(config: BRConfig, args: argparse.Namespace) -> int` — new; deletes the canonical record and returns 0
- `read_run_record(run_dir: Path, writer: str, issue_id: str) -> RunRecord | None` — existing (ENH-3597)

### Call Path

`autodev.yaml:route_refine_outcome` -> `cmd_run_record_read` -> `canonical_record_id` -> `read_run_record` -> `record_token` -> `autodev.yaml:finalize_rate_limited`

`refine-to-ready-issue.yaml:resolve_issue` -> `cmd_run_record_clear` -> `canonical_record_id`

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-26T03:31:35 - `dc688663-27b9-419d-a204-432e1862504f.jsonl`
- `/ll:verify-issues` - 2026-09-26T03:26:54 - `0645a9c4-2e38-4d02-9b76-47ae90b8a2ea.jsonl`
