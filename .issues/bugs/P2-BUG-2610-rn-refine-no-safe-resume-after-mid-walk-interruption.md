---
id: BUG-2610
status: open
captured_at: '2026-07-12T02:55:44Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to:
- ENH-2565
- ENH-2418
confidence_score: 94
outcome_confidence: 78
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 16
score_change_surface: 22
---

# BUG-2610: rn-refine has no safe resume path after a mid-walk interruption

## Summary

The built-in `rn-refine` loop (`scripts/little_loops/loops/rn-refine.yaml`) cannot safely resume a run that was killed during the *refinement walk* (dequeue → refine_node loop). The ENH-2565 resume support only handles one scenario — "tree fully refined, integration phase interrupted" — and routes every resume invocation straight to `resume_build_synth`. A run killed mid-walk has two options, both wrong:

1. **`--context resume=1 --context run_dir=<old>`**: skips the dequeue/refine loop entirely and rolls up never-refined nodes (skeleton-only content) and the in-flight node's stale pre-synthesis content as if finished — a **phantom-complete** reassembly with no error signal.
2. **No resume flag, `run_dir` pointed at the old dir**: `init`'s fresh-seed branch unconditionally re-seeds (`cp plan_file $DIR/plan.md`, `echo "n0" > queue.txt`, `mkdir -p nodes/n0`) — **destroying all completed node work**.

