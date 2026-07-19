---
id: ENH-2691
title: rn-refine synth_dispatch computes worker fail flag but never gates on it
type: ENH
priority: P3
status: done
captured_at: '2026-07-19T00:00:00Z'
completed_at: '2026-07-19T18:57:08Z'
discovered_date: 2026-07-19
discovered_by: audit-loop-run
labels:
- loops
- rn-refine
- verdict-laundering
confidence_score: 98
outcome_confidence: 81
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2691: rn-refine synth_dispatch computes worker fail flag but never gates on it

## Summary

`synth_dispatch` in `loops/rn-refine.yaml` launches N `oracles/integrate-node`
workers in parallel, waits on all of them, and computes `FAIL=1` if any
worker's exit code was non-zero — but the state has no `evaluate`/`on_yes`/
`on_no`, only an unconditional `next: assemble`. The `fail=` value is embedded
in the logged output string (`SYNTH_WORKERS_DONE workers=$WORKERS fail=$FAIL`)
but never inspected by the FSM, so a crashed integration worker is currently
indistinguishable from a clean run at the control-flow level.

## Evidence

Found during audit of run `2026-07-19T161520-rn-refine`
(`.loops/.history/2026-07-19T161520-rn-refine/`). In that run
`fail=0` (both workers succeeded), so the gap did not manifest — but the
`synth_dispatch` state definition has no path that reacts to `fail=1`. If a
worker crashes, `assemble` falls back silently to
`nodes/n0/plan.md` with a `RECOVERY_NEEDED` note appended to
`plan-rubric.md`, framing it as an incomplete-integration case rather than a
worker failure — the two are different problems (a legitimate integration
step that never ran vs. a step that crashed) and currently get the same
downstream handling.

## Proposed Solution

Add an `evaluate: {type: output_contains, pattern: "fail=0"}` to
`synth_dispatch` and route `on_no` to a distinct state that records which
node(s) failed to integrate (e.g. via `worker-logs/worker-*.log`) before
falling through to `assemble`, so the eventual `RECOVERY_NEEDED` note (or a new
marker) can distinguish "worker crashed" from "integration simply didn't
finish."

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

1. Design the new `synth_dispatch` gate so the pre-existing
   `NO_INTERNAL_NODES` empty-queue short-circuit (`rn-refine.yaml:459`,
   which never prints `fail=$FAIL`) does not get misrouted to `on_no` —
   see the empty-queue design note under Files to Modify above.
2. Update `scripts/tests/test_rn_refine.py::test_synthesis_chain_present`
   and `scripts/tests/test_builtin_loops.py::test_has_bottom_up_synthesis_chain`
   for the new `on_yes`/`on_no` routing (both currently assert unconditional
   `next == "assemble"`).
3. Add a new failure-gate test in `test_rn_refine.py` (fake `ll-loop`
   binary that `exit 1`s, seeded `failed_integrations/log.txt`) asserting
   the `on_no` state surfaces the failed node id(s).
4. Update `docs/guides/LOOPS_REFERENCE.md`'s state-flow diagram and
   `docs/guides/RECURSIVE_LOOPS_GUIDE.md`'s parallel-integration prose to
   describe the new branch.
5. Add a new dated `CHANGELOG.md` entry for the fail-gate addition.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Path correction**: `synth_dispatch`/`assemble` live at
  `scripts/little_loops/loops/rn-refine.yaml:437-497` (top-level `loops/`
  no longer exists — package data moved under `scripts/little_loops/`).
