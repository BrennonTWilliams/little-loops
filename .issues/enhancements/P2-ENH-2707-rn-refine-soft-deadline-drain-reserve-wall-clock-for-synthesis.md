---
id: ENH-2707
type: ENH
priority: P2
status: open
captured_at: '2026-07-20T13:48:15Z'
discovered_date: 2026-07-20
discovered_by: capture-issue
relates_to:
- ENH-2565
- BUG-2610
- ENH-2418
confidence_score: 98
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2707: rn-refine — soft-deadline drain: reserve wall-clock for synthesis so a timeout still yields a written-back partial plan

## Summary

A 6-hour `rn-refine` run (`2026-07-20T052123-rn-refine`, sketch-storyboards project) was killed by the loop-level `timeout: 21600` at iteration 123/300 with 18/26 nodes finalized and 7 nodes still queued. Because `build_synth` is reachable only via a `QUEUE_EMPTY` token from `dequeue_next`, the synthesis/write-back phase never ran and the run produced **zero final deliverable** despite ~6 hours of honest, persisted node work (audit: `rn-refine-audit-2026-07-20.md`, verdict `partial`).

Make the refinement walk time-aware: `dequeue_next` should check elapsed wall-clock against a reserved synthesis budget (`synth_reserve` context knob) and, when the soft deadline is reached, stop dequeuing and drain into `build_synth` over whatever nodes are finalized. This fixes two audit findings with one change: the `max_nodes`-vs-`timeout` budget mismatch (rec 2) and the all-or-nothing synthesis cliff (rec 3).

## Current Behavior

- `dequeue_next` (`scripts/little_loops/loops/rn-refine.yaml`, state `dequeue_next`) pops the queue unconditionally until it is empty; `build_synth` fires only on the `QUEUE_EMPTY` token (or `on_error`).
- The FSM engine has no `on_timeout` finalizer hook — `terminated_by: "timeout"` (`fsm/types.py`) simply kills the run, including in-flight sub-loops. There is no state the loop can route through on wall-clock expiry.
- Consequence: any run whose tree is too large for the wall-clock budget forfeits the entire deliverable. 19 nodes consumed the full 6 h; `max_nodes: 40` needs roughly 2×. The contract (`max_depth=3`, `max_node_iters=2`, `max_nodes=40`) cannot mathematically finish inside `timeout: 21600` for plans of this size, and nothing in the loop notices until the kill.
- Recovery today requires a manual `--context resume=1 --context run_dir=<prior>` re-invocation (BUG-2610 walk-resume path) — correct but human-driven; the original run still reports no deliverable.

## Expected Behavior

- `init` stamps a run-start epoch (`$RUN_DIR/start_epoch.txt`).
- `dequeue_next` computes elapsed seconds and compares against `timeout − synth_reserve` (new context var, default sized so synthesis of a ~40-node tree fits — e.g. 3600s, tunable via `--context synth_reserve=N`).
- When the soft deadline is hit and the queue is non-empty, `dequeue_next` emits a distinct `DEADLINE_DRAIN` token, records the undrained queue (e.g. copy `queue.txt` → `undrained.txt`), and routes to `build_synth` exactly like `QUEUE_EMPTY`.
- `build_synth`/`assemble` proceed over the finalized subset — this is already a handled shape: BUG-2610's resume path made synthesis over partially-refined trees legal, and ENH-2565's `RECOVERY_NEEDED` marker + per-node `final.md` snapshots cover degraded assembly.
- The final write-back happens with a visible partial marker (reuse/extend the `RECOVERY_NEEDED` convention, e.g. `PARTIAL_DRAIN` listing undrained node ids), so the user gets an honest, improved-but-incomplete plan **and** can still `--context resume=1` later to finish the drained nodes.

## Motivation

The failure mode is maximally expensive: 6 hours of compute, 174 files of real intermediate work, 18 refined nodes — and the source plan file untouched. The drain converts a total-loss timeout into a partial win at the cost of one shell-arithmetic check per dequeue. Raising `timeout` or lowering `max_nodes` only moves the cliff; the drain removes it. This also makes the loop's implicit contract self-enforcing: the walk adapts to the wall-clock budget instead of silently assuming it is sufficient.

## Proposed Solution

All inside `rn-refine.yaml` — no engine changes:

