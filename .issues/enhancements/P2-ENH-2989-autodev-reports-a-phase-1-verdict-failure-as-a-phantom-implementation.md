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
confidence_score: 98
outcome_confidence: 86
score_complexity: 20
score_test_coverage: 24
score_ambiguity: 20
score_change_surface: 22
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
`phantom` — rather than recorded as a failed implementation. This covers the
**whole** never-started population, not just the NOT-READY branch that prompted
the report: every `process_issue_inplace` early return that precedes Phase 2's
`run_with_continuation` call, plus the pre-Phase-1 confidence gate. See
_Resolved design decisions_ #5 for the enumeration and the reason tokens.

Crucially, the issue must **stop being counted as `phantom` at all**, not merely
gain a second classification alongside it (see the staged-ledger hazard under
_Resolved design decisions_ #4).

Retry behaviour splits on the reason token, because the populations have
opposite retry semantics:

- `unknown` — a non-compliant model turn that failed to parse. **Transient**;
  re-queued for one further attempt, then classified terminally.
- Everything else (`not_ready`, `blocked`, `close_failed`, `path_mismatch`,
  `confidence_gate`) — a real judgment or a structural fault. **Deterministic**;
  never re-queued, since a second identical pass produces the same outcome.

The distinction should be legible in both the run summary and `summary.json`.

## Program Design

`ll-auto`'s output already carries the signal. This run's `ll_auto_last.txt`
contains `ready-issue verdict: UNKNOWN`, `is NOT READY for implementation`, and
`Issues processed: 0` — any of which distinguishes the case from a real Phase 2
failure. ~~The cheapest correct discriminator is probably a dedicated exit code
from `ll-auto`, so the FSM branches on a number rather than pattern-matching
prose that is free to change.~~ **Refuted by codebase research** (see below): the
established convention is a stdout marker consumed by an `output_contains`
fragment, not an exit code. No distinct exit-code space exists, and adding one
would make this the only discriminator in `autodev.yaml` shaped differently from
`check_learning_gate` / `check_impl_auth`.

### Signatures

```yaml
# scripts/little_loops/loops/autodev.yaml — new state, mirroring check_impl_auth,
# inserted ahead of check_learning_gate.
check_impl_reached:
  fragment: ll_auto_not_started_check   # new, in loops/lib/common.yaml
  on_yes: mark_not_started
  on_no: check_learning_gate
  on_error: check_learning_gate         # degrade, never crash (BUG-2594 shape)
```

```python
# scripts/little_loops/issue_manager.py — emitted at EVERY Phase-1 early return
# (see decision #5 for the enumeration). The fact is already in
# IssueProcessingResult.failure_reason; what is missing is the greppable stdout
# marker every other autodev discriminator has.
print(f"PHASE1_NOT_STARTED {info.issue_id} {reason}", flush=True)
```

The marker carries a normalized reason token as a third field so
`mark_not_started` can split transient (`unknown`) from deterministic
(everything else) without a second probe. The token is a fixed vocabulary, not
the raw verdict string — `UNKNOWN` maps to `unknown`, but `NOT_READY` and
`NEEDS_REVIEW` both map to `not_ready`, and the non-verdict branches contribute
`blocked` / `close_failed` / `path_mismatch` / `confidence_gate`.

### Call Path

`implement_current` (`scripts/little_loops/loops/autodev.yaml`) shells out to
`ll-auto` and evaluates on `exit_code`. On non-zero it routes
`check_learning_gate` (pattern `GATE_BLOCKED`) → `check_impl_auth` (pattern
`AUTH_FAILED`) → `clear_inflight_after_impl_failure` → `dequeue_next` →
`finalize_done`. The new state inserts ahead of `check_learning_gate`, matching
the two existing probes' shape exactly.

The signal originates in `process_issue_inplace`
(`scripts/little_loops/issue_manager.py`, roughly `:700-1050`), whose Phase 1
branches all return a `_stamped_result(success=False, ...)` before Phase 2's
`run_with_continuation` is ever called — that early-return set is precisely the
"never reached implementation" population.

> **Line anchors below are symbol-anchored, not line-anchored.** The original
> refine pass recorded `issue_manager.py` offsets that have since drifted by
> ~36 lines (the NOT-READY branch is now `:963-977`, not `927-941`;
> `LEARNING_GATE_BLOCKED` is `:1028`; `IMPLEMENT_FAILED` is `:1046`). Locate
> each site by its `failure_reason` string rather than by line number.

`finalize_done` is where the summary key is written; it currently emits
`verdict` / `closed` / `not_closed` / `skipped` / `gate_blocked` /
`decision_unresolved` / `inflight_unresolved` / `abandoned`.

### Resolved design decisions

_These were open questions at capture; each is now decided. Do not re-litigate
during implementation — the rationale is recorded here._

**1. Discriminator shape → stdout marker, not an exit code.** Settled by the
codebase-research finding below: `check_learning_gate` and `check_impl_auth`, the
only two analogues, are both `output_contains` fragments greppping
`${context.run_dir}/ll_auto_last.txt` for a literal marker emitted by a
`print(..., flush=True)` in `issue_manager.py`. `AutoManager.run()`
(`issue_manager.py`, `AutoManager.run()`) returns `1` uniformly, so an exit code
would require carving out a new code space for one caller. Marker:
`PHASE1_NOT_STARTED {issue_id} {reason}`.

**2. Summary key → `not_started`,** a standalone one-reason-per-file ledger
(`${context.run_dir}/autodev-not-started.txt`), matching
`autodev-gate-blocked.txt` / `autodev-decision-unresolved.txt`. It must be
zero-initialised in `init` alongside the others (`autodev.yaml:63-68`).
Deterministic verdicts do **not** get their own key — they append to the existing
shared ledger as `autodev-skipped.txt  not_ready`, reusing the trailing-reason
shape (`:207`, `:348`, `:419`) rather than widening the summary schema.

**3. Re-queue → bounded, only for `unknown`, and prepended to the queue head.**
Unconditional re-queue is unsafe: `dequeue_next` pops the head back into the
**full** refine → wire → confidence → implement pipeline, so a deterministic
Phase 1 rejection re-queues, re-refines and fails identically, forever, at one
full LLM refinement cycle per attempt. Three consequences for implementation:

- Only `unknown` is re-queued (transient parse failure). Every other reason
  token is terminal on first sight.
- **The existing `autodev-repair-cycle-count.txt` counter cannot be reused as
  the bound** — `dequeue_next` resets it to `0`, so a re-queued issue clears its
  own counter on the way back in. The bound needs a per-issue tally that
  survives dequeue: a run-dir file of `ID count` lines (e.g.
  `autodev-not-started-attempts.txt`), read-modify-written by `mark_not_started`.
  Default bound: **1 re-queue**; on exhaustion the issue falls through to the
  same terminal classification as a deterministic verdict.
- **Prepend to the head, not append to the tail** (decided; do not re-litigate).
  Tail-append was considered and rejected on three grounds. (a) *Dependent
  issues lose their turn.* `check_blockers_at_dequeue` (ENH-2909, `:238-348`)
  already prevents a cascade of failed implementations — a dependent issue is
  ledgered `blocked_by_unmet` and skipped, not failed — but with tail-append the
  order becomes A fails → B dequeued → B skipped as blocked → A retried → A
  succeeds, with B already gone from the queue and skipped for the rest of the
  run. Prepending retries A while B is still queued, so B sees the resolved
  blocker. (b) *Wall-clock spacing buys nothing.*
  `run_ready_issue_with_retry` has already exhausted its in-process `UNKNOWN`
  retries before this branch is reached; the autodev-level re-queue is a coarser
  retry that runs a fresh refine → wire → confidence cycle first, mutating the
  issue file. The intervening work is the variance source, not elapsed time —
  and spacing via other queue items is arbitrary anyway (seconds in a 2-issue
  queue, an hour in a 20-issue one). (c) *Tail-append can silently drop the
  retry.* `autodev-not-started-attempts.txt` is run-dir scoped, so the bound is
  per-run; if the loop hits `max_iterations` or a context handoff before the
  queue drains back to A, the retry never happens and A ends the run sitting
  mid-queue with the inflight sentinel already overwritten — neither retried nor
  cleanly ledgered. Starvation is not a counter-risk: the bound of 1 caps a
  single issue at one extra cycle.

**4. The fix must remove the ID from `autodev-staged.txt` — every occurrence.**
This is the step that actually fixes the reported bug, and it is easy to miss.
Staging happens *before* implementation is attempted, at **five** sites
(`autodev.yaml:496`, `:670`, `:1126`, `:1637`, `:1849` — note `:670`, which the
original capture missed); `finalize_done` (`~:2054-2072`) then walks
`STAGED_IDS` and appends every non-`done` one to `autodev-unverified.txt`, which
is what produces `phantom`. Adding a `not_started` ledger **alone leaves the
`phantom` verdict intact** and double-counts the issue in two ledgers.
`mark_not_started` must therefore also filter the ID out of
`autodev-staged.txt` (or `finalize_done` must subtract not-started IDs from
`STAGED_IDS` before the promotion walk). Prefer the former: it keeps the
subtraction next to the state that knows why, and leaves `finalize_done`'s
counting logic untouched.

Removal must strip **all** matching lines (`grep -vxF "$ID"` rewriting the whole
file), not delete a single line: multiple staging sites can fire for one issue,
and a re-queued issue re-stages on its second pass. `finalize_done`'s `sort -u`
(`~:2059-2060`) dedups for *counting* only — it does not help here, because
removal is a different operation from counting.

**5. The marker covers every Phase-1 early return, with a reason token.**
Instrumenting only the NOT-READY branch would leave the rest of the same
population still misreported as `phantom`, contradicting Expected Behavior.
Every site below returns `_stamped_result(success=False, ...)` before Phase 2's
`run_with_continuation`; each emits `PHASE1_NOT_STARTED {issue_id} {reason}`
immediately before its return. Locate them by `failure_reason` string — the
line numbers drift.

| `failure_reason` | Reason token | Retry |
|---|---|---|
| `below_readiness_threshold (...)` (pre-Phase-1 confidence gate) | `confidence_gate` | terminal |
| `Fallback failed after path mismatch` | `path_mismatch` | terminal |
| `Path mismatch persisted after fallback` | `path_mismatch` | terminal |
| `Invalid reference: ...` | `close_failed` | terminal |
| `CLOSE without validated file path` | `close_failed` | terminal |
| `CLOSE failed: ...` | `close_failed` | terminal |
| `BLOCKED: {concerns}` | `blocked` | terminal |
| `NOT READY: {verdict} - N concern(s)`, verdict `UNKNOWN` | `unknown` | **re-queue once** |
| `NOT READY: {verdict} - N concern(s)`, verdict `NOT_READY` / `NEEDS_REVIEW` | `not_ready` | terminal |

The learning-gate branches (`LEARNING_GATE_BLOCKED`, `IMPLEMENT_FAILED`) are
**excluded** — they occur after Phase 2 has been reached or already have their
own routing, and `check_learning_gate` must keep winning for them. This is why
`check_impl_reached` is inserted *ahead* of `check_learning_gate` but must not
match those markers.

The `confidence_gate` row deserves a note: `CONFIDENCE_GATE_BLOCKED`
(`issue_manager.py:745`, added by commit `2f056733`) is a *pre*-Phase-1 refusal
that today has **no** `autodev.yaml` consumer, so it takes the identical route to
`phantom`. In autodev it is narrow — `check_passed` runs `ll-issues
check-readiness --readiness ${context.readiness_threshold}`, seeded from the same
`commands.confidence_gate.readiness_threshold` the `ll-auto` gate reads, so the
two normally agree — but it is reachable when a run overrides the threshold via
`--context readiness_threshold=NN`, or when the score changes between
`check_passed` and `implement_current`. Folding it in costs one alternation in
the new fragment's grep; leaving it out would strand a third consumer-less
marker. Emit `PHASE1_NOT_STARTED {issue_id} confidence_gate` alongside the
existing `CONFIDENCE_GATE_BLOCKED` print rather than replacing it — other
consumers may rely on the original marker.

Note that `little_loops.ready_issue`'s retry-on-`UNKNOWN` makes the `unknown`
case rarer, but does not eliminate it: a retry that also whiffs, or any other
Phase 1 terminal verdict, still lands here.

### Adjacent gap (noted, out of scope)

`IMPLEMENT_FAILED` (`issue_manager.py:1046`) is printed but consumed by **no**
`autodev.yaml` fragment — the same class of defect as this issue, on a different
branch. With `CONFIDENCE_GATE_BLOCKED` (`:745`) this makes **two** orphaned
markers, which promotes "audit every `issue_manager.py` marker for a consumer"
from a footnote to real work. This issue scopes in `CONFIDENCE_GATE_BLOCKED`
(decision #5) because it shares the phantom misattribution; `IMPLEMENT_FAILED`
stays out. Follow-up worth capturing separately: a test asserting every
`print(f"..._BLOCKED/_FAILED {id}")` marker in `issue_manager.py` has at least
one `loops/**/*.yaml` grep consumer, which closes the class permanently.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact routing chain** (`scripts/little_loops/loops/autodev.yaml`):
- `implement_current` (lines 796-837): `fragment: shell_exit`, `capture: ll_auto_output`; `on_yes: dequeue_next`, `on_no: check_learning_gate`, `on_error: check_learning_gate`.
- `check_learning_gate` (lines 839-851): `fragment: ll_auto_learning_gate_check` (`loops/lib/common.yaml:327-351`); greps `ll_auto_last.txt` for `LEARNING_GATE_BLOCKED`; `on_yes: mark_gate_blocked`, `on_no: check_impl_auth`, `on_error: check_impl_auth`.
- `check_impl_auth` (lines 877-884): `fragment: ll_auto_auth_check` (`loops/lib/common.yaml:304-325`); greps for `401|403|unauthorized|forbidden|...`; `on_yes: abort_env_not_ready`, `on_no: clear_inflight_after_impl_failure`, `on_error: clear_inflight_after_impl_failure`.
- `clear_inflight_after_impl_failure` (lines 886-896): removes the `autodev-inflight` sentinel, `next: dequeue_next` — it does not append the ID to any reason-coded ledger, so the ID's only ledger entry remains the earlier `autodev-staged.txt` write from `check_passed`.
- `finalize_done` (lines 1967-2122): promotes `autodev-staged.txt` IDs into `autodev-passed.txt` only if `ll-issues show --json` reports `status` in `done|completed|cancelled` (1978-1990); otherwise appends to `autodev-unverified.txt` (1988). Verdict logic (2090-2103): `PASSED_COUNT>0 && UNVERIFIED_COUNT==0 && ABANDONED==0 → success`; `PASSED_COUNT>0 → partial`; `UNVERIFIED_COUNT>0 || ABANDONED>0 → phantom`; else `no-op`. A single-issue run that fails at Phase 1 has `PASSED_COUNT=0, UNVERIFIED_COUNT=1` → `phantom`.

**All Phase 1 early-return branches** in `process_issue_inplace()`
(`scripts/little_loops/issue_manager.py`), each setting
`IssueProcessingResult.success=False` before Phase 2's `run_with_continuation()`.
Line anchors below were re-verified against the tree as of 2026-08-02 (the
original refine pass's numbers had drifted ~36 lines); prefer the
`failure_reason` string as the locator.

| Anchor | Condition | `failure_reason` | Stdout marker |
|---|---|---|---|
| ~736-754 | pre-Phase-1 readiness gate (commit `2f056733`) | "below_readiness_threshold (...)" | `CONFIDENCE_GATE_BLOCKED {issue_id}` (`:745`) — **not checked by any `autodev.yaml` fragment today**; scoped in by decision #5 |
| ~845-850 | fallback ready-issue retry failed | "Fallback failed after path mismatch" | none |
| ~862-870 | fallback retry still mismatched | "Path mismatch persisted after fallback" | none |
| ~899-906 | `CLOSE` + `invalid_ref` | "Invalid reference: ..." | none |
| ~914-921 | `CLOSE`, no validated path | "CLOSE without validated file path" | none |
| ~940-947 | `CLOSE`, `close_issue()` failed | "CLOSE failed: ..." | none |
| ~947-961 | `BLOCKED` verdict (`was_blocked=True`, `:956`) | "BLOCKED: {concerns}" | none |
| ~963-977 | `is_ready=False` (covers `NOT_READY`, `NEEDS_REVIEW`, and `UNKNOWN`) | "NOT READY: {verdict} - {N} concern(s)" | **none** — this is the originally-reported ENH-2989 case |
| ~1029-1035 | learning gate `"blocked"` | "Learning gate blocked: ..." | `LEARNING_GATE_BLOCKED {issue_id}` (`:1028`) — out of scope, keeps its own routing |
| ~1047-1053 | learning gate `"impl_failed"` | "Learning gate: implementation failed" | `IMPLEMENT_FAILED {issue_id}` (`:1046`) — not checked by any `autodev.yaml` fragment today; out of scope |

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
- New: **staged-ledger removal test** — the AC-1 regression guard. Synthetic `run_dir` with the ID in both `autodev-staged.txt` and `autodev-not-started.txt`; assert `finalize_done` emits a non-`phantom` verdict and `not_closed: 0`. Without this, the fix can ship while the reported bug persists.
- New: **duplicate-staging removal test** — `autodev-staged.txt` seeded with the same ID on two lines (reachable via the five staging sites and via a re-queued second pass); assert `mark_not_started` leaves **zero** occurrences. Guards the `grep -vxF` whole-file rewrite against a single-line-delete implementation.
- New: **re-queue bound tests** for `mark_not_started`, end-to-end subprocess shape against a synthetic `run_dir`: (a) reason `unknown` with attempts `0` puts the ID at the **head** (`head -1`) of `autodev-queue.txt` ahead of any pre-existing entries, and writes attempts `1`; (b) `unknown` with attempts `1` does **not** re-queue and appends `"$ID  unknown"` to `autodev-skipped.txt`; (c) each terminal reason token (`not_ready`, `blocked`, `close_failed`, `path_mismatch`, `confidence_gate`) never re-queues regardless of attempt count.
- New: fragment-content assertion for `ll_auto_not_started_check` in `loops/lib/common.yaml` — greps `ll_auto_last.txt`, not a `capture:` interpolation (BUG-2594 guard, mirroring the existing `ll_auto_learning_gate_check` assertion).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation, in addition to the `autodev.yaml`/`issue_manager.py` changes already scoped above:_

1. Add the `PHASE1_NOT_STARTED {issue_id} {reason}` stdout marker at **every** Phase-1 early return enumerated in decision #5 (including the pre-Phase-1 confidence gate at `:745`, where it is emitted *alongside* the existing `CONFIDENCE_GATE_BLOCKED` print, not in place of it), following the `LEARNING_GATE_BLOCKED`/`IMPLEMENT_FAILED` convention.
2. Add the `ll_auto_not_started_check` fragment to `loops/lib/common.yaml`, modelled on `ll_auto_learning_gate_check` (`:327-351`) — grep `${context.run_dir}/ll_auto_last.txt` for `PHASE1_NOT_STARTED`, never the FSM `capture:` value (BUG-2594). It must **not** match `LEARNING_GATE_BLOCKED` or `IMPLEMENT_FAILED`, which keep their existing routing.
3. Insert `check_impl_reached` ahead of `check_learning_gate` in `autodev.yaml`; repoint `implement_current.on_no`/`on_error` at it. Ordering matters for the same reason `check_learning_gate` precedes `check_impl_auth` (`common.yaml:338-341`).
4. Add `mark_not_started`, modelled on `mark_gate_blocked` (`:852-875`). It must: (a) append to `autodev-not-started.txt`; (b) **remove every occurrence of the ID from `autodev-staged.txt`** via `grep -vxF` whole-file rewrite (decision #4 — without this the `phantom` verdict survives); (c) `rm -f autodev-inflight` per the BUG-1226 convention; (d) parse the reason token from the marker line, and on `unknown` with attempts remaining, **prepend** the ID onto the head of `autodev-queue.txt` and bump `autodev-not-started-attempts.txt` (decision #3 — head, not tail); (e) otherwise append `"$ID  <reason>"` to `autodev-skipped.txt`. `next: dequeue_next`, `on_error: dequeue_next`.
5. Zero-initialise `autodev-not-started.txt` and `autodev-not-started-attempts.txt` in `init` alongside the sibling ledgers (`autodev.yaml:63-68`).
6. Surface `not_started` in `finalize_done`'s `printf`-emitted `summary.json` object (`:2105-2107`), counted from the new ledger like `GATE_BLOCKED_IDS` (`:2015`).
7. Update `test_issue_manager.py:2431` and the two `test_builtin_loops.py` routing-assertion tests (4985/4993, 13261) to match the new chain; add the new marker/state/finalize tests listed above, including one marker-emission test per reason token in decision #5's table.
8. Update `docs/guides/LOOPS_REFERENCE.md` and `docs/guides/RECURSIVE_LOOPS_GUIDE.md` to document the new state and marker.
9. Verify `test_autodev_implement_current_failure_chain_clears_inflight` and `test_finalize_done_residual_sentinel_not_double_counted` still pass under the new routing.

## Scope Boundaries

- **In scope**: distinguishing "never reached Phase 2" from "implemented but
  did not close" in `autodev.yaml`'s routing and `summary.json`; re-queue
  instead of a false `phantom`.
- **Out of scope**: fixing the Phase 1 failures themselves (that is
  `little_loops.ready_issue`'s retry and ENH-2988); the `phantom` verdict's
  meaning for runs that genuinely did implement; other loops' summary schemas;
  wiring a consumer for the orphaned `IMPLEMENT_FAILED` marker; the
  marker/consumer audit test proposed under _Adjacent gap_.
- **Out of scope but carries the same bug**:
  `auto-refine-and-implement.yaml`'s `finalize` state independently
  reimplements the staged → unverified → `phantom` logic, so a Phase 1
  rejection misreports there too. Not fixed here — capture separately rather
  than widening this issue.

## Acceptance Criteria

1. **The phantom misattribution is gone, not merely annotated.** For a
   single-issue run whose only failure is a Phase 1 rejection, `summary.json`
   reports `"verdict"` ≠ `"phantom"` and `"not_closed": 0` — the ID appears in
   `autodev-not-started.txt` and **not** in `autodev-unverified.txt`. (This is
   the AC that fails if decision #4's staged-ledger removal is skipped.)
2. `summary.json` carries a `not_started` count, defaulting to `0` when the
   ledger is empty or absent.
3. Every Phase-1 early return in decision #5's table prints
   `PHASE1_NOT_STARTED {issue_id} {reason}` to stdout with the reason token that
   table assigns, and prints neither `LEARNING_GATE_BLOCKED` nor
   `IMPLEMENT_FAILED` (not-my-marker negative assertion, per
   `test_impl_failed_gate_prints_implement_failed_marker`). The confidence-gate
   site additionally still prints `CONFIDENCE_GATE_BLOCKED`. Conversely, the two
   learning-gate branches do **not** print `PHASE1_NOT_STARTED`, and
   `check_learning_gate` still wins for them.
4. `implement_current.on_no` and `.on_error` both target `check_impl_reached`,
   which falls through to `check_learning_gate` on `on_no` and `on_error`.
5. An `unknown` reason re-queues the ID **to the head of
   `autodev-queue.txt`** at most once, so the retried issue is the next one
   dequeued; a second `unknown` on the same ID in the same run is terminal.
   Every other reason token is never re-queued.
6. `mark_not_started` clears the `autodev-inflight` sentinel on every path,
   satisfying the structural walk in
   `test_autodev_implement_current_failure_chain_clears_inflight` without that
   test needing an edit.
7. `python -m pytest scripts/tests/` exits 0, and `ll-loop validate` passes for
   `autodev.yaml`.

## Impact

Run summaries stop misattributing validation failures to implementation.
Operators reading "implementation did not close" can trust it. Affects every
autodev run that fails in Phase 1.

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-08-02T16:42:49 - `6cac52a1-bb84-4f01-9a95-1cb4926b4e41.jsonl`
- `/ll:wire-issue` - 2026-08-02T13:54:24 - `8b8edef1-c39e-4866-83db-7f4d2ee1561d.jsonl`
- `/ll:refine-issue` - 2026-08-02T13:43:45 - `55aa09f8-706d-4a53-9c33-dad9b40b2fa3.jsonl`

## Related Key Documentation

- `docs/ARCHITECTURE.md` — documents Sequential Mode (`ll-auto`) internals; this issue's fix distinguishes a Phase 1 rejection from a Phase 2 implementation failure inside that exact flow.
- `docs/reference/API.md` — covers the `fsm/*` executor/evaluator modules and `Loops` reference this issue's new `autodev.yaml` discriminator state and `issue_manager.py` marker convention extend.
