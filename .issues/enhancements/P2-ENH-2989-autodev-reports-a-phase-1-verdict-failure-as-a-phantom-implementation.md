---
id: ENH-2989
title: autodev reports a Phase 1 verdict failure as a phantom implementation
type: ENH
priority: P3
status: open
captured_at: '2026-08-02T00:00:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2988
labels:
- automation
- resilience
- loops
testable: true
---

# ENH-2989: autodev reports a Phase 1 verdict failure as a phantom implementation

## Summary

When `ll-auto` exits non-zero without ever reaching Phase 2, `autodev.yaml`
records the issue as `unverified` with verdict `phantom` and the message
"threshold passed; implementation did not close — re-queue to retry". That is
materially wrong: no implementation was attempted. The run summary blames the
issue for a failure that happened before any work began.

Give autodev a probe that distinguishes "never reached implementation" from
"implemented but did not close."

## Current Behavior

`implement_current` evaluates on `exit_code` alone. On a non-zero exit it routes
through `check_learning_gate` (pattern `GATE_BLOCKED`) and `check_impl_auth`
(pattern `AUTH_FAILED`); neither matches a Phase 1 verdict failure, so control
falls through to `clear_inflight_after_impl_failure` and on to `finalize_done`,
which classifies the issue as `unverified` and writes
`{"verdict": "phantom", "not_closed": 1}`.

Observed in `.loops/runs/autodev-20260801T214427/` (ENH-2971). The full state
trace: `refine_issue`, `wire_issue` and `confidence_check` all succeeded —
Readiness 96, Outcome 79 — then `implement_current` failed in 11.5 seconds
because `ll-auto` Phase 1 got an unparseable `ready-issue` verdict and returned
"Issues processed: 0". `summary.json` reports `"verdict":"phantom"`.

The operator-visible output is actively misleading: it points at the issue's
implementation when the actual failure was a single non-compliant model turn
during validation.

## Expected Behavior

A run that never reached Phase 2 is reported as its own outcome — distinct from
`phantom` — and re-queued, rather than recorded as a failed implementation.

The distinction should be legible in both the run summary and `summary.json`.

## Program Design

`ll-auto`'s output already carries the signal. This run's `ll_auto_last.txt`
contains `ready-issue verdict: UNKNOWN`, `is NOT READY for implementation`, and
`Issues processed: 0` — any of which distinguishes the case from a real Phase 2
failure. The cheapest correct discriminator is probably a dedicated exit code
from `ll-auto`, so the FSM branches on a number rather than pattern-matching
prose that is free to change.

### Signatures

```yaml
# scripts/little_loops/loops/autodev.yaml — new state, mirroring check_impl_auth
check_impl_reached:
  action: <probe ll-auto output or exit code>
  evaluate:
    type: check_output
    pattern: "NOT_STARTED"
  on_yes: <record not_started + re-queue>
  on_no: check_learning_gate
```

```python
# scripts/little_loops/issue_manager.py — IssueProcessingResult already carries
# the fact; what is missing is a distinct process-level exit signal.
IssueProcessingResult.failure_reason  # e.g. "NOT READY: UNKNOWN - 0 concern(s)"
```

### Call Path

`implement_current` (`scripts/little_loops/loops/autodev.yaml`) shells out to
`ll-auto` and evaluates on `exit_code`. On non-zero it routes
`check_learning_gate` (pattern `GATE_BLOCKED`) → `check_impl_auth` (pattern
`AUTH_FAILED`) → `clear_inflight_after_impl_failure` → `dequeue_next` →
`finalize_done`. The new state inserts ahead of `check_learning_gate`, matching
the two existing probes' shape exactly.

The signal originates in `process_issue_inplace`
(`scripts/little_loops/issue_manager.py:719-930`), whose Phase 1 branches all
return a `_stamped_result(success=False, ...)` before Phase 2's
`run_with_continuation` is ever called — that early-return set is precisely the
"never reached implementation" population.

`finalize_done` is where the summary key is written; it currently emits
`verdict` / `closed` / `not_closed` / `skipped` / `gate_blocked` /
`decision_unresolved` / `inflight_unresolved` / `abandoned`.

### Open questions for refinement

- Whether the discriminator is a new `ll-auto` exit code or output pattern.
- Which summary key it emits — `not_started`, alongside the existing keys.
- Whether re-queueing is unconditional or bounded by an attempt counter, to
  avoid an issue looping on a persistently failing validation step.

