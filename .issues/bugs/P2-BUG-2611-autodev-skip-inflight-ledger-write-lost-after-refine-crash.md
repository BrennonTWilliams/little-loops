---
id: BUG-2611
captured_at: '2026-07-12T03:48:48Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
status: done
confidence_score: 85
outcome_confidence: 52
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 10
score_change_surface: 18
---

# BUG-2611: autodev's skip_inflight ledger write is lost after a refine_current crash

## Summary

When `autodev`'s `refine_current` state (`scripts/little_loops/loops/autodev.yaml`)
crashes on its `refine-to-ready-issue` sub-loop invocation, it routes to
`skip_inflight`, which is supposed to append `"<ID>  refine_failed"` to
`autodev-skipped.txt` before advancing the queue. In a live run against
EPIC-2575 (run dir
`.loops/runs/auto-refine-and-implement-20260711T220542/`), this write never
landed: the issue (ENH-2577) that crashed is completely absent from
`autodev-passed.txt`, `autodev-skipped.txt`, `autodev-gate-blocked.txt`, and
`autodev-decision-unresolved.txt`. It vanished from the run with no ledger
trace at all, even though the queue correctly advanced past it to the next
issue.

## Current Behavior

1. `auto-refine-and-implement --context scope=EPIC-2575` ran `delegate` →
   `autodev` against the resolved issue set `ENH-2577,ENH-2578,FEAT-2576`.
2. `autodev` dequeued `ENH-2577` first (03:05:47Z) and started
   `refine-to-ready-issue`.
3. By 03:08:15Z that sub-loop had already failed and entered its `diagnose`
   state. The diagnostic LLM found the issue's Session Log completely
   untouched — no `refine-issue`/`wire-issue`/confidence-check entries were
   ever appended — meaning the crash happened very early (likely
   `resolve_issue` or `check_lifetime_limit`), before any real refinement
   work started.
4. `refine_current`'s `on_failure`/`on_error` both route to `skip_inflight`
   (autodev.yaml:138-152), which appends `"${captured.input.output}
   refine_failed"` to `${context.run_dir}/autodev-skipped.txt` and clears
   the inflight sentinel, then transitions to `dequeue_next`.
