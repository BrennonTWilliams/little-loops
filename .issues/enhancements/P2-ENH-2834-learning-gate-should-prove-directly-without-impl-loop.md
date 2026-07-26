---
id: ENH-2834
type: ENH
title: learning gate should invoke ready-to-implement-gate directly instead of chaining
  a redundant impl loop with empty task
priority: P2
status: done
captured_at: '2026-07-26T18:09:17Z'
completed_at: '2026-07-26T19:19:55Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
relates_to:
- BUG-2832
- BUG-2833
- BUG-2831
- FEAT-1738
labels:
- learning-gate
- ll-auto
- proof-first-task
- efficiency
decision_needed: false
confidence_score: 98
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2834: learning gate should invoke ready-to-implement-gate directly instead of chaining a redundant impl loop with empty task

## Summary

ll-auto's learning gate (`run_learning_gate_for_issue`, `scripts/little_loops/learning_tests/gate.py:58`) only needs a prove/refute verdict for the issue's `learning_tests_required` targets — after the gate passes, `issue_manager.py` proceeds to its own Phase 2 implementation. But the wrapper it spawns, `proof-first-task`, always chains past the gate into `run_impl` (`proof-first-task.yaml:65`), launching the `general-task` impl loop with `input: "${context.task}"` where `task` is empty (gate.py passes only `issue_file` and `targets_csv`). This is:

1. **Redundant** — any impl work done there is thrown away; ll-auto implements the issue itself afterwards.
2. **Wasteful** — a full baseline pytest run (~2.5 min) plus DoD/plan LLM calls per gated issue.
3. **Fragile** — the empty-task injection makes the child improvise a plan from ambient repo state, and any impl-side failure is mislabeled as a gate block (BUG-2833; currently guaranteed by BUG-2832). Observed in run `proof-first-task-20260726T125247`, which caused BUG-2831's spurious `gate_blocked` deferral.

## Current Behavior

`gate.py` → `ll-loop run proof-first-task --context issue_file=... --context targets_csv=...` → `gate_direct` (ready-to-implement-gate, the actual proof) → on success `run_impl` (general-task with empty task) → outcome of the *impl* loop determines the gate verdict.

## Expected Behavior

The learning gate's verdict is determined solely by the proof step. Either:

- **Option A (preferred)**: `gate.py` invokes `ready-to-implement-gate` directly: `ll-loop run ready-to-implement-gate --context targets=<csv>`. Its terminals are exactly `done`/`blocked`, so the existing exit-code mapping becomes correct by construction, and BUG-2833's conflation is structurally impossible. The `targets` are already resolved by `resolve_learning_targets()` before the call, so the JIT-extraction fallback (`assumption-firewall` path) is only needed when `targets_csv` is empty — keep routing that case through `proof-first-task`, or accept extraction inline.
- **Option B**: add a `gate_only: "true"` context flag to `proof-first-task` that routes `gate_direct`/`check_gate_blocked` success to `done` instead of `run_impl`; `gate.py` passes it.

## Motivation

Deferral is supposed to be the rarest autodev outcome. Every structural dependency between the learning gate and an unrelated impl loop widens the set of failures that masquerade as `gate_blocked`. Cutting the impl loop out of the gate path removes an entire failure class and ~3–5 minutes of wasted compute per gated issue.

## Proposed Solution

> **Selected:** Option A — matches the proven `_run_learning_gate_preflight()` pattern already in production and fully eliminates the impl-loop overhead rather than partially trimming it.

**Option A**: `gate.py` invokes `ready-to-implement-gate` directly: `ll-loop run ready-to-implement-gate --context targets=<csv>`. Its terminals are exactly `done`/`blocked`, so the existing exit-code mapping becomes correct by construction, and BUG-2833's conflation is structurally impossible. The `targets` are already resolved by `resolve_learning_targets()` before the call, so the JIT-extraction fallback (`assumption-firewall` path) is only needed when `targets_csv` is empty — keep routing that case through `proof-first-task`, or accept extraction inline.

**Option B**: add a `gate_only: "true"` context flag to `proof-first-task` that routes `gate_direct`/`check_gate_blocked` success to `done` instead of `run_impl`; `gate.py` passes it.

### Decision Rationale

**Selected: Option A**

`_run_learning_gate_preflight()` (`scripts/little_loops/cli/sprint/run.py:172-236`) is a working, in-repo precedent for exactly Option A's mechanics: it already shells `ll-loop run ready-to-implement-gate --context targets=<csv>` directly and treats non-zero exit as `blocked`, with no impl-loop chaining. `ready-to-implement-gate.yaml` has exactly two terminals (`done`/`blocked`), so BUG-2833's `blocked` vs `impl_failed` conflation becomes structurally impossible on this path rather than merely avoided. Option B only trims the trailing `run_impl` hop while still paying `proof-first-task`'s FSM overhead (`check_issue_file`/`check_targets_csv`) and bolts an unrelated "gate-only mode" concern onto a loop framed as an impl-delegator.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A | 3 | 2 | 2 | 2 | 9/12 |
| B | 1 | 2 | 2 | 3 | 8/12 |

