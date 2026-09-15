---
id: ENH-3473
title: 'Write a best_effort-tagged checkpoint when a loop ends with no acceptance, so no outer iteration produces zero artifacts'
type: ENH
priority: P2
status: open
discovered_date: '2026-09-13'
labels: []
parent: ENH-3468
depends_on: [ENH-3472]
reconcile_attempted: true
---

## Summary

When a loop's budget ends with no acceptance (`max_steps`, `max_iterations_reached`, `timeout`, `stall_detected`, `cycle_detected`), nothing is written beyond the cap-hit itself — the run's final captured state is discarded even though it was already paid for. This issue makes `PersistentExecutor.run()` write one fixed-name artifact, `best_effort.json`, into `run_dir` on those terminations, tagged `metadata.best_effort: true` and holding the run's last attempt (final state, captured values, termination reason). It is an **artifact only**: no new `terminated_by` value, no new `map_final_status()` bucket, no new exit code. The run is still a `max_steps` (etc.) run; it just leaves a salvage file behind.

**Depends on ENH-3472**: the write lands inside the tail of `PersistentExecutor.run()` that ENH-3472 guards, and must itself never fail the run. It does **not** depend on ENH-3471 — the qualifying values are budget-exhaustion values that already exist; an action crash (`error`) or a routing failure (`no_route`) is not a "closest attempt" and gets no checkpoint.

## Current Behavior

`PersistentExecutor._save_state()` (`fsm/persistence.py:1129-1159`) overwrites a single fixed per-instance state file on each `state_enter`/`loop_complete`/`baseline_complete` event; `archive_run()` (`:585-644`) copies `state.json`, `events.jsonl`, `summary.json`, `probe-*.json`, and `prepatch_evidence_*.json` from `run_dir` into `.loops/.history/`. No runner-written file records "this run ran out of budget; here is what it had when it stopped." Loops that want that behavior implement it bespoke in YAML (`canvas-sketch-generator.yaml`'s `finalize`, `general-task.yaml`'s `summarize_partial`/`partial`), and every other loop gets nothing.

## Expected Behavior