5. The queue did visibly advance — `ENH-2578` was dequeued next at
   03:08:58Z (confirmed via `.loops/.history/2026-07-12T030542-*/events.jsonl`)
   — which can only happen if `dequeue_next` was reached, which can only
   happen via `skip_inflight` (or `on_no`, which doesn't apply since the
   queue wasn't empty).
6. Despite that, the final `autodev-skipped.txt` for this run contains only
   one line: `ENH-2578  low_readiness`. The expected `ENH-2577
   refine_failed` line is missing.
7. `finalize` (auto-refine-and-implement.yaml) computes `SKIPPED_BREAKDOWN`
   and `PARKED_RATE` purely from `autodev-skipped.txt`'s line count, so the
   final `summary.json` for the run undercounts skips by exactly the
   crashed issue: `{"skipped":1,...}` instead of `{"skipped":2,...}`.
   ENH-2577 is invisible to every reporting surface (summary.json,
   `passed`/`not_closed`/`skipped` ledgers, `SKIPPED_BREAKDOWN`) even though
   it was dequeued, attempted, and crashed.

## Expected Behavior

Every issue popped from `autodev-queue.txt` should land in exactly one
terminal ledger (`autodev-passed.txt`, `autodev-skipped.txt`,
`autodev-gate-blocked.txt`, or `autodev-decision-unresolved.txt`) by the
time the run ends — there should be no path where an issue is dequeued,
worked on, and then disappears without a trace. A `refine_current` crash
specifically should reliably produce an `"<ID>  refine_failed"` line in
`autodev-skipped.txt` so `finalize`'s `SKIPPED_BREAKDOWN`/`PARKED_RATE`
accounting stays accurate and operators can see that the issue needs a
re-run rather than assuming it was silently deferred by design.

## Motivation

`SKIPPED_BREAKDOWN` and `PARKED_RATE` in `auto-refine-and-implement`'s
`finalize` state exist specifically so an operator can distinguish a
healthy run (e.g. "2 decomposed") from an unhealthy one without re-reading
`events.jsonl`. If `skip_inflight`'s write can silently disappear, that
visibility signal under-reports real failures — a crash that should read as
"1 refine_failed" instead reads as nothing, and the operator has to
manually diff `autodev-queue.txt`'s original input against every ledger
file (as was done to find this bug) to discover the missing issue.

## Proposed Solution — SUPERSEDED, see Root Cause (Confirmed) below

_Original hypotheses (write-loss inside `skip_inflight`'s shell action) were_
_ruled out by live reproduction on 2026-07-12 — `skip_inflight` never_
_executes at all. Kept below for history; do not use as an implementation_
_guide._

- ~~**File**: `scripts/little_loops/loops/autodev.yaml`, `skip_inflight`
  state (line ~138)~~
- ~~Investigate why the `echo "${captured.input.output}  refine_failed" >>
  ${context.run_dir}/autodev-skipped.txt` append didn't survive to the final
  file.~~ Ruled out: `skip_inflight` is never entered on a `refine_current`
  crash, so there is no append to investigate.
- ~~A race between the epic-branch worktree ... and the run_dir path~~ —
  ruled out; irrelevant once `skip_inflight` isn't reached.
- ~~re-reading the dequeued ID from `autodev-inflight`~~ — irrelevant; the
  fix is a routing-table bug, not a stale-variable bug.

### Root Cause (Confirmed 2026-07-12, via live reproduction)

Reproduced with `ll-loop run autodev "ENH-2577" --context scope=EPIC-2575`
after instrumenting `skip_inflight` to log to an absolute,
worktree-independent debug path. Result: the instrumentation **never
fired** — `events.jsonl` shows the route go directly
`{"from": "refine_current", "to": "dequeue_next"}` with no `skip_inflight`
state-enter event at all. `autodev-skipped.txt` stayed empty and
`autodev-inflight` was never cleared, confirming the write/cleanup are
*skipped*, not lost.

`refine_current` (`autodev.yaml`) declares:
```yaml
on_success: copy_broke_down
on_failure: skip_inflight
on_error: skip_inflight
on_no: dequeue_next
```
`StateConfig.from_dict` (`scripts/little_loops/fsm/schema.py:706`) computes
`on_no = data.get("on_no") or data.get("on_failure")`. Because this state
explicitly sets `on_no: dequeue_next`, that value wins — `on_failure:
skip_inflight` is silently shadowed and has been **dead code** since
`on_no: dequeue_next` was added (comment above it claims `on_no` means
"queue empty / sub-loop never started," a case the delegate-routing
mechanism doesn't actually distinguish).

`_execute_delegate_state` (`executor.py:946-962`) routes any child result
that isn't `terminated_by=="terminal" and final_state=="done"` through
`on_no` when it's not the `error` case specifically — i.e. a crashed
sub-loop reaching its own `failed` terminal (`terminated_by=="terminal"`,
`final_state=="failed"`) is exactly the case that falls into `on_no`, not a
distinct "on_failure" slot. So every `refine_current` crash that reaches a
terminal-but-not-`done` state has always routed to `dequeue_next`,
bypassing `skip_inflight` entirely, ever since the stray `on_no:
dequeue_next` was added to this state.

### Fix

Delete the `on_no: dequeue_next` line from `refine_current` in
`autodev.yaml`. With no explicit `on_no`, the schema's `on_no = ... or
on_failure` fallback resolves `on_no` to `"skip_inflight"` — matching
`on_failure` — so every non-`done` terminal (crash, `max_iterations`,
`timeout`, signal) correctly routes through `skip_inflight` and its ledger
write. No changes needed to `executor.py`, `run_dir` resolution, or the
worktree-delegation path — this is a one-line YAML fix.

Existing test `test_refine_current_on_no_routes_to_dequeue_next`
(`test_builtin_loops.py:2877`) encodes the buggy config as intended
behavior and must be deleted/replaced. All existing `skip_inflight` tests
assert against the raw YAML dict (`data["states"][...]`), never against the
*compiled* schema's `on_no`/`on_failure` merge — that's the coverage gap
that let this ship unnoticed. Add a test that loads the compiled
`FSMConfig`/`StateConfig` (not the raw dict) and asserts
`refine_current.on_no == "skip_inflight"` post-compilation, so a future
stray `on_no:` key on this state fails loudly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Hypothesis "capture-variable staleness" appears ruled out by static
  reading**: `_execute_delegate_state`'s capture merge
  (`scripts/little_loops/fsm/executor.py` ~lines 942-944) stores a crashed
  sub-loop's captures under `self.captured["refine_current"]`, not
  `self.captured["input"]`. `${captured.input.output}` (set by
  `dequeue_next`'s `capture: input`, `autodev.yaml:102`) is a distinct key
  in `autodev`'s own `self.captured` dict and is not touched when
  `refine-to-ready-issue` crashes.
- **Hypothesis "relative `run_dir` reaching `skip_inflight` unresolved"
  also appears ruled out by static reading**: `run_dir` does start as a
  relative path (`scripts/little_loops/cli/loop/run.py` ~176-179:
  `str(loops_dir / "runs" / instance_id) + "/"`), but the *outer*
  `auto-refine-and-implement.delegate` state's `worktree:` attach block
  (`executor.py` lines 869-877) already forces
  `child_fsm.context["run_dir"] = str(Path(...).resolve())` once, at the
  moment `autodev` itself is invoked as the worktree-delegated sub-loop.
  Because `autodev`'s own `FSMExecutor` instance carries this
  now-absolute `run_dir` for the rest of its run, `skip_inflight` (a plain
  state, not a further delegate) reads the already-absolutized value
  directly — no additional resolve is missing at that boundary per the
  code as written.
- `refine_current`'s own delegation to `refine-to-ready-issue` uses
  `context_passthrough: true` with no per-state `worktree:`
  (`autodev.yaml:121-136`), so it takes the `context_passthrough` branch
  (`executor.py` lines 814-821) rather than the `with:`+`worktree:`
  branch. This merge does not re-run `Path.resolve()`, but it is only
  inheriting `autodev`'s own (already-absolute) context, so this is not
  obviously broken either on static reading.
- **Revised recommendation**: since both leading hypotheses in the
  Proposed Solution above appear ruled out by reading
  `scripts/little_loops/fsm/executor.py`, the bug is more likely a
  runtime/timing issue invisible to static analysis — e.g. `skip_inflight`'s
  shell append racing `worktree_utils.cleanup_worktree()`'s teardown of the
  delegated worktree, or output buffering lost mid-write when the worktree
  is removed. Before attempting a code fix, reproduce with
  `ll-loop run autodev "ENH-2577" --context scope=EPIC-2575` and instrument
  `skip_inflight`'s action (e.g. `set -x` plus an explicit `pwd`/`echo
  $context.run_dir` marker) to capture the actual resolved values at the
  moment of failure, rather than continuing from static hypotheses alone.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` state and
  possibly `dequeue_next`'s inflight-sentinel handling
- `scripts/little_loops/fsm/executor.py` — `_execute_delegate_state`'s
  `context_passthrough` branch (~lines 814-821); this is the general
  mechanism `refine_current`'s `context_passthrough: true` relies on, and
  the direct precedent for a fix is the worktree `run_dir` absolutization
  already implemented a few lines away (~869-877, added for ENH-2609) — if
  the root cause is confirmed to be a `run_dir`/cwd divergence, the fix
  likely generalizes that existing absolutization into this branch rather
  than only touching `autodev.yaml`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize`
  state reads `autodev-skipped.txt` for `SKIPPED_BREAKDOWN`/`PARKED_RATE`;
  also the `delegate` state (~line 224, `worktree:
  "${captured.epic_branch.output}"`) is the exact ENH-2609 call site that
  triggers the worktree-absolutization code path in `executor.py`
- Any other loop that calls `loop: autodev` (e.g. `sprint-refine-and-implement`
  if applicable) inherits the same undercounting risk

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py:532-533` — asserts
  `record_decision_unresolved`'s action contains
  `autodev-decision-unresolved.txt`; a sibling ledger state sharing the
  same failure-mode risk once root cause is confirmed

### Similar Patterns
- `mark_gate_blocked` and `record_decision_unresolved` (autodev.yaml) use
  the same "append to run_dir ledger file, then dequeue_next" idiom — worth
  auditing for the same failure mode once root cause is known, since they
  likely share whatever path-resolution issue affects `skip_inflight`
- `recheck_after_size_review` (autodev.yaml ~748-768) shares the exact same
  idiom on both its `on_yes`/`on_no` branches (writes `autodev-passed.txt` /
  `autodev-skipped.txt`)

### Tests
- No existing test covers `refine_current` crashing mid-sub-loop and
  verifying the skip ledger; add one exercising `skip_inflight` under the
  epic-branch/worktree delegation path (ENH-2609) if that turns out to be
  the root cause

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py::TestSubLoopWorktree` (lines
  4872-5009) — closest existing runtime pattern for a new regression test:
  `test_worktree_attach_runs_child_inside_and_detaches` (4917) already
  proves cwd and `${context.run_dir}` can be independently resolved and
  diverge; `test_worktree_cleanup_runs_even_when_child_fails` (4965) proves
  `cleanup_worktree` runs on child failure. Neither chains into a
  *subsequent parent state* (i.e. `skip_inflight`) writing to `run_dir`
  after cleanup — that chained assertion is the actual gap and doesn't
  exist yet anywhere in the suite.
- `scripts/tests/test_worktree_utils.py::TestCleanupWorktree` (lines
  360-536, esp. `test_unlock_called_before_remove` at 464 and
  `test_remove_proceeds_when_unlock_fails` at 493) — establishes the
  unlock-before-remove teardown ordering convention; reusable to simulate
  the suspected cleanup/append race in a new test.
- `scripts/tests/test_builtin_loops.py` lines 3143-3254 (the
  `autodev-inflight` handshake lifecycle tests: init reset, dequeue_next
  write, enqueue_or_skip/enqueue_children clear, done read,
  recheck_after_size_review clear) and lines 4448-4459
  (`SKIPPED_BREAKDOWN` aggregation test asserting the exact `"ID  REASON"`
  two-space-delimited format) — will need review/updating if the fix
  changes `skip_inflight` from reading `${captured.input.output}` to
  reading `${context.run_dir}/autodev-inflight` directly (option (b) in
  Proposed Solution), since several of these tests hardcode the
  `${captured.input.output}` substitution
  (`test_skip_inflight_shell_action_writes_skipped_and_clears_inflight`,
  `test_builtin_loops.py:3713-3739`, is the one most directly affected).
- No integration-level test runs the real `autodev.yaml` end-to-end via
  `FSMExecutor(...).run()` with a crash injected into `refine_current`
  under worktree delegation — all current coverage is either YAML-shape
  assertions or single-state shell-action execution via the `_run_finalize`
  helper pattern. A true repro test would combine that helper's
  action-extraction approach with `TestSubLoopWorktree`'s cwd-divergence
  proof, running `skip_inflight`'s action with `cwd` set to a torn-down
  worktree directory distinct from where `${context.run_dir}` resolves.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (lines 922, 949, 980, 982) — documents
  the `on_failure`/`on_error` → `skip_inflight` → `dequeue_next` routing
  (line 949 references ENH-1679 explicitly); update if the fix changes the
  write timing or routing shape of `skip_inflight`

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_builtin_loops.py` `TestAutodevLoop` (~line 2860+)
  already has narrow unit coverage of `skip_inflight` in isolation —
  `test_refine_current_failure_routes_to_skip_inflight` (2860),
  `test_refine_current_error_routes_to_skip_inflight` (2869),
  `test_skip_inflight_writes_skipped_file` (2898),
  `test_skip_inflight_clears_autodev_inflight` (2906),
  `test_skip_inflight_routes_to_dequeue_next` (2915), and
  `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight`
  (3713). None of these exercise the epic-branch worktree delegation path
  (ENH-2609) — they run `skip_inflight`'s shell action directly against a
  plain `run_dir`, so they can't catch a worktree-cwd/run_dir-resolution
  or teardown-race bug. A new test should follow the `_run_finalize`
  helper shape (`test_builtin_loops.py` ~2111-2186: substitute
  `${context.run_dir}`/`${captured...}` into the raw `action:` string,
  `subprocess.run(["bash", "-c", script], cwd=<dir>, ...)`) but run
  `skip_inflight`'s action with `cwd` set to a worktree directory distinct
  from the directory `${context.run_dir}` resolves to, to reproduce the
  cwd/run_dir mismatch this bug's investigation is chasing.
- Sibling states sharing the exact same "append to run_dir ledger, then
  `dequeue_next`" idiom worth auditing once root cause is known:
  `mark_gate_blocked` (`autodev.yaml` ~489-500, writes
  `autodev-gate-blocked.txt`), `record_decision_unresolved` (~360-372,
  writes `autodev-decision-unresolved.txt`), and
  `recheck_after_size_review` (~748-768, writes `autodev-passed.txt` /
  `autodev-skipped.txt` on its `on_yes`/`on_no` branches). All read
  `${captured.input.output}` and `${context.run_dir}` the same way
  `skip_inflight` does, so they inherit the same risk if the fix isn't
  generalized.
- The existing worktree-aware `run_dir` absolutization fix
  (`scripts/little_loops/fsm/executor.py` lines 869-877, added for
  ENH-2609) is the direct precedent for "resolve run_dir defensively
  across a cwd change" — any code fix for this bug should follow the same
  pattern rather than introducing a new mechanism.

## Impact

- **Priority**: P2 - Silently undercounts failures in the reporting layer
  that `auto-refine-and-implement`'s epic-branch mode (just landed) depends
  on for operator visibility; not data-destructive, but actively misleads
  anyone reading `summary.json` after a run.
- **Effort**: Small - Likely a path-resolution or capture-variable staleness
  fix scoped to one or two states in `autodev.yaml`.
- **Risk**: Low - Fix is isolated to bookkeeping/logging, not the core
  refine/implement control flow.
- **Breaking Change**: No

## Resolution

- **Action**: fix
- **Completed**: 2026-07-12
- **Status**: Completed

### Root Cause

Reproduced live with `ll-loop run autodev "ENH-2577" --context
scope=EPIC-2575` (instrumented `skip_inflight` with a debug log to an
absolute, worktree-independent path). The instrumentation never fired —
`events.jsonl` showed the route go directly `refine_current → dequeue_next`
with no `skip_inflight` state-enter at all, confirming the write/cleanup
were *skipped*, not lost as originally hypothesized.

`refine_current` (`autodev.yaml`) declared both `on_failure: skip_inflight`
and `on_no: dequeue_next`. `StateConfig.from_dict`
(`scripts/little_loops/fsm/schema.py:706`) computes `on_no = data.get("on_no")
or data.get("on_failure")` — the explicit `on_no` won, permanently shadowing
`on_failure`. `_execute_delegate_state` (`executor.py:946-962`) routes any
child result that reaches a terminal-but-not-`"done"` state (i.e. a genuine
crash) through `on_no`, not a separate slot for `on_failure` — so every
`refine_current` crash has always routed straight to `dequeue_next`,
bypassing `skip_inflight`, ever since the stray `on_no: dequeue_next` was
added.

### Changes Made

1. **`scripts/little_loops/loops/autodev.yaml`**: removed `on_no:
   dequeue_next` from `refine_current`. With `on_no` unset, it now falls
   back to `on_failure`'s value (`"skip_inflight"`) per the schema, so
   every failure mode (crash, `max_iterations`, `timeout`, signal) reaches
   the ledger write. Added a comment explaining why `on_no` must not be
   re-added to this state.
2. **`scripts/tests/test_builtin_loops.py`** (`TestAutodevLoop`): replaced
   `test_refine_current_on_no_routes_to_dequeue_next` (which encoded the
   buggy config as intended behavior) with
   `test_refine_current_has_no_explicit_on_no`, and added
   `test_refine_current_compiled_on_no_resolves_to_skip_inflight`, which
   loads the *compiled* `StateConfig` (not just the raw YAML dict — the
   gap that let this ship unnoticed) and asserts `on_no == "skip_inflight"`.

### Verification

- `ll-loop validate autodev` passes.
- `python -m pytest scripts/tests/test_builtin_loops.py -k TestAutodevLoop`
  — 120 passed.
- Live re-run of `ll-loop run autodev "ENH-2577" --context scope=EPIC-2575`
  completed in 33 iterations / 56m without hitting `skip_inflight` (ENH-2577
  decomposed cleanly this time — the original crash trigger was an
  external SIGKILL, which is non-deterministic and didn't recur). The
  routing fix itself is proven deterministically by the compiled-schema
  unit test above rather than depending on reproducing another crash.
- Audited all other `autodev.yaml` states for the same `on_no`+`on_failure`
  collision (`mark_gate_blocked`, `record_decision_unresolved`,
  `recheck_after_size_review`, etc.) — `refine_current` was the only state
  defining both keys together, so this was an isolated instance, not a
  systemic pattern.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 52/100 → LOW

### Concerns
- Root cause is not actually confirmed: both leading hypotheses in "Proposed Solution" (capture-variable staleness, relative `run_dir`) were ruled out by static reading of `executor.py` during the refine pass. The issue itself recommends reproducing with `ll-loop run autodev "ENH-2577" --context scope=EPIC-2575` and instrumenting `skip_inflight` before attempting a code fix — implementation should start with that reproduction step, not a direct patch.

### Outcome Risk Factors
- Ambiguity: the actual failure mechanism (suspected cleanup/teardown race between `worktree_utils.cleanup_worktree()` and the `skip_inflight` shell append) is unconfirmed and may require runtime instrumentation to pin down before a fix shape can be chosen.
- Test coverage: existing `skip_inflight` unit tests (`test_builtin_loops.py` ~2860-3739) exercise the shell action in isolation against a plain `run_dir` and don't cover the epic-branch worktree delegation path (ENH-2609) — the scenario this bug actually occurred in has no regression coverage yet.
- If the fix generalizes the `context_passthrough` branch in `executor.py` (~814-821) rather than only touching `autodev.yaml`, it also affects the sibling ledger states (`mark_gate_blocked`, `record_decision_unresolved`, `recheck_after_size_review`) and any other loop that delegates via `context_passthrough`, widening the effective change surface beyond the two primary files.

## Session Log
- `/ll:confidence-check` - 2026-07-12T00:00:00 - `400f3567-388b-4f60-ae88-68b3cf2dba4f.jsonl`
- `/ll:wire-issue` - 2026-07-12T04:10:50 - `74f3660e-5676-499e-9aa0-c53a1d7036e5.jsonl`
- `/ll:refine-issue` - 2026-07-12T03:56:58 - `acbc127f-2596-4cf5-8cde-40e47b0c0ecf.jsonl`
- `/ll:capture-issue` - 2026-07-12T03:48:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d9db9d7-f5b8-4bb6-a582-c2b7b01b3900.jsonl`
- Root cause reproduced live, fixed, and verified - 2026-07-12T07:15:00

---

**Done** | Created: 2026-07-12 | Priority: P2
