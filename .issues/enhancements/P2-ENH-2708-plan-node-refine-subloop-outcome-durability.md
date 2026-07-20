---
id: ENH-2708
status: done
captured_at: '2026-07-20T19:30:00Z'
completed_at: '2026-07-20T21:24:06Z'
discovered_date: 2026-07-20
discovered_by: capture-issue
decision_needed: false
confidence_score: 96
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# ENH-2708: plan-node-refine sub-loop outcome durability

## Summary

The `plan-node-refine` sub-loop (`scripts/little_loops/loops/oracles/plan-node-refine.yaml`) only persists its decision (`node_outcome_<id>.txt`) from terminal `emit_*` states. If the sub-loop's runner is killed (e.g. parent `rn-refine` timeout) after the LLM has decided but before it reaches a terminal state, the decision is lost even though the work product (e.g. decomposed child plans) was already written to disk.

## Current Behavior

In the `rn-refine-20260720T002123` run (see `rn-refine-audit-2026-07-20T134636.md`), node `n20`'s sub-loop reached `decide_decompose`, got `DECISION: DECOMPOSE` from the LLM, and wrote 5 child sub-plans to `nodes/n20/children/{1..5}.md` and rewrote the parent index at `nodes/n20/plan.md`. The sub-loop then entered `route_decision` (iter 11) but the parent's 6h wall-clock budget expired before `materialize_children` ran, so:

- `node_outcome_n20.txt` was never written
- The parent's `classify_node` state found no outcome file and fell back to `REFINE_FAILED`
- The 5 child plans were never copied to `nodes/n21..n25` or enqueued
- `nodes/n20/children/` was left orphaned in the run dir with fully complete, scored sub-plans