**Key evidence:**
- `run.py:_run_learning_gate_preflight()` already implements Option A's direct-invocation approach in production (`ll-sprint` path).
- `ready-to-implement-gate.yaml` has exactly two terminals (`done`/`blocked`) — no `impl_failed`-equivalent to conflate with.
- Option A's follow-up cost (updating `gate.py`'s `impl_failed` return-contract/tests) is bounded and mechanical; Option B grows `proof-first-task.yaml`'s routing surface for a narrower win and still runs the wrapper's preamble states even when targets are already resolved.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing template for the direct-invocation change**: `scripts/little_loops/cli/sprint/run.py:_run_learning_gate_preflight()` (~lines 178-236) already invokes `ready-to-implement-gate` directly with `--context targets=<csv>` and treats any non-zero exit as `blocked` — no `list_run_history()` needed, because `ready-to-implement-gate.yaml`'s `prove` state has exactly one failure terminal (`blocked`; `done` is the only success terminal). This is the pattern `gate.py`'s new branch should copy.
- **`run_learning_gate_for_issue` current shape** (`scripts/little_loops/learning_tests/gate.py:58-121`): builds `cmd = ["ll-loop", "run", "proof-first-task", "--context", f"issue_file={issue_path}"]`, adds `--context targets_csv=...` only when `targets` is non-empty, and — post BUG-2833 (commit `b45b29fb`) — on `FAILURE_TERMINAL_EXIT_CODE` (`fsm/types.py:25`, value `2`) calls `list_run_history("proof-first-task", loops_dir=working_dir / ".loops")` and inspects `history[0].current_state` to distinguish `blocked` from `impl_failed`. That discrimination step becomes unnecessary once the direct-invocation path is added, since `ready-to-implement-gate` has no `impl_failed`-equivalent terminal to conflate with.
- **`proof-first-task.yaml`'s own FSM-level branch already encodes this split** (`check_targets_csv` state, line 25 → `on_yes: gate_direct`, `on_no: gate`): `gate_direct` (line 31) invokes `ready-to-implement-gate` with `targets: "${context.targets_csv}"`, but its `on_success` still routes to `run_impl` (line 65) instead of `done` — that's the redundant hop ENH-2834 removes by having `gate.py` call `ready-to-implement-gate` directly instead of going through `proof-first-task` at all when targets are non-empty. The `gate` fallback state (assumption-firewall JIT path) is the empty-targets case to preserve per Option A's carve-out.
- **`worker_pool.py`'s equivalent preflight** (`scripts/little_loops/parallel/worker_pool.py:~68-120`) has the same empty/non-empty targets dispatch shape and the same simplified exit-code-only verdict mapping (comment there, ~lines 107-110, notes the old state-file read was "retired" under ENH-2814 in favor of exit-code-only checking) — worth aligning with once `gate.py` is fixed, though it isn't in this issue's stated scope.
- **`general-task.yaml` has no empty-input guard**: every prompt state (`define_done`, `plan`, `do_work`, etc.) interpolates `${context.input}` verbatim with no validation, confirming AC #3's claim that an empty task is never rejected — it silently runs the full baseline-test + DoD/plan pipeline against ambient repo state.
- **`issue_manager.py` Phase 2 already discards any `run_impl` work**: verdict branching at lines ~879-916 only inspects the `passed`/`blocked`/`impl_failed`/`skipped` string from `run_learning_gate_for_issue`; on `passed` it proceeds to its own independent `manage-issue` invocation (line ~916 onward) regardless of what `general-task` did inside the gate call — confirming the "redundant" framing in the Summary.
- **Existing regression-test pattern to extend**: `scripts/tests/test_learning_tests_gate.py` — `TestRunLearningGateForIssueTargetsThreading` (lines 12-86) patches `little_loops.learning_tests.gate.subprocess.run` and inspects `mock_sub.call_args[0][0]` to assert the built `cmd` list; `TestRunLearningGateForIssueTerminalDiscrimination` (lines 103-169) patches `little_loops.fsm.persistence.list_run_history` via a local `_make_loop_state()` helper. AC #2's new regression test (proven target + broken impl chain still passes) should assert that when `targets` is non-empty, `cmd[2] == "ready-to-implement-gate"` (not `proof-first-task`) and that no `list_run_history` call is made — proving the impl loop is structurally unreachable, not just avoided by luck.

## Impact

- **Blast radius**: `scripts/little_loops/learning_tests/gate.py` (`run_learning_gate_for_issue`) and `scripts/little_loops/loops/proof-first-task.yaml`; `issue_manager.py`'s verdict branching is unaffected since the returned string contract (`passed`/`blocked`/`impl_failed`/`skipped`) stays the same.
- **Behavioral change**: gated issues with resolved `learning_tests_required` targets skip the `general-task` impl loop entirely, cutting per-issue gate wall-time from ~2.5+ minutes (baseline pytest + DoD/plan calls) to the registry-check cost alone.
- **Risk**: low — `ready-to-implement-gate` is already invoked as a sub-step of `proof-first-task`'s `gate_direct` state and directly by `sprint/run.py:_run_learning_gate_preflight()`, so this reuses a proven path rather than introducing a new one.