- **`fail=$FAIL` alone will miss the exact failure mode described in the
  Evidence section.** `oracles/integrate-node.yaml` (the worker
  `synth_dispatch` spawns) has a *single* terminal state, `done` (line
  156-157), and no `failed` terminal. Per the executor's exit-code
  convention (`scripts/little_loops/cli/loop/_helpers.py:1802-1806`, "a
  terminal state whose name is not `done` represents failure"), when a
  worker's `integrate` prompt errors on one node, `integrate_error`
  (`oracles/integrate-node.yaml:141-154`) logs the failing node id to
  `$RUN_DIR/failed_integrations/log.txt`, then routes back to `pop` and
  keeps draining the rest of the queue — the worker still reaches `done`
  normally. **That means the `ll-loop run oracles/integrate-node` process
  exits 0 even when a node failed to integrate**, so `wait "$p" ||
  FAIL=1` only catches a whole-process crash (infra error, uncaught
  exception, exceeding `max_steps`/`timeout`) — not the per-node
  integration failure this issue's Evidence describes. `FAIL=1` and "a
  node landed in `failed_integrations/log.txt`" are two independent
  signals; gating only on `fail=0` leaves the per-node case exactly as
  invisible as before.
- **A ready-made per-node failure record already exists**: every worker
  writes to the SAME shared `$RUN_DIR/failed_integrations/log.txt` (one
  node id per line, `oracles/integrate-node.yaml:150-151`), append-only
  and flock-free (each worker only appends its own failed node id, so
  concurrent appends across workers are safe on POSIX). `synth_dispatch`'s
  `on_no` state (or a state unconditionally inserted before `assemble`)
  should check `[ -s "$RUN_DIR/failed_integrations/log.txt" ]` instead of
  (or in addition to) `fail=0`, and surface its contents in the
  `RECOVERY_NEEDED` note so the note can name which node(s) crashed rather
  than just flagging that *something* didn't finish.
- **`assemble`'s existing fallback (`rn-refine.yaml:481-497`) already
  covers the "popped-but-not-integrated" case** for the root node
  specifically (missing `nodes/n0/final.md` → copy `plan.md`, append
  `RECOVERY_NEEDED`). It has no visibility into non-root node failures
  recorded in `failed_integrations/log.txt` — those currently surface only
  as "root's descendant chain never got a final.md," with no indication
  of *which* node or *why*.

## Acceptance Criteria

- [x] A worker failure in `synth_dispatch` is distinguishable in the run
      artifacts from a clean pass.
- [x] `on_no` path does not silently discard which node(s) failed.
- [x] Existing clean-pass behavior (`fail=0` → `assemble`) is unchanged.

## Impact

- **Priority**: P3 — did not manifest in the audited run and integration
  worker crashes are likely rare, but the failure mode is currently invisible
  when it does occur.
- **Effort**: Small — one state's `evaluate`/`on_yes`/`on_no` plus a small new
  recording state in `loops/rn-refine.yaml`.

## Related Files

- `scripts/little_loops/loops/rn-refine.yaml` (`synth_dispatch`, `assemble`)
- `scripts/little_loops/loops/oracles/integrate-node.yaml` (`integrate_error`
  writes `$RUN_DIR/failed_integrations/log.txt`; sole terminal state is
  `done`, so a per-node integration failure does not make the worker process
  exit non-zero)
- `scripts/little_loops/cli/loop/_helpers.py:1802-1806` (exit-code/terminal-state
  convention referenced above)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/oracles/integrate-node.yaml` (worker
  `synth_dispatch` background-spawns via `ll-loop run oracles/integrate-node`,
  line 466) — uses `python3 -m little_loops.rn_synth_queue try-pop`/
  `mark-complete` to drain the shared queue; `rn_synth_queue.py`'s
  `try_pop_ready()`/`mark_complete()` are the only other code path that
  touches this synthesis flow [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — enforces the "terminal state
  named anything but `done` is failure" exit-code convention that is the
  root cause of the gap (a per-node `integrate_error` doesn't change the
  worker's own terminal state, so its process still exits 0) [Agent 1
  finding]

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_ no plugin/manifest registration or
config-schema changes are needed — `output_contains` is already a
registered evaluator type and `on_yes`/`on_no` routing is generic FSM
plumbing (`scripts/little_loops/fsm/validation.py:68`,
`scripts/little_loops/fsm/schema.py:538-539`,
`scripts/little_loops/fsm/fsm-loop-schema.json:769`) — confirmed by Agent 2,
no code change required there. **Design note from Agent 2**: the existing
`NO_INTERNAL_NODES` empty-queue short-circuit (`rn-refine.yaml:459`) exits
before the `SYNTH_WORKERS_DONE ... fail=$FAIL` line is ever printed, so a
naive `output_contains: {pattern: "fail=0"}` evaluator would see no match
(not a literal `fail=0`) on that branch and could misroute it to `on_no`.
The new evaluate/on_no design must account for this pre-existing early-exit
path.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:359-365` — ASCII state-flow diagram shows
  `synth_dispatch → assemble` as an unbranched arrow; needs a branch
  annotation for the new `on_no` failure path [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:124` — describes `synth_dispatch`'s
  parallel-worker behavior with no mention of failure handling; extend once
  fail-gating exists [Agent 2 finding]
- `CHANGELOG.md` — needs a new dated entry (not an edit to the existing
  ENH-2565 entry at lines 384-394) documenting the fail-gate addition, per
  this repo's no-`[Unreleased]` convention [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_refine.py::test_synthesis_chain_present` (~line
  99-115) — asserts `fsm.states["synth_dispatch"].next == "assemble"` and
  `.on_error == "assemble"`; will break once `evaluate`/`on_yes`/`on_no`
  replace the unconditional `next` — update to assert `on_yes == "assemble"`
  (clean-pass, satisfies AC #3) and `on_no == <new recording state>`
  [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestRnRefineRecursiveDecomposition
  .test_has_bottom_up_synthesis_chain` (~line 9402-9413) — same breakage on
  the raw-dict side (`data["states"]["synth_dispatch"]["next"]`) [Agent 3
  finding]
- `scripts/tests/test_rn_refine.py::test_synth_dispatch_empty_queue_short_circuits`
  (~line 128-141) — exercises the `NO_INTERNAL_NODES` early exit; must keep
  passing without tripping the new fail-gate (see the empty-queue design
  note above) [Agent 2 + 3 finding]
- New: a `TestSynthDispatchFailureGate`-style test in `test_rn_refine.py`,
  following the fake-`ll-loop`-binary-on-`PATH` pattern from
  `test_synth_dispatch_spawns_clamped_workers_concurrently` (~line 143-177)
  but with the fake binary `exit 1` and a seeded
  `$RUN_DIR/failed_integrations/log.txt`, asserting the new `on_no` state's
  output surfaces the failed node id(s) — no existing test exercises a
  non-zero-exit worker today [Agent 3 finding]
- No test currently exercises `oracles/integrate-node.yaml`'s
  `integrate_error` state at the action-body (`_bash`-executed) level, or
  asserts on `failed_integrations/log.txt` contents — worth adding
  alongside the new `synth_dispatch` test if practical [Agent 3 finding]

---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-19
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/rn-refine.yaml`: `synth_dispatch` now ORs a
  whole-worker crash with a non-empty `failed_integrations/log.txt` into a
  single `SYNTH_DISPATCH_RESULT=OK|FAILED` marker (including on the
  `NO_INTERNAL_NODES` early exit, so that branch isn't misrouted), gated with
  `evaluate`/`on_yes: assemble`/`on_no: synth_failure_record`. New state
  `synth_failure_record` appends a `RECOVERY_NEEDED` line naming the failed
  node id(s) (or a generic crash note) to `plan-rubric.md` before falling
  through to `assemble`.
- `scripts/tests/test_rn_refine.py`: updated `test_synthesis_chain_present`
  for the new `on_yes`/`on_no` routing; added
  `test_synth_dispatch_result_ok_on_clean_pass`,
  `test_synth_dispatch_result_ok_on_empty_queue`,
  `test_synth_dispatch_result_failed_on_worker_crash`,
  `test_synth_dispatch_result_failed_on_per_node_integration_failure`, and a
  new `TestSynthFailureRecord` class.
- `scripts/tests/test_builtin_loops.py`: updated
  `test_has_bottom_up_synthesis_chain` for the new routing.
- `docs/guides/LOOPS_REFERENCE.md`, `docs/guides/RECURSIVE_LOOPS_GUIDE.md`:
  documented the new failure-gate branch.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 15498 passed, 38 skipped)
- Lint: PASS (`ruff check` on changed Python files)
- Types: PASS (`python -m mypy scripts/little_loops/`)
- Loop validation: PASS (`ll-loop validate rn-refine`)
- Integration: PASS — no new duplication; reuses the existing `output_contains`
  evaluator type and `on_yes`/`on_no` FSM plumbing, consistent with
  `preflight_check`'s established pattern in the same file.

## Status

**Done** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-07-19T18:45:18 - `370326aa-ddac-4b55-9460-0050bd8abf11.jsonl`
- `/ll:refine-issue` - 2026-07-19T18:39:20 - `2d4151a2-6a83-4d6a-b02f-8912b4033020.jsonl`
- `/ll:manage-issue` - 2026-07-19T18:56:21Z - `6edc5165-125c-404a-b405-00cf3ebe5e13.jsonl`