The decision text itself (`decision.output` in the parent's captured state) shows the LLM's `DECOMPOSE` verdict was already final — only the persistence step was lost.

## Expected Behavior

The sub-loop should persist its decision at decision time, not only in terminal `emit_*` states, so a runner kill between decision and materialization is recoverable:

- Write a provisional outcome marker immediately after `decide_decompose`/`decide_leaf` routes (before `materialize_children` runs), so a killed run can distinguish "decided but not materialized" from "never decided."
- Alternatively, pass a `deadline_epoch` into the sub-loop via `with:` so it can check its own remaining budget and short-circuit cleanly (write the outcome, skip materialization gracefully) instead of being killed mid-`route_decision` by the parent's external timeout.

## Motivation

This is the root cause of the lost work in the 2026-07-20 audit, not just a downstream symptom. Even with the run-dir observability fixes (see companion issue), the underlying loss is real: an LLM decision (2m53s of work) and materialized artifacts are silently discarded because there is no durability boundary between "decided" and "persisted." Any future rn-refine run with a similarly timed timeout will lose work the same way, regardless of what summary.json reports about it afterward.

## Proposed Solution

Two candidate approaches (needs `/ll:refine-issue` codebase research before implementation — the audit's own proposed diffs are rough sketches, not verified against the actual FSM structure):

1. **Provisional sentinel at decision time**: after `decide_decompose`/`decide_leaf` routes but before `materialize_children`, write a provisional `node_outcome_<id>.txt` (e.g. `DECOMPOSE_PENDING` or similar) containing enough info for the parent/resume path to recover the decision even if materialization never completes. The audit's proposed diff (writing a bare timestamp sentinel via `.decide_started_${context.node_id}`) does **not** actually persist the decision — it only marks that the prompt started, which doesn't help `classify_node` recover anything. A working fix needs to persist the decision output itself once it's known.
2. **Deadline propagation**: pass `deadline_epoch` (derived from the parent's `context.timeout_total` and elapsed time) into the sub-loop via `with:`, and have `route_decision` (or the state after the decision prompt) check it and short-circuit to a clean emit state instead of being killed by the parent's external process-timeout.

> **Selected:** Deadline propagation — avoids the decision/materialization race entirely by short-circuiting before the vulnerable window, rather than papering over it with a provisional token the existing resume reader can't safely distinguish from "complete."

Requires investigating: how `with:` context propagation works for sub-loop invocation in this FSM engine, and whether `plan-node-refine`'s states have access to `loop.elapsed_ms` equivalent to the parent's.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact durability gap** (`scripts/little_loops/loops/oracles/plan-node-refine.yaml`): the decision and any DECOMPOSE work products (child `.md` files, rewritten `plan.md` index) are written inside the `decide_decompose` prompt action itself (line 196) — *before* `DECISION: DECOMPOSE`/`DECISION: LEAF` is even captured. From there the FSM takes 1–3 more state transitions before any `node_outcome_${context.node_id}.txt` is written: `route_decision` (line 242, `on_yes: gate_decompose` / `on_no: emit_leaf`) → `gate_decompose` (line 251, `on_yes: materialize_children` / `on_no: emit_capped`) → `materialize_children` (line 276, allocates child ids from `node_counter.txt`, appends `edges.tsv`/`depth_map.txt`, prepends to `queue.txt`) → one of the four terminal writers: `emit_decomposed` (line 326), `emit_leaf` (line 338), `emit_capped` (line 349), `refine_failed` (line 357) — each the *only* place `node_outcome_<id>.txt` is written. A kill at any point in that window (confirmed: `route_decision`/`gate_decompose`/`materialize_children` are separate FSM steps, each survivable-by-kill) leaves on-disk decision artifacts with no corresponding outcome token.

**Parent read path** (`scripts/little_loops/loops/rn-refine.yaml`): `refine_node` invokes the sub-loop with `with: {run_dir, node_id, depth, max_depth, max_node_iters, max_nodes}` and routes both `on_success` and `on_failure` to `classify_node` — so a clean "done" terminal and a "failed" terminal are handled identically by the parent; both defer to `classify_node`'s `cat node_outcome_<id>.txt 2>/dev/null || echo "REFINE_FAILED"`. This means a missing outcome file (never written due to mid-flight kill) is indistinguishable from a genuine `refine_failed` terminal — both collapse to the same `REFINE_FAILED` token and the same `record_failure` bookkeeping. Only `refine_node`'s `on_error` (an in-process exception the child executor catches, `terminated_by == "error"`) diverges to `record_node_crash` — a hard/external kill of the sub-loop process never reaches this path at all, since `child_executor.run()` simply never returns.

**FSM engine sub-loop mechanics** (`scripts/little_loops/fsm/executor.py`, `_execute_sub_loop`, ~line 763–950): `with:` values are interpolated in the *parent's* context before merging into `child_fsm.context` — so a parent-computed expression (e.g. arithmetic on `${context.timeout_total}` and `${loop.elapsed_ms}`) is fully resolvable and passable into a sub-loop's `with:` the same way `max_depth`/`max_node_iters`/`max_nodes` already are (rn-refine.yaml `refine_node` state). **No existing loop does this today** — Option 2 (`deadline_epoch` propagation) is structurally supported by `with:` but would be new usage, not a copy of an existing pattern. Confirmed: `${loop.elapsed_ms}` is **not** inherited by the sub-loop — a fresh `FSMExecutor` resets `start_time_ms` at child `run()` start, so the child's own `${loop.elapsed_ms}` reflects only its own wall-clock, not the parent's cumulative elapsed time. The engine does already clamp `child_fsm.timeout` down to the parent's remaining budget when the parent has a `timeout:` set (ENH-1293 Fix 2, `_execute_sub_loop`) — but this clamp only affects the child's own internal timeout enforcement; it is not exposed as a value the child's states can branch on (no `${context.deadline_epoch}` equivalent is injected automatically).

**Closest existing precedent for Option 2** (soft-deadline check inside a state): `rn-refine.yaml`'s `dequeue_next` state (ENH-2707) checks `${loop.elapsed_ms}` against `(context.timeout_total - context.synth_reserve) * 1000` in a plain shell action, widens its `output_contains` evaluator pattern to `"QUEUE_EMPTY|DEADLINE_DRAIN"` rather than adding a new gate state, and parks unprocessed work in a marker file (`undrained.txt`) before emitting the token — the `on_yes`/`on_no` wiring for the pre-existing token is unchanged. This is the idiom to follow for a `plan-node-refine` self-deadline check, but note it only works because `dequeue_next` measures the loop's *own* elapsed time against context vars mirrored from its *own* `timeout:` — `plan-node-refine` would need `deadline_epoch` (or equivalent) explicitly passed in via `with:`, since its own `${loop.elapsed_ms}` starts fresh per sub-loop invocation and knows nothing of the parent's total budget consumed so far.

**Closest existing precedent for Option 1** (provisional marker before terminal state): the "advisory marker, single downstream consumer greps for it" idiom used by `RECOVERY_NEEDED`/`PARTIAL_DRAIN` markers in `rn-refine.yaml`'s `synth_failure_record`/`assemble` states and `oracles/integrate-node.yaml`'s `integrate_error` state — none of these branch FSM routing on the marker's presence, they're read out-of-band by a later prompt/resume state. No existing loop persists an *intermediate decision* (as opposed to a failure/skip marker) before its terminal state, so a "decision sentinel" write would be a new pattern, structurally similar to the existing `node_outcome_<id>.txt` writes but triggered one state earlier (immediately after `decide_decompose`/`route_decision` capture the decision, before `gate_decompose`/`materialize_children` run).

**Engine limitation relevant to both options**: `executor.py`'s graceful-shutdown path (`request_shutdown()`/`_finish_for_shutdown()`) only fires if the Python process running the sub-loop stays alive to observe the shutdown flag between state transitions. A hard/external kill (SIGKILL, or a parent orchestrator force-terminating the process tree on its own timeout) bypasses this entirely — the process stops existing mid-state with no chance to run any in-process cleanup. There is also a narrow existing flush-on-timeout mechanism (BUG-1226, tested in `test_fsm_executor.py::TestTimeoutHandling`) that flushes one pending **shell** state's action before honoring an engine-level timeout — but per `test_loop_timeout_does_not_flush_slash_command_state`, this is explicitly *not* extended to `prompt`/`loop:` states like `decide_decompose`, since those "could take minutes; flushing them would violate the timeout budget." Neither existing mechanism protects against the external-kill scenario this issue describes; a fix must write the marker synchronously as part of a state action that already runs in the vulnerable window (Option 1), or avoid entering the window at all by short-circuiting earlier (Option 2).

**Relevant test scaffolding to model new tests after**:
- `scripts/tests/test_fsm_executor.py::TestSubLoopBudgetClamping` (`test_child_timeout_clamped_to_parent_remaining`, `test_child_timeout_routes_parent_via_on_no`) — shows how to assert on parent routing when a child sub-loop times out/is clamped, using `patch("little_loops.fsm.executor._now_ms", ...)` rather than a real clock.
- `scripts/tests/test_rn_refine.py::TestDequeuePlumbing` (`test_deadline_drain_parks_queue_and_emits_sentinel`, `test_deadline_drain_evaluator_routes_to_build_synth`) — the render/exec/assert-on-disk idiom (construct `InterpolationContext(elapsed_ms=...)` directly, `interpolate()` the raw action string, execute with `_bash()` against a scratch dir, assert stdout tokens + marker file contents) to reuse for a `plan-node-refine` deadline-check test.
- `scripts/tests/test_rn_refine.py::TestResumeReconcile` (BUG-2610) — existing three-way resume logic already reads `node_outcome_<id>.txt` to detect incomplete nodes; any new provisional-marker format must stay compatible with (or extend) this reader.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-20.

**Selected**: Deadline propagation

**Reasoning**: Option 1's provisional sentinel reuses the existing `echo TOKEN > node_outcome_<id>.txt` write idiom cleanly, but the resume readers (`check_resume`/`resume_reconcile` in `rn-refine.yaml`) treat file *presence* — not content — as "complete," so a `DECOMPOSE_PENDING` token would be misread as done on resume and silently drop the staged-but-unmaterialized children (the exact failure mode the issue is trying to fix). Option 2 has direct engine-level precedent (`with:`-propagated shell-computed values, proven by `test_with_interpolation_from_parent_captures`) and a directly transferable idiom in `dequeue_next`'s ENH-2707 soft-deadline check, and it eliminates the race by short-circuiting to a terminal emit state *before* `materialize_children` runs, rather than requiring new consumer-side routing logic to disambiguate a provisional token from a complete one.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Provisional sentinel at decision time | 2/3 | 2/3 | 3/3 | 1/3 | 8/12 |
| Deadline propagation | 2/3 | 2/3 | 3/3 | 2/3 | 9/12 |

**Key evidence**:
- Provisional sentinel: reuses the exact `node_outcome_<id>.txt` write path/format from all four existing terminal writers and the render/exec/assert-on-disk test idiom (`TestResumeReconcile`), but no existing loop persists an in-flight *decision* (only failure/skip facts), and `check_resume`/`resume_reconcile` read file-presence only — a provisional token would need new routing in `route_decomposed`/`route_leaf`/`route_capped` to avoid being mistaken for a completed outcome.
- Deadline propagation: `with:`/`interpolate_dict` and the `dequeue_next` bash-arithmetic-on-interpolated-literals idiom transfer directly, and `TestSubLoopWithBindings` proves shell-computed values already flow into a sub-loop's `with:` block; no loop does cross-loop deadline propagation today, so both a parent-side `deadline_epoch` computation state and a child-side short-circuit state are new, but the approach avoids the resume-ambiguity hazard structurally rather than needing to litigate it in the reader.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml` — add a provisional-outcome write (Option 1) after `decide_decompose`/`route_decision` (line 242), and/or a `deadline_epoch` self-check state (Option 2) before `materialize_children` (line 276); add `deadline_epoch` to the `parameters:` block if Option 2 is chosen.
- `scripts/little_loops/loops/rn-refine.yaml` — if Option 2: compute `deadline_epoch` and add it to `refine_node`'s `with:` block alongside the existing `run_dir`/`node_id`/`depth`/`max_depth`/`max_node_iters`/`max_nodes`; if Option 1: no parent change needed since `classify_node`'s existing `cat node_outcome_<id>.txt` read already picks up whatever token is present.

### Dependent Files (Readers of `node_outcome_<id>.txt`)
- `scripts/little_loops/loops/rn-refine.yaml` — `classify_node` state (reads the file, falls back to `REFINE_FAILED`); `TestResumeReconciliation`'s resume-reconcile path (BUG-2610) also reads it to detect incomplete nodes on restart — any new provisional token value must not collide with `DECOMPOSED`/`REFINED_LEAF`/`REFINED_CAPPED`/`REFINE_FAILED`.

### Similar Patterns
- `scripts/little_loops/loops/rn-refine.yaml:dequeue_next` (ENH-2707 soft-deadline drain) — the closest precedent for Option 2's self-deadline-check-in-shell-action idiom.
- `scripts/little_loops/loops/rn-refine.yaml` (`synth_failure_record`/`assemble`) and `scripts/little_loops/loops/oracles/integrate-node.yaml:integrate_error` — the "advisory marker, read out-of-band" idiom closest to Option 1, though none of them persist an in-flight *decision* today.

### Engine Code (context for either option)
- `scripts/little_loops/fsm/executor.py:_execute_sub_loop` (~line 763–950) — `with:` binding resolution and the existing parent→child timeout clamp (ENH-1293 Fix 2); relevant to Option 2's `deadline_epoch` plumbing.
- `scripts/little_loops/fsm/interpolation.py:InterpolationContext._get_loop_value` (~line 179) — confirms `${loop.elapsed_ms}` is per-executor-instance, not inherited by sub-loops.

### Tests
- `scripts/tests/test_rn_refine.py::TestResumeReconcile` — existing coverage for `node_outcome_<id>.txt` semantics; extend rather than duplicate.
- `scripts/tests/test_rn_refine.py::TestDequeuePlumbing` — test-idiom precedent (render/exec/assert-on-disk via `InterpolationContext(elapsed_ms=...)`) to model a new `plan-node-refine` deadline test after.
- `scripts/tests/test_fsm_executor.py::TestSubLoopBudgetClamping` — precedent for asserting parent-routing behavior when a sub-loop is clamped/times out.
- No existing test simulates a hard/external kill mid-`route_decision`; new coverage will need to construct that scenario directly (e.g. invoke `plan-node-refine` to `decide_decompose`, then assert on partial on-disk state without ever calling a terminal `emit_*` state).

## Scope Boundaries

In scope: `plan-node-refine.yaml`'s decision-persistence path (decide → materialize → emit). Out of scope: the parent `rn-refine` loop's run-dir observability (summary.json/writeback.json — see companion issue) and the deadline-drain queue-truncation issue (separate, not addressed here).

## Impact

- **Priority**: P2 — this is the actual root cause of lost sub-loop work on a real 6-hour run; will recur on any similarly-timed timeout.
- **Effort**: Medium — requires FSM state/routing changes in `plan-node-refine.yaml` plus verification via a real (non-simulated) sub-loop timeout scenario.
- **Risk**: Medium — touches decision routing in a nested sub-loop; must not regress the normal (non-timeout) decompose/leaf path.

## Related Key Documentation

| Document | Relevance |
|---|---|
| .claude/CLAUDE.md | Loop Authoring meta-loop rules (MR-1 through MR-11) apply to any edit of `plan-node-refine.yaml` |

## Resolution

Implemented **Option 2 (deadline propagation)** as selected:

- `rn-refine.yaml`: new `compute_deadline` state (inserted between `read_depth`
  and `refine_node`) converts the run's own remaining wall-clock budget
  (`timeout_total - synth_reserve - elapsed`) into an absolute epoch-seconds
  cutoff, mirroring the ENH-2707 `dequeue_next` budget math. `refine_node`'s
  `with:` block now passes `deadline_epoch` (defaulting to `0` = no deadline
  if the capture is missing) alongside the existing bindings.
- `plan-node-refine.yaml`: new `deadline_epoch` parameter/context default (`0`).
  New `check_decompose_deadline` state is inserted between `route_decision`'s
  `on_yes` and `gate_decompose`: if the deadline has already passed, it routes
  straight to `emit_capped` (reusing the existing capped-leaf terminal) instead
  of running the multi-step `gate_decompose` → `materialize_children` →
  `emit_decomposed` dance, eliminating the state-transition window an external
  kill could land in. If no deadline is set or it's still ahead, routing is
  unchanged.
- Both loops validate clean under `ll-loop validate` (no MR violations).
- New tests: `TestComputeDeadline`, `TestDecomposeDeadline` in
  `scripts/tests/test_rn_refine.py` (render/exec/assert-on-disk idiom, modeled
  after `TestDequeuePlumbing`/`TestGateDecomposeCaps`). Updated
  `TestRecursiveStructure::test_node_oracle_refines_then_decides` for the new
  routing hop. Full suite (`python -m pytest scripts/tests/`) passes: 15597
  passed, 38 skipped.

## Status

- [x] Done

## Session Log
- `/ll:manage-issue` - 2026-07-20T21:23:39Z
- `/ll:ready-issue` - 2026-07-20T21:16:04 - `e80addfb-432d-439e-8615-f2bf9531048b.jsonl`
- `/ll:confidence-check` - 2026-07-20T21:30:00 - `349366d6-bed2-400b-a3bd-bf51b78e4015.jsonl`
- `/ll:decide-issue` - 2026-07-20T21:12:34 - `8f1cc6f6-c800-449a-bd8e-b4933ca33f93.jsonl`
- `/ll:refine-issue` - 2026-07-20T21:07:16 - `bb6f1ea7-e3ef-4d23-b23c-60e4798cf713.jsonl`
- `/ll:capture-issue` - 2026-07-20T19:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e43208e6-cc93-448d-8f8e-8ba33fb2cb7e.jsonl`