- On a qualifying no-acceptance termination, `PersistentExecutor.run()` writes exactly one `best_effort.json` into `run_dir` before `save_state()`/`archive_run()` run, so `archive_run()` copies it into `.loops/.history/`.
- On every other termination (`terminal` success or failure, `error`, `no_route`, `interrupted`, `user_stopped`, `handoff`, `workdir_vanished`, …) no file is written.
- When `run_dir` is absent from context, the write is skipped silently.
- A failure writing the file is logged and never fails the run (it lives inside ENH-3472's guarded tail).
- Downstream durable-artifact consumers (archive copy-list, credential scan, evidence hashing, aux-mutation audit, handoff fallback) know the fixed name.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 3** and the checkpoint-artifact consumer wiring.

## Design

### Decision 1: artifact only — no vocabulary change
An earlier draft wavered between "new artifact" and "new `terminated_by` value / new `map_final_status()` bucket." The latter would ripple through `map_final_status`, `_derive_loop_outcome`, `EXIT_CODES`, `_WASTED_RUN_PREDICATE`, `_execute_sub_loop`, `mcp_server/tasks.py`, `_FLAG_OUTCOMES`, the `refine-to-ready` case arm, and the `test_ll_logs` parity list — for no consumer benefit, since the run *is* still budget-exhausted and should still count as wasted, still route to `on_timeout`/`on_no`, still exit 1. Decision: **no vocabulary change.** All of that wiring is out of scope.

### Decision 2: qualifying set
`_NO_ACCEPTANCE_TERMINATIONS = frozenset({"max_steps", "max_iterations_reached", "timeout", "stall_detected", "cycle_detected"})`, a module-level constant in `fsm/persistence.py`. These are the values where the executor stopped a run that was still trying. Excluded: `terminal` (the loop decided, pass or fail), `error`/`no_route`/`workdir_vanished` (died), `interrupted`/`user_stopped`/`system_signal`/`handoff`/`host_pressure_abort`/`host_budget_exceeded`/`cost_ceiling_exceeded` (deliberate or external stops that already have their own resting place). Anyone widening the set edits one constant.

### Decision 3: fixed filename `best_effort.json`, not `iter_<N>_best_effort.json`
`run_dir` is per run instance (`runs/<loop>-<stamp>/`); the "outer iteration N" of the source framework has no counterpart here, and `ExecutionResult.iterations` is the FSM step count, not an outer-loop index. A fixed name matches the existing runner-written convention (`state.json`, `summary.json`, `usage.jsonl`) and turns every consumer edit into a plain name addition rather than a glob/prefix check. The step count is recorded *inside* the file.

### Decision 4: no "closest to objective" scoring
The executor has no scores; no shared "best of N" utility exists anywhere (confirmed by repo-wide search — every hit is an unrelated domain or a bespoke loop-YAML state). The checkpoint is the **last attempt**: what `ExecutionResult` carries when the budget ran out. Loops with a numeric score keep their bespoke per-loop selection (`canvas-sketch-generator.yaml`'s `scores.tsv` sort, `vega-viz.yaml`'s in-place `best.html`); the runner does not attempt to generalize it.

### File shape
```json
{
  "metadata": {"best_effort": true, "loop_name": "<name>", "written_at": "<iso8601>"},
  "terminated_by": "max_steps",
  "final_state": "<state>",
  "iterations": 42,
  "duration_ms": 123456,
  "captured": { ... },
  "error": null
}
```
Written via `ExecutionResult.to_dict()` plus the `metadata` wrapper, atomically (`tempfile` + `os.replace`, the same pattern as `StatePersistence.save_state()` `:502-523`).

### Escape hatch (non-goal, not a test target)
Context-compaction failure (`cli/compact_session.py::main_compact_session()` → `session_store/lifecycle.py::compact_session()`, `:679-710`, no surrounding try/except) stays hard-terminal. That code path never touches `PersistentExecutor` and gains no checkpoint by construction; it is stated here so nobody extends the pattern there, but it is not a boundary this issue can test. (`hooks/pre_compact.py` is a separate host-compaction hook, unrelated.)

### Codebase Research Findings (retained, condensed)

- `canvas-sketch-generator.yaml` `finalize` (`:34` `on_max_steps: finalize`, `:344` state body) and `vega-viz.yaml` `record` (`:485-538`) are per-loop precedents for "publish the best iteration on cap-hit"; `general-task.yaml`'s `on_max_steps: summarize_partial` (`:1219`) writes a prose `summary.md` on the cap path — the JSON `summary.json` writer (`:1244`) is reached only via `final_verify.on_error`. None is a shared primitive.
- No `metadata.best_effort`-style tag or `iter_<N>_*.json` file exists anywhere today; established per-iteration conventions are `iter-N/` directories or `*-iter-N.*` names. `vega-viz.yaml:571` globs `iter-*/` directories; no collision with a flat `best_effort.json`.
- `map_final_status()` (`fsm/persistence.py:132-168`) is a closed 5-value contract with four callers (`transport.py:1750`, `persistence.py:1184,1246`, `session_store/writers.py:2934`) — untouched by Decision 1.
- `cli/logs.py::_derive_loop_outcome()` (`:2058-2083`) — untouched by Decision 1; a `max_steps` run still buckets as `max-steps`.

## Program Design

### Types
- `_NO_ACCEPTANCE_TERMINATIONS: frozenset[str]` (new, `scripts/little_loops/fsm/persistence.py`).
- `BEST_EFFORT_FILENAME = "best_effort.json"` (new constant, `scripts/little_loops/fsm/persistence.py`) — imported by `cli/loop/evidence.py` and `cli/loop/audit.py` so the name has one source of truth.

### Signatures
- `write_best_effort_checkpoint(run_dir: Path, result: ExecutionResult, loop_name: str) -> Path` (new, `scripts/little_loops/fsm/persistence.py`) — writes `run_dir / BEST_EFFORT_FILENAME` atomically; pure function, no branching on `terminated_by` (the caller decides).
- `PersistentExecutor.run(self, clear_previous: bool = True) -> ExecutionResult` (`fsm/persistence.py:1212`) — gains, at the top of ENH-3472's guarded tail and before `save_state()`, `if result.terminated_by in _NO_ACCEPTANCE_TERMINATIONS and run_dir_str: try: write_best_effort_checkpoint(...) except Exception: logger.warning(...)`.

### Call Path
`PersistentExecutor.run()` → `write_best_effort_checkpoint()` (new) → `StatePersistence.save_state()` → `StatePersistence.archive_run()` (copies `best_effort.json` via the widened copy-list).

## Wiring

### Durable-artifact consumers (the checkpoint lives in the gitignored, ephemeral `run_dir`; each of these keeps a closed hand-maintained filename list)

- `scripts/little_loops/fsm/persistence.py::StatePersistence.archive_run()` (`:585-644`) — add `BEST_EFFORT_FILENAME` to the fixed-name copy list (alongside `state.json`/`events.jsonl`/`summary.json`), and to the docstring at `:590-600`.
- `scripts/little_loops/cli/loop/evidence.py::_scan_for_credentials()` (`:198-254`, tuple at `:211`) — add `BEST_EFFORT_FILENAME` to the `("state.json", "events.jsonl", "summary.json")` tuple so it is credential-scanned (ENH-3470).
- `scripts/little_loops/cli/loop/evidence.py` sha256 hashing tuple (`:313`) — second independent copy of the same tuple; add the name so it enters the evidence bundle (FEAT-3182).
- `scripts/little_loops/cli/loop/audit.py::_AUX_EXCLUDED_NAMES` (`:23-30`) — add `BEST_EFFORT_FILENAME` as a plain set member (fixed name; no prefix check needed). Without it every checkpoint inflates `aux_mutation_count`.
- `scripts/little_loops/hooks/pre_compact_handoff.py::_build_fallback()` (`:103-135`) — takes the *first* file from an unordered `rd.glob("*.json")` per run dir. Prefer `summary.json` when present, else `state.json`, else the first sorted `*.json`; this is a latent nondeterminism bug independent of this issue, but the new file makes it more likely to surface `{"metadata": ...}` keys as "the" run state.

### Documentation

- `docs/reference/loops.md` § "Output Artifacts" / "Runner-written files" — the sole doc listing runner-written `run_dir` files (currently only `usage.jsonl`); add `best_effort.json` with the qualifying-set and file-shape description.
- `docs/guides/LOOPS_GUIDE.md` `### Safety Limits` table (~127, `on_max_steps` row: "unset | Silent budget exhaustion…") — no longer silent; note the checkpoint.
- `skills/audit-loop-run/SKILL.md` (~293) Step 6b verdict table — add a note that a `max_steps`/`timeout` run with `best_effort.json` present should be read as "salvageable partial" (prose only; `test_audit_loop_run_skill.py` is string-containment, no automated verdict logic).

### Confirmed Not Affected (per Decision 1)

- `map_final_status()`, `_derive_loop_outcome()`, `_FLAG_OUTCOMES`/`is_flagged()`/`fleet_improve.py`, `EXIT_CODES`/`_is_success`, `_WASTED_RUN_PREDICATE`, `FSMExecutor._execute_sub_loop()`, `mcp_server/tasks.py::handle_tasks_get`, `refine-to-ready-issue.yaml:1043` and `auto-refine-and-implement.yaml:367` case arms, `generate_schemas.py`/`EVENT-SCHEMA.md`, `test_ll_logs.py::TestIsFlaggedParity`, `docs/runbooks/FLEET_LOOP_REVIEW.md` — no vocabulary changes, so none of these observe anything new.
- `PersistentExecutor.archive_run_only()` (`:1161-1210`) — its one caller (`cli/loop/signals.py:60`) hardcodes `terminated_by="interrupted_force"`, which is not in the qualifying set, and it has no `ExecutionResult`; no checkpoint on the force-exit path.
- Nested sub-loops: `_execute_sub_loop()`'s child (`fsm/executor.py:1226`) is a plain `FSMExecutor`, not a `PersistentExecutor`, so only the outermost `ll-loop run` instance writes a checkpoint. Document this in `docs/reference/loops.md`; it is a scope limitation, not a bug.

## Implementation Steps

1. Add `_NO_ACCEPTANCE_TERMINATIONS`, `BEST_EFFORT_FILENAME`, and `write_best_effort_checkpoint()` to `fsm/persistence.py` (atomic write, `ExecutionResult.to_dict()` + `metadata` wrapper).
2. Call it from `PersistentExecutor.run()`'s guarded tail (after ENH-3472 lands), before `save_state()`, only when `terminated_by` qualifies and `run_dir` is set; wrap in its own `except Exception  # noqa: BLE001` + `logger.warning`.
3. Widen `archive_run()`'s copy list, both `evidence.py` tuples, and `_AUX_EXCLUDED_NAMES`, importing `BEST_EFFORT_FILENAME` rather than repeating the literal.
4. Fix `pre_compact_handoff.py::_build_fallback()`'s file pick to prefer `summary.json` → `state.json` → first sorted `*.json`.
5. Tests, `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor` (post-construction method-assign convention):
   - A loop that hits `max_steps` with `run_dir` in context → `best_effort.json` exists under the run dir, `json.loads` shows `metadata.best_effort is True`, `terminated_by == "max_steps"`, and `captured` matches `result.captured`.
   - Same for `timeout` (via a tiny `timeout:`) — pins that the set is not `max_steps`-only.
   - Negative cases: `terminal` success, `terminal` with `failure_terminal=True`, and an `error` run write **no** file.
   - No `run_dir` in context → no file, no exception.
   - `write_best_effort_checkpoint` patched with `side_effect=RuntimeError` → `run()` still returns the result and `save_state`/`archive_run` are still called.
   - `archive_run()` copies `best_effort.json` when present / omits it when absent — the `test_archive_run_copies_probe_files_from_run_dir` (:772-792) / `..._omits_probe_files_when_absent` (:810-823) pair shape.
6. Tests elsewhere: `test_cli_loop_audit.py::TestAuditRun` — a `best_effort.json` in `run_dir` does not increment `aux_mutation_count` (today's only test, `test_aux_mutation_scan_counts_new_files` :176-184, proves only the positive case); `test_feat3182_evidence_bundle.py` — the file is hashed and credential-scanned when present; a `test_pre_compact_handoff.py` case that a run dir containing both `best_effort.json` and `summary.json` surfaces `summary.json`'s keys.
7. Update `docs/reference/loops.md`, `docs/guides/LOOPS_GUIDE.md` Safety Limits row, and `skills/audit-loop-run/SKILL.md` per Wiring; resync skill mirrors with `ll-adapt` if `test_verify_host_map.py` flags the SKILL.md edit.
8. `python -m pytest scripts/tests/test_fsm_persistence.py scripts/tests/test_cli_loop_audit.py scripts/tests/test_feat3182_evidence_bundle.py scripts/tests/test_pre_compact_handoff.py scripts/tests/test_audit_loop_run_skill.py -v` passes.

## Tests

- `test_fsm_persistence.py::TestPersistentExecutor` (~856-925) — `test_run_saves_final_state` (:915) is the construction template; `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects` (:960-968) is the method-assign template.
- `test_fsm_executor.py::test_finish_survives_record_loop_run_summary_failure` (:3679-3699) — failure-injection shape for "checkpoint write fails, run still returns."
- `test_cli_loop_audit.py::TestAuditRun::test_aux_mutation_scan_counts_new_files` (:176-184) — shape for the exclusion negative case.

## Scope Boundaries

- **In scope**: the `best_effort.json` write path and its five durable-artifact consumers; the handoff-fallback file-pick fix; docs.
- **Out of scope**: any `terminated_by`/`map_final_status`/exit-code/outcome-bucket change (Decision 1); a generic scoring or "best of N" utility (Decision 4); checkpoints for nested sub-loops or the force-exit path; `PersistentExecutor._save_state()`'s existing single-file overwrite; context-compaction handling.

## Impact

- **Priority**: P2 - Matches frontmatter; sequenced after ENH-3472.
- **Effort**: Small-Medium - One writer function, one guarded call, four name additions, one glob-order fix, docs, and ~10 tests.
- **Risk**: Low - Additive file write on a path that already ends the run; no shared classification code is touched.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-13 | Priority: P2

## Session Log
- `/ll:verify-issues` - 2026-09-15T23:13:48 - `0f995d07-641d-467b-93d8-b6a178acbacb.jsonl`
- Manual review rewrite - 2026-09-15 - dropped the ENH-3471 dependency (qualifying set is budget-exhaustion values that already exist) in favor of ENH-3472; decided artifact-only (no vocabulary/`map_final_status`/exit-code change), fixed filename `best_effort.json`, last-attempt semantics (no scoring); removed the untestable compaction Step 4; cut the vocabulary-driven wiring accordingly.
- `/ll:wire-issue` - 2026-09-15T22:33:23 - `74d0e714-5fa8-4d36-8d26-f70b1e11f439.jsonl`
- `/ll:reconcile-issue` - 2026-09-15T22:22:51 - `d2ee88e4-436e-400b-a42b-568c16a51760.jsonl`
- `/ll:refine-issue` - 2026-09-15T22:19:37 - `a0a3cae8-46b6-4741-b032-8859dea7a727.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:29:41 - `8cf1df9b-8fca-46d9-b751-f28d170c6572.jsonl`
- `/ll:refine-issue` - 2026-09-14T19:32:06 - `93b68600-9c57-4c65-a431-1e887e42f117.jsonl`
- `/ll:format-issue` - 2026-09-14T19:19:10 - `b113a2f7-29c0-4877-96df-0ecdfe92bfb9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:46 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:25 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`