Note that `little_loops.ready_issue`'s retry-on-`UNKNOWN` makes this case rarer,
but does not eliminate it: a retry that also whiffs, or any other Phase 1
terminal verdict, still lands here.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact routing chain** (`scripts/little_loops/loops/autodev.yaml`):
- `implement_current` (lines 796-837): `fragment: shell_exit`, `capture: ll_auto_output`; `on_yes: dequeue_next`, `on_no: check_learning_gate`, `on_error: check_learning_gate`.
- `check_learning_gate` (lines 839-851): `fragment: ll_auto_learning_gate_check` (`loops/lib/common.yaml:327-351`); greps `ll_auto_last.txt` for `LEARNING_GATE_BLOCKED`; `on_yes: mark_gate_blocked`, `on_no: check_impl_auth`, `on_error: check_impl_auth`.
- `check_impl_auth` (lines 877-884): `fragment: ll_auto_auth_check` (`loops/lib/common.yaml:304-325`); greps for `401|403|unauthorized|forbidden|...`; `on_yes: abort_env_not_ready`, `on_no: clear_inflight_after_impl_failure`, `on_error: clear_inflight_after_impl_failure`.
- `clear_inflight_after_impl_failure` (lines 886-896): removes the `autodev-inflight` sentinel, `next: dequeue_next` — it does not append the ID to any reason-coded ledger, so the ID's only ledger entry remains the earlier `autodev-staged.txt` write from `check_passed`.
- `finalize_done` (lines 1967-2122): promotes `autodev-staged.txt` IDs into `autodev-passed.txt` only if `ll-issues show --json` reports `status` in `done|completed|cancelled` (1978-1990); otherwise appends to `autodev-unverified.txt` (1988). Verdict logic (2090-2103): `PASSED_COUNT>0 && UNVERIFIED_COUNT==0 && ABANDONED==0 → success`; `PASSED_COUNT>0 → partial`; `UNVERIFIED_COUNT>0 || ABANDONED>0 → phantom`; else `no-op`. A single-issue run that fails at Phase 1 has `PASSED_COUNT=0, UNVERIFIED_COUNT=1` → `phantom`.

**All Phase 1 early-return branches** in `process_issue_inplace()` (`scripts/little_loops/issue_manager.py:619-1017`), each setting `IssueProcessingResult.success=False` before Phase 2's `run_with_continuation()` (line 1055):

| Location | Condition | `failure_reason` | Stdout marker |
|---|---|---|---|
| 806-813 | fallback ready-issue retry failed | "Fallback failed after path mismatch" | none |
| 819-832 | fallback retry still mismatched | "Path mismatch persisted after fallback" | none |
| 858-870 | `CLOSE` + `invalid_ref` | "Invalid reference: ..." | none |
| 872-885 | `CLOSE`, no validated path | "CLOSE without validated file path" | none |
| 904-911 | `CLOSE`, `close_issue()` failed | "CLOSE failed: ..." | none |
| 913-925 | `BLOCKED` verdict | "BLOCKED: {concerns}" | none |
| 927-941 | `is_ready=False` (covers `NOT_READY`, `NEEDS_REVIEW`, and `UNKNOWN`) | "NOT READY: {verdict} - {N} concern(s)" | **none** — this is the ENH-2989 case |
| 993-999 | learning gate `"blocked"` | "Learning gate blocked: ..." | `LEARNING_GATE_BLOCKED {issue_id}` (line 992) |
| 1011-1017 | learning gate `"impl_failed"` | "Learning gate: implementation failed" | `IMPLEMENT_FAILED {issue_id}` (line 1010) — not checked by any `autodev.yaml` fragment today |

`output_parsing.py:parse_ready_issue_output()` seeds `verdict = "UNKNOWN"` (line 272) as the default, never overwritten if no strategy finds a recognizable token; `VALID_VERDICTS` (line 24) does not include `"UNKNOWN"`. `is_ready = verdict in ("READY", "CORRECTED")` (line 417), so `UNKNOWN` always routes into the same NOT-READY branch as a genuine `NOT_READY` verdict. `ready_issue.py:run_ready_issue_with_retry()` (lines 83-126) retries only while `verdict == "UNKNOWN"`, up to `config.automation.ready_issue_unknown_retries`; exhausting retries still lands here.

`AutoManager.run()` (`issue_manager.py:1552-1627`) returns exit code `1` identically for a Phase 1 rejection and a genuine Phase 2 crash — `processed_count` is never incremented on `success=False` (1596-1597), and `_log_timing_summary()` prints `"Issues processed: 0"` (1636) in both cases. No distinct exit code space exists today — every early-return above shares the same process exit code, except the learning-gate branches, which are additionally marked on stdout.