1. **Context**: add `synth_reserve: 3600` (seconds reserved for bottom-up synthesis + write-back) alongside `max_depth`/`max_nodes`.
2. **`init`**: append `date +%s > "$DIR/start_epoch.txt"` in both fresh-seed and resume branches (resume keeps the original epoch if present? No — stamp fresh on every invocation: the reserve is per-invocation wall-clock, matching the engine's per-run `timeout`).
3. **`dequeue_next`**: before popping, compute
   ```bash
   START=$(cat "$RUN_DIR/start_epoch.txt" 2>/dev/null || date +%s)
   ELAPSED=$(( $(date +%s) - START ))
   BUDGET=$(( ${context.timeout_total:default=21600} - ${context.synth_reserve:default=3600} ))
   if [ -s "$QUEUE" ] && [ "$ELAPSED" -ge "$BUDGET" ]; then
     cp "$QUEUE" "$RUN_DIR/undrained.txt"; : > "$QUEUE"
     echo "DEADLINE_DRAIN"; exit 0
   fi
   ```
   (Beware FSM interpolation rules: engine-side `${context...:default=}` syntax, `$$` only for bash `${VAR}` braces — MR-7/MR-9. The loop-level `timeout` scalar is not interpolatable as `${context.timeout}`; mirror it as a context var or hardcode-with-comment so the two stay in sync.)
4. **Routing**: `evaluate` currently matches `QUEUE_EMPTY` via `output_contains`. Either widen the pattern strategy (emit `QUEUE_EMPTY` for both cases and log `DEADLINE_DRAIN` separately) or add explicit token routing so both tokens reach `build_synth`. Keep `on_no: read_depth` unchanged.
5. **Partial marker**: in `assemble` (or `build_synth` setup), if `undrained.txt` is non-empty, prepend/emit a `PARTIAL_DRAIN` marker naming the undrained node ids next to the existing `RECOVERY_NEEDED` mechanism, and echo the exact `--context resume=1 --context run_dir=...` command in the final output.
6. **Resume compatibility**: verify `check_resume`/`resume_reconcile` (BUG-2610) treat a drained run correctly — undrained nodes were moved out of `queue.txt`, so `resume_reconcile` must re-queue from `undrained.txt` as well (or the drain should append undrained ids back to `queue.txt` *after* synthesis completes, whichever is simpler to keep the three-way routing intact).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — `context` block, `init`, `dequeue_next`, `build_synth`/`assemble`, possibly `resume_reconcile`

### Dependent Files (Callers/Importers)
- Loops that delegate to `rn-refine` (grep `loop: rn-refine` / `loop: oracles/plan-node-refine` callers) — behavior additive, no contract change expected

_Wiring pass added by `/ll:wire-issue`:_
- **Correction**: no loop YAML actually delegates *into* `rn-refine` — grep across `scripts/little_loops/loops/**/*.yaml` found zero `loop: rn-refine` / `loop: oracles/plan-node-refine` callers; `rn-refine` is a top-level `ll-loop run rn-refine <plan_file>` entry point only, and it is the one that delegates *out* to `oracles/plan-node-refine` (line 243) and spawns `oracles/integrate-node` workers (line 471, `synth_dispatch`). The "callers" bullet above has no concrete target — nothing to wire on that axis. [Agent 1 finding]

### Similar Patterns
- ENH-2565 `RECOVERY_NEEDED` marker + `resume_build_synth` reconcile-from-disk pattern
- BUG-2610 three-way `check_resume` routing (`RESUME_WALK`/`RESUME_SYNTH`/`FRESH`)

### Tests
- `scripts/tests/test_builtin_loops.py::TestRnRefine` — add fixture assertions: `synth_reserve` context default exists; `dequeue_next` action contains the deadline check; drain token routes to `build_synth`; existing `QUEUE_EMPTY` routing unchanged; MR-7/MR-9 escape lint passes (`ll-loop validate rn-refine`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_refine.py::TestDequeuePlumbing.test_empty_queue_emits_sentinel` (lines 427-434) — existing test asserting `"QUEUE_EMPTY" in result.stdout` from `dequeue_next`'s action; extend or add a sibling test asserting `"DEADLINE_DRAIN" in result.stdout` when elapsed exceeds `timeout_total - synth_reserve`, following the same `_render`/`_bash` pattern. [Agent 3 finding]
- `scripts/tests/test_rn_refine.py::TestRecursiveStructure.test_empty_queue_routes_to_synthesis` (lines 94-97) — asserts `fsm.states["dequeue_next"].on_yes == "build_synth"` structurally; verify this still holds (or gets a companion assertion) once the `DEADLINE_DRAIN` token is wired in — the answer depends on whether the drain widens the existing `QUEUE_EMPTY` evaluator pattern (keeps `on_yes` unchanged) or adds a chained gate (introduces a new intermediate state, per the `check_resume`/`route_resume_synth` precedent). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestRnRefineRecursiveDecomposition.test_empty_queue_routes_to_bottom_up_synthesis` (~lines 9399-9400) — the raw-YAML-dict twin of the above structural assertion (`data["states"]["dequeue_next"]["on_yes"] == "build_synth"`); same update-or-unaffected question applies. [Agent 2 + 3 finding]
- `scripts/tests/test_rn_refine.py::TestResumeRouting` (lines 584-655) — new test needed: seed `visited.txt`/outcome files as "fully walked" (the existing setup that currently produces `RESUME_SYNTH`, see `test_check_resume_emits_resume_synth_when_tree_fully_walked`, lines 617-628) plus a non-empty `undrained.txt`, and assert `"RESUME_WALK" in result.stdout` instead — proving step 6's `check_resume` fix. No existing test touches `undrained.txt` (zero grep hits before this change). [Agent 3 finding]
- `scripts/tests/test_rn_refine.py::TestLoadsClean.test_rn_refine_validates_without_errors` (lines 55-61) is the only backstop that would catch a new MR-7/MR-9 escape bug in the new shell blocks — no rn-refine-specific MR-7/MR-9 test exists, so this generic `load_and_validate` gate is load-bearing, not supplementary. [Agent 3 finding]

### Documentation
- `docs/reference/LOOPS.md` (or wherever rn-refine's context vars are documented) — document `synth_reserve`

_Wiring pass added by `/ll:wire-issue`:_
- **Correction**: the actual file is `docs/guides/LOOPS_REFERENCE.md`, not `docs/reference/LOOPS.md` (which does not exist). Three concrete edits: the context-variable table (lines 305-315, currently lists `plan_file`/`max_depth`/`max_node_iters`/`max_nodes`/`synth_workers`/`resume`/`run_dir` with no `synth_reserve`/`timeout_total` row); the FSM flow diagram (line 342, `dequeue_next (shell: pop a node id; empty queue → build_synth)` — asserts single-token routing, needs the `DEADLINE_DRAIN` path added); the "Resume (ENH-2565, BUG-2610)" notes bullet (line 389, describes `check_resume` reconciling `visited.txt`/`queue.txt`/`node_outcome_<id>.txt` with no mention of `undrained.txt` — will misdescribe resume behavior once step 6 lands). [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — table row (line 61, ends "...bounded by max_depth/max_nodes", no wall-clock dimension) and the `rn-refine` prose block (lines 116-159, same `check_resume`/`resume_reconcile` staleness as above). [Agent 2 finding]
- `CHANGELOG.md` — every prior rn-refine enhancement (BUG-2610, ENH-2565, ENH-2418, ENH-1957, ENH-1613) got a one-line entry under its concrete release section (never `[Unreleased]`, per project convention); this change should follow the same pattern. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale test reference**: `scripts/tests/test_builtin_loops.py::TestRnRefine` does not exist. The class there is `TestRnRefineRecursiveDecomposition`; the dedicated, fixture-style test file for this loop is `scripts/tests/test_rn_refine.py` (constant `RN_REFINE = LOOPS / "rn-refine.yaml"` at line 29). Point new tests here instead.
- **`test_rn_refine.py` test idiom to follow** (closest existing precedent, `TestSynthFailureRecord`, lines 283-311): loads the state action via `_load_rn_refine().states["dequeue_next"].action`, renders it with `_render(action, context=..., captured=...)` (wraps `InterpolationContext` + `interpolate()`), executes with `_bash(rendered, tmp_path)` against a scratch `run_dir`, then asserts on-disk side effects (e.g. `undrained.txt` contents, `plan-rubric.md` marker text) and `result.returncode == 0`. A pure string-containment check on `.action` (no execution) is also used elsewhere, e.g. `test_synth_dispatch_background_spawns_integrate_worker` (lines 121-127) — useful for a quick "action contains the deadline guard" assertion without executing bash.
- **`${context.timeout_total}` does not exist today and won't resolve** — confirmed via `fsm/interpolation.py` (`_get_loop_value`, lines 179-200) and `fsm/schema.py` (`LoopConfig.timeout` at line 1104, no `context.timeout` alias). The loop's `timeout: 21600` (rn-refine.yaml:35) is a top-level `LoopConfig` field, never surfaced into the `context` or `loop` interpolation namespaces — only `${loop.elapsed_ms}` / `${loop.elapsed}` / `${loop.started_at}` are exposed (`fsm/interpolation.py:179-200`). The step 3 pseudocode's `${context.timeout_total:default=21600}` reference must be a real context var declared in `rn-refine.yaml`'s `context:` block (e.g. `timeout_total: 21600`), not a read-through to the engine's own `timeout:` key — the two will silently drift unless a comment ties them together, exactly as the issue's own caveat at the end of step 3 anticipates. Confirmed no other loop YAML exposes/mirrors its own `timeout:` into `context:` either — no existing precedent to copy for keeping them in sync beyond a comment.
- **`${loop.elapsed_ms}` already gives live elapsed wall-clock — `start_epoch.txt` may be unnecessary**: `InterpolationContext` is constructed with `elapsed_ms=_now_ms() - self.start_time_ms + self.elapsed_offset_ms` (`fsm/executor.py:2146`), the exact same formula the engine's own timeout check uses (`fsm/executor.py:489-510`). This value is already available to a shell action as `${loop.elapsed_ms}` with no new file needed. `start_epoch.txt` would only be required if the deadline check must survive resume-with-a-fresh-process (`elapsed_ms` already accounts for `elapsed_offset_ms` from prior segments on `PersistentExecutor` resume — `fsm/executor.py:222`) — worth confirming during implementation whether `${loop.elapsed_ms}` alone is sufficient before adding the extra `start_epoch.txt` stamping/read machinery in `init`/`dequeue_next`.
- **Routing precedent for a 3rd token from `dequeue_next`**: this exact "one shell action emits 3 possible tokens, gates are binary `on_yes`/`on_no` so they must chain" shape already exists twice in this file — `check_resume` → `route_resume_synth` (tokens `RESUME_WALK`/`RESUME_SYNTH`/`FRESH`) and `route_decomposed` → `route_leaf` → `route_capped` (tokens `DECOMPOSED`/`REFINED_LEAF`/`REFINED_CAPPED`/fallthrough). Adding `DEADLINE_DRAIN` as a third `dequeue_next` outcome should follow the same idiom: `dequeue_next`'s existing `evaluate: {output_contains, pattern: "QUEUE_EMPTY"}` stays as `on_no: read_depth`, and a new chained gate (or a widened `QUEUE_EMPTY` emission per the issue's own step 4 note) routes `DEADLINE_DRAIN` to `build_synth` alongside `QUEUE_EMPTY`.
- **`RECOVERY_NEEDED` marker mechanics (exact precedent for `PARTIAL_DRAIN`)**: written by plain `echo "RECOVERY_NEEDED: <reason>" >> "$RUN_DIR/plan-rubric.md"` in two states — `synth_failure_record` (rn-refine.yaml:503-520) and `assemble` (rn-refine.yaml:522-538). It is **advisory only** — no state branches on its presence; both call sites fall through to `next:`/`on_error` unconditionally. The sole consumer is the `report` state's `action_type: prompt` text (rn-refine.yaml:683-723), which instructs the agent to grep `plan-rubric.md` for the literal string and "surface it prominently." `PARTIAL_DRAIN` should reuse this exact contract: append to `plan-rubric.md` (not a new file), and extend the `report` prompt's Step 1 instructions to also check for `PARTIAL_DRAIN` and echo the resume command.
- **`resume_reconcile` will NOT pick up `undrained.txt` nodes as currently written** — a more specific version of the issue's own step 6 concern. `resume_reconcile` (rn-refine.yaml, BUG-2610) only walks `visited.txt` for ids missing a `node_outcome_<id>.txt` file and re-prepends those to `queue.txt`; nodes moved to `undrained.txt` by the drain were **never dequeued**, so they never entered `visited.txt` and `resume_reconcile` has no path to them. Worse, `check_resume`'s `RESUME_WALK` vs `RESUME_SYNTH` decision reads `queue.txt` non-empty as its `RESUME_WALK` signal (rn-refine.yaml `check_resume`) — since the drain empties `queue.txt` into `undrained.txt`, a resumed run would see empty `queue.txt` + all visited nodes having outcome files, and misroute to `RESUME_SYNTH` (or worse, `FRESH`-like), silently dropping the undrained nodes entirely rather than re-walking them. `check_resume`'s queue-emptiness check must also inspect `undrained.txt` (or the drain must merge `undrained.txt` back into `queue.txt` before/at resume, whichever proves simpler) to keep the three-way routing correct.

### Configuration
- N/A (context var only)

## Implementation Steps

1. Add `synth_reserve` context var + mirror of the loop timeout; stamp `start_epoch.txt` in `init`.
2. Add the elapsed-vs-budget guard at the top of `dequeue_next` with `undrained.txt` capture.
3. Wire drain token routing into `build_synth`; add the `PARTIAL_DRAIN` marker + resume-hint echo in assembly.
4. Reconcile with BUG-2610 resume paths (undrained nodes must be re-queueable) — specifically, fix `check_resume`'s queue-emptiness check to also treat a non-empty `undrained.txt` as a `RESUME_WALK` signal (see Codebase Research Findings under Integration Map for why `resume_reconcile` alone won't catch drained nodes).
5. `ll-loop validate rn-refine`; add tests to `scripts/tests/test_rn_refine.py` (not `test_builtin_loops.py` — see Integration Map findings) following the `TestSynthFailureRecord` render/exec/assert-on-disk pattern; run `python -m pytest scripts/tests/test_rn_refine.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update/extend `TestDequeuePlumbing.test_empty_queue_emits_sentinel` and `TestRecursiveStructure.test_empty_queue_routes_to_synthesis` in `test_rn_refine.py`, and `TestRnRefineRecursiveDecomposition.test_empty_queue_routes_to_bottom_up_synthesis` in `test_builtin_loops.py` — confirm whether the `on_yes`/`data["states"]["dequeue_next"]["on_yes"]` structural assertions stay `"build_synth"` or need a companion check for the `DEADLINE_DRAIN` path, depending on the widened-pattern vs. chained-gate implementation choice.
7. Add a new test in `TestResumeRouting` (`test_rn_refine.py`) proving `check_resume` emits `RESUME_WALK` when `undrained.txt` is non-empty even though `visited.txt`/outcome files look "fully walked."
8. Update `docs/guides/LOOPS_REFERENCE.md` — context-var table (~lines 305-315), FSM flow diagram (~line 342), and the "Resume (ENH-2565, BUG-2610)" notes bullet (~line 389).
9. Update `scripts/little_loops/loops/README.md` — `rn-refine` table row (~line 61) and prose block (~lines 116-159).
10. Add a `CHANGELOG.md` entry under the next concrete release section (not `[Unreleased]`), following the existing one-line-per-rn-refine-enhancement convention.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Before adding `start_epoch.txt` stamping in `init` (step 1), verify whether `${loop.elapsed_ms}` (already live-computed and interpolation-accessible, `fsm/interpolation.py:179-200`) is sufficient on its own — it uses the same formula as the engine's own timeout check and already accounts for resume via `elapsed_offset_ms`. If sufficient, step 1 simplifies to just adding the `timeout_total`/`synth_reserve` context vars, with no new on-disk epoch file.
- `timeout: 21600` (rn-refine.yaml:35) has no interpolation path (`${context.timeout}` and `${loop.timeout}` both raise `InterpolationError`) — the mirrored context var is required, not optional; confirm no other loop already solves this drift problem to copy from (none found in this codebase).

## Impact

- **Reliability**: converts total-loss wall-clock timeouts into honest partial deliverables with a resume path.
- **Cost**: one `date +%s` subtraction per dequeue — negligible.
- **Risk**: interpolation-escape mistakes in the new shell block (MR-7/MR-9) — covered by `ll-loop validate` + fixture tests; drain/resume interaction is the main design-care point.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Meta-loop shape rules and MR lint taxonomy governing the YAML edits |
| `docs/ARCHITECTURE.md` | FSM engine termination semantics (`terminated_by`) |

## Session Log
- `/ll:confidence-check` - 2026-07-20T15:30:00 - `ba45d779-8d1f-4023-a4d9-5fd667b3504e.jsonl`
- `/ll:wire-issue` - 2026-07-20T14:58:33 - `06f4f6d4-77e8-4a4a-a17d-53d936c6e3b7.jsonl`
- `/ll:refine-issue` - 2026-07-20T14:45:35 - `f962c371-dc2c-48a9-a32e-41d648ea4b67.jsonl`
- `/ll:capture-issue` - 2026-07-20T13:48:15Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/059234da-1924-4b21-8ae8-692af47cef3f.jsonl`

---

## Status

**Status**: open
**Created**: 2026-07-20
