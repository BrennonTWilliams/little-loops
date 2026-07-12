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
- `/ll:capture-issue` - 2026-07-12T02:55:44Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1eac247c-15b6-4270-a306-2f8ac305bf0a.jsonl`
- `/ll:confidence-check` - 2026-07-11T21:58:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4c1894e-1315-4fba-b031-9ece3a16bcc3.jsonl`