**Codebase convention for this kind of discriminator** (from `check_learning_gate`/`check_impl_auth`, the two existing analogues in `loops/lib/common.yaml:304-351`): both are `output_contains`-evaluated fragment states that grep `${context.run_dir}/ll_auto_last.txt` for a stable literal marker string — never a distinct process exit code, and never reading the FSM's `capture:` value directly in the grep (BUG-2594: interpolating captured Markdown into a shell string breaks on untrusted content). The marker itself originates from a `print(f"MARKER {issue_id}", flush=True)` call inside `issue_manager.py` (e.g. `LEARNING_GATE_BLOCKED` at line 992, `IMPLEMENT_FAILED` at line 1010) — Python emits, the FSM fragment consumes. This is direct evidence against the first open question below: the established convention in this codebase for "does ll-auto distinguish reason X" is a stdout marker, not an exit code. No stdout marker currently exists for the Phase 1 NOT-READY/UNKNOWN branch (`issue_manager.py:927-941`) — every other discriminator autodev routes on has one; this branch is the outlier, not a differently-conventioned case.

`check_learning_gate` is deliberately ordered before `check_impl_auth`, "so a gate block is not misattributed as an auth failure or a generic implementation failure" (`common.yaml:338-341`) — the same ordering-matters property would apply to inserting a new discriminator state ahead of both, per the issue's own proposed `check_impl_reached` signature above.

**Summary.json / ledger-file convention**: reason codes are recorded via a dedicated per-run ledger file under `${context.run_dir}/` (two shapes coexist: standalone one-reason-per-file, e.g. `autodev-gate-blocked.txt`, `autodev-decision-unresolved.txt`; or a shared `autodev-skipped.txt` with a trailing `"  <reason>"` token), read back and counted by `finalize_done`, then folded into one fixed `printf` that emits the whole `summary.json` object (`autodev.yaml:2105-2107`). `auto-refine-and-implement.yaml`'s `finalize` state independently reimplements the same convention rather than sharing code with `autodev.yaml`'s `finalize_done` — CLAUDE.md's ENH-2666 note on `deferred_reason` parity documents this cross-loop duplication as a known, tracked consistency requirement, not an accident.

**Re-queue mechanics**: there is no dedicated "push back to queue" state — the existing pattern is a direct read-modify-write of `${context.run_dir}/autodev-queue.txt`. The closest analogue to "give this issue another attempt" is `implement_current`'s own stale-inflight-resume logic (lines 804-821), which prepends a recovered ID back onto the queue. The `deferred`-transition convention (`ll-issues set-status $ID deferred --by automation --reason <code>`, e.g. `mark_gate_blocked` at lines 853-875) is the opposite of a re-queue — it removes the issue from this run's active selection rather than retrying it.