## Scope Boundaries

**In scope**: `gate.py`'s non-empty-targets branch (direct `ready-to-implement-gate` invocation, dropping the `list_run_history()` discrimination for that branch); `proof-first-task.yaml`'s empty-task hole in `run_impl` for the remaining empty-targets/JIT-extraction fallback path; the regression test extending `test_learning_tests_gate.py`.

**Out of scope**: aligning `worker_pool.py`'s equivalent targets-empty/non-empty dispatch (noted as a follow-on, not required here); changing the `passed`/`blocked`/`impl_failed`/`skipped` string contract consumed by `issue_manager.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py` — `run_learning_gate_for_issue()` (lines 58-121): branch on non-empty `targets` to build `["ll-loop", "run", "ready-to-implement-gate", "--context", f"targets={','.join(targets)}"]` instead of `proof-first-task`; drop the `list_run_history()` discrimination for that branch (only needed for `proof-first-task`'s two-failure-terminal case)
- `scripts/little_loops/loops/proof-first-task.yaml` — fix the empty-task hole in `run_impl` (line 65): synthesize `context.task` from `context.issue_file` when empty, or fail fast, before invoking `general-task`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:875-916` — calls `resolve_learning_targets(info)` then `run_learning_gate_for_issue(...)`; verdict-branching logic (`passed`/`blocked`/`impl_failed`/`skipped`) is unaffected by this change since the string contract stays the same
- `scripts/little_loops/parallel/worker_pool.py:~68-120` — has an equivalent targets-empty/non-empty dispatch that still routes both branches through `proof-first-task`; not in this issue's stated scope but should be aligned once `gate.py` is fixed
- `scripts/little_loops/cli/sprint/run.py:_run_learning_gate_preflight()` (~178-236) — already calls `ready-to-implement-gate` directly; this is the template, not a caller that needs changing

### Similar Patterns
- `scripts/little_loops/cli/sprint/run.py:_run_learning_gate_preflight()` — direct `ready-to-implement-gate` invocation with simple exit-code-only verdict mapping (no history lookup)

### Tests
- `scripts/tests/test_learning_tests_gate.py` — `TestRunLearningGateForIssueTargetsThreading` (lines 12-86) and `TestRunLearningGateForIssueTerminalDiscrimination` (lines 103-169): extend with a case asserting non-empty targets build a `ready-to-implement-gate` command and never call `list_run_history`
- `scripts/tests/test_builtin_loops.py` — validates `proof-first-task`/`ready-to-implement-gate` loop structure; check for existing assertions that may need updating if `proof-first-task.yaml`'s `run_impl` gains a task-synthesis guard

## Acceptance Criteria

- [x] With resolved targets, `run_learning_gate_for_issue` no longer spawns any impl loop; the verdict comes from `ready-to-implement-gate` (or gate-only mode) alone
- [x] A proven-registry issue whose impl chain is broken still passes the learning gate (regression test for the BUG-2831 scenario)
- [x] `proof-first-task` with `issue_file` set but empty `task` either synthesizes the task from the issue file or fails fast at validation — it no longer launches `general-task` with an empty task
- [x] Gate wall-time for a proven target drops to the registry-check cost (no baseline pytest run)
- [x] `python -m pytest scripts/tests/` passes with no new failures

## Resolution

Implemented Option A: `run_learning_gate_for_issue()` now invokes `ready-to-implement-gate`
directly (`--context targets=<csv>`) when `targets` is non-empty, mirroring
`_run_learning_gate_preflight()`'s proven pattern — exit code alone determines
`passed`/`blocked`, with no `list_run_history()` discrimination needed since
`ready-to-implement-gate` has no `impl_failed`-equivalent terminal. The
empty-targets JIT-extraction fallback still routes through `proof-first-task`
unchanged (including its `list_run_history`-based blocked/impl_failed
discrimination). `proof-first-task.yaml` gained a `resolve_task` state ahead
of `run_impl` that synthesizes a fallback task from `issue_file` when
`context.task` is empty, and fails fast to a new `task_missing` terminal when
neither is set — closing the empty-input hole for the remaining fallback path.

## Session Log
- `/ll:manage-issue` - 2026-07-26T19:19:33Z - `6454f323-812c-4104-80f2-c8d1eab3918d.jsonl`
- `/ll:ready-issue` - 2026-07-26T19:10:28 - `f0e14076-63a4-44a4-8d96-93dc291673f5.jsonl`
- `/ll:confidence-check` - 2026-07-26T19:15:00 - `63501b35-10b7-4fd6-983c-92b6f9b0051e.jsonl`
- `/ll:decide-issue` - 2026-07-26T19:07:11 - `0a0824ca-0c51-497b-b936-70b37aa92d13.jsonl`
- `/ll:refine-issue` - 2026-07-26T19:04:06 - `5f628015-08cb-4164-a11a-d5c3772a4b1d.jsonl`
- `/ll:capture-issue` - 2026-07-26T18:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad137648-1307-46a8-940f-ff28f5c2fa83.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-07-26