Observed on run `rn-refine-20260711T173608`, stopped via `ll-loop stop` at ~4h / 121 of 300 max_steps: 18/24 discovered nodes complete, node n19 in-flight (research.md written, synthesize SIGKILL'd before writing plan.md), nodes n5/n20–n23 never dequeued. Neither resume path could continue; manual per-node replay was required.

## Current Behavior

`check_resume` branches only on `resume` being set + `nodes/` existing, emitting a two-way token (`RESUME_MODE` → `resume_build_synth`, `FRESH` → `dequeue_next` via init's fresh-seed). There is no path that says "queue.txt is non-empty / some visited nodes have no outcome — keep walking."

## Expected Behavior

- A resume against a partially-walked tree continues the refinement walk from durable on-disk state, re-processing the in-flight node, before ever reaching synthesis.
- Pointing `run_dir` at a populated prior run dir without the resume flag refuses to re-seed (error with a "pass `--context resume=1`" hint) instead of destroying the tree.

## Root Cause

`rn-refine.yaml` states `init` (fresh-seed branch) and `check_resume`. ENH-2565's resume was scoped to the integration phase; the walk phase writes durable completion markers (`node_outcome_<id>.txt`, `queue.txt`, `visited.txt`) but nothing reconciles against them on resume.

Note the in-flight node is *not* in `queue.txt` (already popped), so a queue-nonempty check alone is insufficient — the completion marker is `node_outcome_<id>.txt`, and any node in `visited.txt` lacking one must be re-queued.

## Proposed Solution

Three-way routing in `check_resume`, mirroring `resume_build_synth`'s reconcile-against-on-disk-markers pattern:

- **`RESUME_WALK`** — any node in `visited.txt` lacks `node_outcome_<id>.txt`, OR `queue.txt` is non-empty → new `resume_reconcile` state that prepends incomplete visited nodes back onto `queue.txt`, then routes to `dequeue_next`.
- **`RESUME_SYNTH`** — every visited node has an outcome file and queue is empty → existing `resume_build_synth` behavior.
- **`FRESH`** — no resume flag / no prior tree → unchanged.

**Re-queue order for `resume_reconcile`**: walk `visited.txt` in file order (append order = discovery/dequeue order) and collect every entry lacking a `node_outcome_<id>.txt`. Prepend that filtered list onto the *front* of `queue.txt`, preserving `visited.txt`'s relative order among them (do not re-sort by depth or id). This matches `dequeue_next`'s existing FIFO-pop-of-head/prepend-on-decompose contract: the earliest-visited incomplete node (the true in-flight node at kill time, e.g. `n19`) is processed before later-visited-but-still-incomplete nodes, and both come before any node that was already sitting in `queue.txt` and never dequeued (e.g. `n5`, `n20`–`n23`), since those are appended after the reconciled prefix, not before it.

Plus a guard in `init`: `nodes/` exists under `$DIR` but `resume` is empty → exit 1 with a hint message instead of re-seeding (routes to `diagnose` via `on_error`).

**Idempotency caveat (to verify during implementation)**: a re-queued in-flight node re-enters `oracles/plan-node-refine` with partial artifacts on disk (e.g. a finished `research.md`, `iter-*` dirs). Confirm the sub-loop is idempotent under those — redoing work is acceptable; skipping work is not. If the sub-loop is not idempotent as-is, scope a minimal guard (e.g. detect and reuse a completed `research.md` before re-running that step) rather than a broader rewrite.

**Test-file touch point**: `scripts/tests/test_builtin_loops.py` (search `class TestRnRefine`, ~line 8155) already asserts the current two-way contract at line ~8210 (`check_resume.on_yes == resume_build_synth`, `on_no == dequeue_next`). That assertion must be updated for the three-way split (`RESUME_WALK` → `resume_reconcile` → `dequeue_next`; `RESUME_SYNTH` → `resume_build_synth`; `FRESH` → `dequeue_next`) in addition to adding the new fixture-based routing test called for in Acceptance Criteria.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml`
  - `init` (lines 55-106) — fresh-seed guard is `if [ -n "$RESUME" ] && [ -d "$DIR/nodes" ]` (line 73); needs the `nodes/`-exists-but-`resume`-unset refusal branch.
  - `check_resume` (lines 108-126) — `output_contains "RESUME_MODE"` two-way gate (`on_yes: resume_build_synth` line 124, `on_no: dequeue_next` line 125); needs a third `RESUME_WALK` branch. Since `evaluate.type: output_contains` only supports `on_yes`/`on_no`, follow the in-file precedent at `route_decomposed`/`route_leaf`/`route_capped` (lines 191-216) — a chain of `output_contains` gates — to express the 3-way split, rather than inventing a new evaluator type.
  - `dequeue_next` (lines 128-154) — only writer of `visited.txt` (line 144); writes it *before* refinement completes, which is why an in-flight node shows up in `visited.txt` with no matching outcome file.
  - `classify_node` (line 186) — reads `${run_dir}/node_outcome_${node_id}.txt`, defaulting to `REFINE_FAILED` if absent (lines 185-187) — the exact completion-marker contract `resume_reconcile` must check against.
  - `resume_build_synth` (lines 306-364) — existing reconcile-against-on-disk-markers pattern (filters `edges.tsv`-derived internal nodes by missing `final.md`, writes `synth_queue.txt`) to mirror structurally for the new `resume_reconcile` state.
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml`
  - `setup` (lines 79-98) — idempotency contract for re-entering a partially-refined node: preserves existing `plan.md`/`research.md` (guarded `[ -f ... ] || : > ...`, lines 90/92) but unconditionally resets `.node_iter` to `0` (line 93) and `rm -rf`s `children/` (line 94) on every entry. Confirm during implementation whether resetting `.node_iter` on a re-queued in-flight node is acceptable (issue's stated idempotency caveat) or needs a completed-step-detection guard.
  - `materialize_children` (lines 276-321) — mutates the *global* `queue.txt`/`edges.tsv`/`depth_map.txt`/`node_counter.txt` per child inside a shell loop with no atomicity guarantee if killed mid-loop; the reconcile logic must tolerate a node whose decomposition was only partially committed here.

### Dependent Files (Queue-Prepend Idiom to Reuse)
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml:310-313` (`materialize_children`) — canonical depth-first prepend-to-`queue.txt` shell idiom: `{ for c in $CHILD_IDS; do echo "$c"; done; echo "$EXISTING"; } | grep -v '^[[:space:]]*$' > queue.txt`. `resume_reconcile` should reuse this exact shape with `PENDING` (visited-but-outcome-less nodes) in place of `$CHILD_IDS`.
- `scripts/little_loops/loops/rn-decompose.yaml:191-196` — near-identical prepend idiom (second precedent for the same shape).

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml:57-77` (`init`) — closest existing precedent for an init-time resume guard, though it's currently a *permissive* short-circuit (skip re-seed when `resume` is set and `queue.txt` is non-empty), not the *hard refusal* (exit 1 + hint) BUG-2610's `init` guard needs — inverse-direction logic, same location shape.
- `scripts/little_loops/loops/rn-build.yaml:49-86` (`init`) — alternate `RESUME_MODE:$RESUME_EPIC` token-based resume-knob precedent.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — several passages describe the current two-way `resume` contract and will go stale under the 3-way split:
  - Line 198 (`rn-refine` catalog row) — "Resumable mid-integration via `--context resume=1`" implies resume only covers the integration/synth phase.
  - Line 303 (`resume` context-var table row) — "`init` skips re-seeding and `check_resume` routes straight into bottom-up synthesis" describes exactly the two-way behavior being replaced.
  - Line 323 (loop-shape diagram comment) — `→ check_resume (shell: resume knob + existing nodes/ → resume_build_synth; ...)` needs a third arrow for `resume_reconcile` → `dequeue_next`.
  - Line 338 (`resume_build_synth` section header) — should be qualified as one of two resume paths once `resume_reconcile` exists.
  - Line 362 (Resume (ENH-2565) prose) — "a run interrupted mid-integration... is resumable without redoing refinement" needs a companion sentence for walk-phase resume.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:109-140` — the runnable `--context resume=1` example and surrounding prose currently imply resume always means "reuse existing `nodes/*/final.md` and skip refinement"; needs updating to note resume can re-enter the walk phase.
- `scripts/little_loops/loops/README.md:61` — `rn-refine` catalog entry doesn't currently mention resume semantics, so lower-priority, but verify it stays accurate once a second resume path exists.

### Tests
- `scripts/tests/test_builtin_loops.py` — `class TestRnRefineRecursiveDecomposition` (line ~8154), `test_resume_routes_into_synthesis` (lines ~8205-8212) asserts the current two-way contract (`check_resume.on_yes == resume_build_synth`, `on_no == dequeue_next`); must gain a third assertion branch for `resume_reconcile`.
- `scripts/tests/test_rn_refine.py` — companion granular test file already covering resume routing at the FSM-object level:
  - `class TestResumeRouting` (lines 457-493) — `on_yes`/`on_no`/`on_error` assertions + `_render`/`_bash`-based execution tests for `check_resume`'s `RESUME_MODE`/`FRESH` tokens.
  - `class TestInitResumeShortCircuit` (lines 496-535) — `test_resume_preserves_existing_tree` seeds a populated `nodes/`/`queue.txt`/`node_counter.txt` tree and asserts `init` doesn't clobber it when `resume=1`; needs a companion `test_no_resume_flag_refuses_to_reseed` (seed the same tree, render with `resume=""`, assert `returncode == 1` and a `resume=1`-hint string, and that `queue.txt`/`nodes/` are untouched).
  - `class TestResumeBuildSynth` (lines 538-583) — execution-based fixture test template (`_render` + `_bash`, asserting on resulting `synth_queue.txt`/`final.md` state) to model a new `TestResumeReconcile` class after, fixture-seeding `visited.txt`/`queue.txt`/`node_outcome_<id>.txt` and asserting on the resulting `queue.txt` ordering.

## Impact

- **Severity**: P2 — data-loss (no-flag path) and silent phantom-complete output (resume path) in a shipped built-in loop whose runs take hours, making interruption+resume a common need.
- **Scope**: `scripts/little_loops/loops/rn-refine.yaml` only; `oracles/plan-node-refine` idempotency check as verification.

## Acceptance Criteria

- [ ] `check_resume` distinguishes walk-resume from synth-resume via `node_outcome_*.txt` / `queue.txt` state and routes walk-resume back through `dequeue_next`.
- [ ] Visited-but-outcome-less nodes (in-flight at kill time) are re-queued and re-processed on walk-resume.
- [ ] `init` refuses to re-seed a `run_dir` containing an existing `nodes/` dir when `resume` is unset.
- [ ] Synth-resume behavior (all outcomes present, queue empty) is unchanged.
- [ ] A `scripts/tests/test_builtin_loops.py`-style test asserts the three-way routing against fixture run-dir states (mid-walk, post-walk, fresh).
- [ ] `ll-loop validate rn-refine` passes.

## Session Log
- `/ll:wire-issue` - 2026-07-12T03:30:27 - `118fcc05-0101-48e9-9735-9721f77a6ee0.jsonl`
- `/ll:refine-issue` - 2026-07-12T03:20:29 - `3b4e4367-c46d-42a1-8673-1a5f4c6a41ea.jsonl`
- `/ll:capture-issue` - 2026-07-12T02:55:44Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1eac247c-15b6-4270-a306-2f8ac305bf0a.jsonl`
- `/ll:confidence-check` - 2026-07-11T21:58:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4c1894e-1315-4fba-b031-9ece3a16bcc3.jsonl`