**Test coverage for FSM routing assertions** (`scripts/tests/test_autodev_loop.py`, `scripts/tests/test_builtin_loops.py::TestAutodevLoop`, `LOOP_FILE = BUILTIN_LOOPS_DIR / "autodev.yaml"` at line 4130): three established shapes — (a) static state-shape assertions indexing `data["states"][...]` for `fragment`/`on_yes`/`on_no`/`on_error` literals (e.g. `test_check_learning_gate_routes_to_auth_check_on_no`, lines 5000-5014); (b) marker/pattern assertions against the real `evaluate_output_contains` evaluator with no subprocess (`test_autodev_loop.py:83-127`); (c) end-to-end subprocess execution of the real shell action against a synthetic `run_dir`, used specifically for `finalize`-shaped states (`test_builtin_loops.py:2886-2992`, e.g. `test_finalize_gate_blocked_count_surfaces` at lines 3253-3260) — the closest existing pattern for a test asserting a new `summary.json` key.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` — two direct call sites (`_run_with_timeout` and the sequential-retry block) construct/read `IssueProcessingResult` directly and would silently gain any new dataclass field; the same Phase-1-vs-Phase-2 conflation risk exists here (`ll-sprint` also blames Phase 2 for a Phase 1 failure), but this file is out of this issue's declared Scope Boundaries ("other loops' summary schemas") — awareness only, no change required [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the "Diagram omissions" paragraph for `autodev` (~line 1045) and the Auth fast-fail (ENH-2353) Notes paragraph (~line 1047) both hard-code the current `implement_current → check_learning_gate → check_impl_auth` chain verbatim; need the new discriminator state added to the documented routing [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — the Outcome-token handoff marker table (lines 245-259) and surrounding convention prose (261-312) catalogue every `issue_manager.py`-originated stdout marker (`LEARNING_GATE_BLOCKED`, `IMPLEMENT_FAILED`, etc.); needs a new row/entry for the Phase-1-not-reached marker for consistency with how every other marker is documented [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py:2431` `test_not_ready_verdict_fails_processing` — exercises the exact NOT-READY branch (`issue_manager.py:927-941`) this issue targets but has no `capsys` fixture; update to assert the new stdout marker once that branch emits one [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:4985,4993` `test_implement_current_on_no_routes_to_check_learning_gate` / `test_implement_current_on_error_routes_to_check_learning_gate` (`TestAutodevLoop`) — assert `implement_current.on_no`/`on_error == "check_learning_gate"` directly; must be repointed at the new discriminator state once it's inserted ahead of `check_learning_gate` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:13261` `test_implement_current_routes_to_check_learning_gate_then_auth` (`TestAutodevAuthGuard`) — duplicate copy of the same direct-target assertion; needs the same update [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:13379` `test_autodev_implement_current_failure_chain_clears_inflight` — structural walk that automatically traverses into any state reachable from `implement_current`; will enforce that the new discriminator state clears the `autodev-inflight` sentinel (or routes only to something that does) without needing an edit — verify it still passes, treat as a gap-catcher [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` (~13337-13375) `test_finalize_done_residual_sentinel_not_double_counted` — verify a new not-started classification is excluded from `UNVERIFIED_COUNT`, or the fix reintroduces the exact phantom-misattribution bug this issue reports [Agent 2 finding]
- New: fragment/state-shape test for the new discriminator state, modeled on `test_check_learning_gate_routes_to_auth_check_on_no` (`test_builtin_loops.py`) and the `ll_auto_learning_gate_check` fragment-content assertion (`common.yaml:327-351` pattern) [Agent 3 finding]
- New: `issue_manager.py` marker-print unit test modeled on `test_blocked_gate_prints_greppable_marker` (`test_issue_manager.py:4433-4458`), including the not-my-marker negative-assertion pattern from `test_impl_failed_gate_prints_implement_failed_marker` (`:4488-4513`) [Agent 3 finding]
- New: end-to-end `finalize_done` subprocess test for the new summary.json key, modeled on `test_finalize_done_reports_phantom_when_staged_but_not_closed` (`:4902-4933`) and the count-surfacing pattern `test_finalize_gate_blocked_count_surfaces` (`:3253-3260`) [Agent 3 finding]
- New: companion "defaults to zero when no ledger entries" test modeled on `test_finalize_decision_unresolved_zero_when_no_ledger_entries` (`:3292-3300`) [Agent 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation, in addition to the `autodev.yaml`/`issue_manager.py` changes already scoped above:_

1. Insert the new discriminator state ahead of `check_learning_gate` in `autodev.yaml`; repoint `implement_current.on_no`/`on_error` at it.
2. Add the corresponding stdout marker print in `issue_manager.py`'s NOT-READY branch (lines 927-941), following the `LEARNING_GATE_BLOCKED`/`IMPLEMENT_FAILED` convention.
3. Update `test_issue_manager.py:2431` and the two `test_builtin_loops.py` routing-assertion tests (4985/4993, 13261) to match the new chain; add the new marker/state/finalize tests listed above.
4. Update `docs/guides/LOOPS_REFERENCE.md` and `docs/guides/RECURSIVE_LOOPS_GUIDE.md` to document the new state and marker.
5. Verify `test_autodev_implement_current_failure_chain_clears_inflight` and `test_finalize_done_residual_sentinel_not_double_counted` still pass under the new routing.

## Scope Boundaries

- **In scope**: distinguishing "never reached Phase 2" from "implemented but
  did not close" in `autodev.yaml`'s routing and `summary.json`; re-queue
  instead of a false `phantom`.
- **Out of scope**: fixing the Phase 1 failures themselves (that is
  `little_loops.ready_issue`'s retry and ENH-2988); the `phantom` verdict's
  meaning for runs that genuinely did implement; other loops' summary schemas.

## Impact

Run summaries stop misattributing validation failures to implementation.
Operators reading "implementation did not close" can trust it. Affects every
autodev run that fails in Phase 1.

## Status

open


## Session Log
- `/ll:wire-issue` - 2026-08-02T13:54:24 - `8b8edef1-c39e-4866-83db-7f4d2ee1561d.jsonl`
- `/ll:refine-issue` - 2026-08-02T13:43:45 - `55aa09f8-706d-4a53-9c33-dad9b40b2fa3.jsonl`
