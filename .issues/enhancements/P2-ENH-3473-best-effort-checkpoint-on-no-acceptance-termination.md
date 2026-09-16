---
id: ENH-3473
title: Write a best_effort-tagged checkpoint when a loop ends with no acceptance,
  so no outer iteration produces zero artifacts
type: ENH
priority: P2
status: done
discovered_date: '2026-09-13'
completed_at: '2026-09-16T02:24:04Z'
labels: []
parent: ENH-3468
depends_on:
- ENH-3472
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
verify_verdict: VALID
---

## Summary

When a loop's budget ends with no acceptance (`max_steps`, `max_iterations_reached`, `timeout`, `stall_detected`, `cycle_detected`), nothing is written beyond the cap-hit itself — the run's final captured state is discarded even though it was already paid for. This issue makes `PersistentExecutor.run()` write one fixed-name artifact, `best_effort.json`, into `run_dir` on those terminations, tagged `metadata.best_effort: true` and holding the run's last attempt (final state, captured values, termination reason). It is an **artifact only**: no new `terminated_by` value, no new `map_final_status()` bucket, no new exit code. The run is still a `max_steps` (etc.) run; it just leaves a salvage file behind.

**Builds on ENH-3472** (done, `949b08712`): the write lands inside the tail of `PersistentExecutor.run()` that ENH-3472's guard wraps, and must itself never fail the run. It does **not** depend on ENH-3471 — the qualifying values are budget-exhaustion values that already exist; an action crash (`error`) or a routing failure (`no_route`) is not a "closest attempt" and gets no checkpoint.

## Current Behavior

`PersistentExecutor._save_state()` (`fsm/persistence.py:1130-1160`) overwrites a single fixed per-instance state file on each `state_enter`/`loop_complete`/`baseline_complete` event; `archive_run()` (`:586-645`) copies `state.json`, `events.jsonl`, `summary.json`, `probe-*.json`, and `prepatch_evidence_*.json` from `run_dir` into `.loops/.history/`. No runner-written file records "this run ran out of budget; here is what it had when it stopped." Loops that want that behavior implement it bespoke in YAML (`canvas-sketch-generator.yaml`'s `finalize`, `general-task.yaml`'s `summarize_partial`/`partial`), and every other loop gets nothing.

## Expected Behavior

- On a qualifying no-acceptance termination, `PersistentExecutor.run()` writes exactly one `best_effort.json` into `run_dir` before `save_state()`/`archive_run()` run, so `archive_run()` copies it into `.loops/.history/`.
- On every other termination (`terminal` success or failure, `error`, `no_route`, `interrupted`, `user_stopped`, `handoff`, `workdir_vanished`, …) no file is written, **and any pre-existing `run_dir / best_effort.json` is removed** (guarded, logged on failure). This matters after resume: `max_steps` / `max_iterations_reached` persist as `interrupted`, which is in `RESUMABLE_STATUSES`; `cmd_resume` re-injects the *same* `run_dir` (`cli/loop/lifecycle.py:673`) and `resume()` calls `run(clear_previous=False)`. Without the unlink, a resumed segment that finishes on `terminal` leaves the first segment's checkpoint in `run_dir`, and `archive_run()` copies it next to a `completed` `state.json`. (`stall_detected`/`cycle_detected` map to `failed` and are never resumable, so the unconditional rule costs nothing there.)
- When `run_dir` is absent from context, the write (and the cleanup) is skipped silently.
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

**Handler-routed caps do not qualify.** When a loop sets `on_max_steps` / `on_max_iterations`, the cap check in `fsm/executor.py:685-708` routes to the summary state instead of calling `_finish("max_steps")`, and the run then ends as `terminal` — so no checkpoint is written. This is by design: the loop declared its own salvage path (the two precedents below, `canvas-sketch-generator.yaml` and `general-task.yaml`, are exactly such loops and get no `best_effort.json`). The checkpoint fires only when no handler is configured, or when the handler state itself re-hits the cap (`_summary_state_executed` is already set, so the second hit falls through to `_finish("max_steps")`). Document this in `docs/reference/loops.md` alongside the qualifying set. This exclusion is **deferred, not final**: ENH-3483 (handler-routed caps should be resumable) is the follow-on; if it chooses a new `terminated_by` value for handler-routed caps, `_NO_ACCEPTANCE_TERMINATIONS` gains that one value — exactly the one-constant edit this decision promises.

`stall_detected` and `cycle_detected` map to `failed` (not `interrupted`) in `map_final_status()`; they are kept in the set because they are budget-style stops, but note the checkpoint there is low-value — a stall is by definition N identical failing attempts, so the "last attempt" equals the previous ones. Harmless, not a test-coverage priority.

### Decision 3: fixed filename `best_effort.json`, not `iter_<N>_best_effort.json`
`run_dir` is per run instance (`runs/<loop>-<stamp>/`); the "outer iteration N" of the source framework has no counterpart here, and `ExecutionResult.iterations` is the FSM step count, not an outer-loop index. A fixed name matches the existing runner-written convention (`state.json`, `summary.json`, `usage.jsonl`) and turns every consumer edit into a plain name addition rather than a glob/prefix check. The step count is recorded *inside* the file.

### Decision 4: no "closest to objective" scoring
The executor has no scores; no shared "best of N" utility exists anywhere (confirmed by repo-wide search — every hit is an unrelated domain or a bespoke loop-YAML state). The checkpoint is the **last attempt**: what `ExecutionResult` carries when the budget ran out. Loops with a numeric score keep their bespoke per-loop selection (`canvas-sketch-generator.yaml`'s `scores.tsv` sort, `vega-viz.yaml`'s in-place `best.html`); the runner does not attempt to generalize it.

### File shape
```json
{
  "metadata": {
    "best_effort": true,
    "loop_name": "<name>",
    "started_at": "<iso8601 — ExecutionResult has no started_at; pass executor.started_at>",
    "written_at": "<iso8601>"
  },
  "terminated_by": "max_steps",
  "final_state": "<state>",
  "iterations": 42,
  "duration_ms": 123456,
  "captured": { ... },
  "error": null
}
```
Written via `ExecutionResult.to_dict()` plus the `metadata` wrapper, atomically (`tempfile` + `os.replace`, the same pattern as `StatePersistence.save_state()` `:503-524`).

**Key-presence contract.** `ExecutionResult.to_dict()` (`fsm/types.py:71-89`) omits `error`, `failure_terminal`, `handoff`, and `continuation_prompt` when falsy and includes `messages` (a `list[str]`, potentially large) only when non-empty. The writer normalizes exactly one of these: `error` is **always present** (`None` when absent) so consumers can key on it without a `.get`. Everything else keeps `to_dict()`'s conditional presence — `messages` may appear, `failure_terminal`/`handoff`/`continuation_prompt` will not on any qualifying value (none of them is a handoff or a terminal). Tests assert `"error" in data`, not the full key set. `messages` (appended at `fsm/executor.py:2751`) and `captured` can be large; the writer does **not** truncate either — `state.json` already persists the same `captured` payload, and adding a cap later is a separate decision, not an implementation detail.

`metadata.started_at` is included because the `.loops/.history/<run_id>-<loop>/` folder name is derived from `started_at` (`derive_run_id()`), so a stray `best_effort.json` can be correlated back to its archive entry without opening `state.json`.

### Escape hatch (non-goal, not a test target)
Context-compaction failure (`cli/compact_session.py::main_compact_session()` → `session_store/lifecycle.py::compact_session()`, `:679-710`, no surrounding try/except) stays hard-terminal. That code path never touches `PersistentExecutor` and gains no checkpoint by construction; it is stated here so nobody extends the pattern there, but it is not a boundary this issue can test. (`hooks/pre_compact.py` is a separate host-compaction hook, unrelated.)

### Codebase Research Findings (retained, condensed)

- `canvas-sketch-generator.yaml` `finalize` (`:34` `on_max_steps: finalize`, `:344` state body) and `vega-viz.yaml` `record` (`:485-538`) are per-loop precedents for "publish the best iteration on cap-hit"; `general-task.yaml`'s `on_max_steps: summarize_partial` (`:1219`) writes a prose `summary.md` on the cap path — the JSON `summary.json` writer (`:1244`) is reached only via `final_verify.on_error`. None is a shared primitive.
- No `metadata.best_effort`-style tag or `iter_<N>_*.json` file exists anywhere today; established per-iteration conventions are `iter-N/` directories or `*-iter-N.*` names. `vega-viz.yaml:571` globs `iter-*/` directories; no collision with a flat `best_effort.json`.
- `map_final_status()` (`fsm/persistence.py:132-169`) is a closed 5-value contract with four callers (`transport.py:1750`, `persistence.py:1185,1247`, `session_store/writers.py:2934`) — untouched by Decision 1.
- `cli/logs.py::_derive_loop_outcome()` (`:2058-2083`) — untouched by Decision 1; a `max_steps` run still buckets as `max-steps`.

## Program Design

### Deviations

- 2026-09-16 — Decision 2's "the run then ends as terminal" premise for
  handler-routed caps (`on_max_steps`/`on_max_iterations`) does not hold
  against current code. Empirically verified (both a bare terminal handler
  and the canvas-sketch-generator `finalize → finalize_done → done` shape):
  once `_summary_state_executed`/`_iteration_summary_executed` is set,
  `fsm/executor.py:822-835` (terminal check) and `:973-980` (`next_state is
  None`) unconditionally preserve `terminated_by="max_steps"` /
  `"max_iterations_reached"` (BUG-158/BUG-2204), even after the handler
  routes onward to a distinct terminal state. So handler-routed caps are
  **not** excluded from the checkpoint in practice — `write_best_effort_checkpoint`
  still fires for them today, since `max_steps`/`max_iterations_reached` stay
  in `_NO_ACCEPTANCE_TERMINATIONS` regardless of whether a handler ran. This
  is harmless (a checkpoint for a handler-routed cap is still a legitimate
  salvage artifact) and does not change the implementation — `docs/reference/loops.md`
  was written to describe the verified behavior instead of the original
  premise. Left for ENH-3483 to reconsider if it introduces a new
  `terminated_by` value for handler-routed caps. The Implementation Steps'
  test-4 assertion ("on_max_steps pointing at a terminal state → no file,
  `terminated_by == terminal`") was corrected to match verified behavior in
  `test_fsm_persistence.py::TestPersistentExecutor::test_run_writes_checkpoint_on_max_steps_with_handler_chaining_to_terminal`.

### Types
- `_NO_ACCEPTANCE_TERMINATIONS: frozenset[str]` (new, `scripts/little_loops/fsm/persistence.py`).
- `BEST_EFFORT_FILENAME = "best_effort.json"` (new constant, `scripts/little_loops/fsm/persistence.py`) — imported by `cli/loop/evidence.py` and `cli/loop/audit.py` so the name has one source of truth.

### Signatures
- `write_best_effort_checkpoint(run_dir: Path, result: ExecutionResult, loop_name: str, started_at: str) -> Path` (new, `scripts/little_loops/fsm/persistence.py`) — writes `run_dir / BEST_EFFORT_FILENAME` atomically; pure function, no branching on `terminated_by` (the caller decides). Normalizes `error` to always-present per the key-presence contract.
- `PersistentExecutor.run(self, clear_previous: bool = True) -> ExecutionResult` (`fsm/persistence.py:1213`) — gains, at the top of ENH-3472's guarded tail and before `save_state()`, `if run_dir_str: try: if result.terminated_by in _NO_ACCEPTANCE_TERMINATIONS: write_best_effort_checkpoint(...) else: (run_dir / BEST_EFFORT_FILENAME).unlink(missing_ok=True) except Exception: logger.warning(...)`. The `else` branch is the post-resume stale-checkpoint cleanup from Expected Behavior.

### Call Path
`PersistentExecutor.run()` → `write_best_effort_checkpoint()` (new) → `StatePersistence.save_state()` → `StatePersistence.archive_run()` (copies `best_effort.json` via the widened copy-list).

## Wiring

### Durable-artifact consumers (the checkpoint lives in the gitignored, ephemeral `run_dir`; each of these keeps a closed hand-maintained filename list)

- `scripts/little_loops/fsm/persistence.py::StatePersistence.archive_run()` (`:586-645`) — add `BEST_EFFORT_FILENAME` to the fixed-name copy list (alongside `state.json`/`events.jsonl`/`summary.json`), and to the docstring at `:591-601`.
- `scripts/little_loops/cli/loop/evidence.py::_scan_for_credentials()` (`:198-254`, tuple at `:212`) — add `BEST_EFFORT_FILENAME` to the `("state.json", "events.jsonl", "summary.json")` tuple so it is credential-scanned (ENH-3470).
- `scripts/little_loops/cli/loop/evidence.py` sha256 hashing tuple (`:312`) — second independent copy of the same tuple; add the name so it enters the evidence bundle (FEAT-3182).
- `scripts/little_loops/cli/loop/audit.py::_AUX_EXCLUDED_NAMES` (`:23-30`) — add `BEST_EFFORT_FILENAME` as a plain set member (fixed name; no prefix check needed). Without it every checkpoint inflates `aux_mutation_count`.
- `scripts/little_loops/cli/loop/audit.py` audit report (`:190`, where it already opens `run_dir / "summary.json"`) — add a machine-readable `best_effort_present: bool` field to the audit output (`run_dir / BEST_EFFORT_FILENAME` exists). The skill-prose note below asks a human to notice the file; the audit already opens the run dir, so the flag is one `.exists()` call and lets `audit-loop-run` and fleet tooling key on it instead of on a filename.

### Independent latent bug, bundled (own step, own test — may be split out as a BUG)

- `scripts/little_loops/hooks/pre_compact_handoff.py::_build_fallback()` (`:103-135`, pick at `:122`) — takes the *first* file from an unordered `rd.glob("*.json")` per run dir. Prefer `summary.json` when present, else `state.json`, else the first sorted `*.json`. Nothing in the checkpoint path depends on this fix; it is bundled only because the new file makes the nondeterminism more likely to surface `{"metadata": ...}` keys as "the" run state. Keep it in its own implementation step and its own test so a regression there is not attributed to the checkpoint; splitting it into a standalone BUG and dropping it here is an acceptable alternative.

### Documentation

- `docs/reference/loops.md` `:122` — the `> **Runner-written files**:` blockquote (not a heading; it is the sole doc listing runner-written `run_dir` files, currently only `usage.jsonl`, and it states that file is **not** archived to `.loops/.history/`). Add `best_effort.json` as an explicit contrast — it **is** archived — with the qualifying set, the handler-routed-cap exclusion (`on_max_steps`/`on_max_iterations` loops end as `terminal` and get no checkpoint; see ENH-3483), the post-resume cleanup rule, the key-presence contract, and the nested-sub-loop limitation.
- `docs/guides/LOOPS_GUIDE.md` `### Safety Limits` table (`:127`, `on_max_steps` row: "unset | Silent budget exhaustion…") — no longer silent; note the checkpoint.
- `skills/audit-loop-run/SKILL.md` (~293) Step 6b verdict table — add a note that a `max_steps`/`timeout` run with `best_effort.json` present should be read as "salvageable partial" (prose only; `test_audit_loop_run_skill.py` is string-containment, no automated verdict logic).

### Confirmed Not Affected (per Decision 1)

- `map_final_status()`, `_derive_loop_outcome()`, `_FLAG_OUTCOMES`/`is_flagged()`/`fleet_improve.py`, `EXIT_CODES`/`_is_success`, `_WASTED_RUN_PREDICATE`, `FSMExecutor._execute_sub_loop()`, `mcp_server/tasks.py::handle_tasks_get`, `refine-to-ready-issue.yaml:1043` and `auto-refine-and-implement.yaml:367` case arms, `generate_schemas.py`/`EVENT-SCHEMA.md`, `test_ll_logs.py::TestIsFlaggedParity`, `docs/runbooks/FLEET_LOOP_REVIEW.md` — no vocabulary changes, so none of these observe anything new.
- `PersistentExecutor.archive_run_only()` (`:1162-1211`) — its one caller (`cli/loop/signals.py:60`) hardcodes `terminated_by="interrupted_force"`, which is not in the qualifying set, and it has no `ExecutionResult`; no checkpoint on the force-exit path.
- Nested sub-loops: `_execute_sub_loop()`'s child (`fsm/executor.py:1245`) is a plain `FSMExecutor`, not a `PersistentExecutor`, so only the outermost `ll-loop run` instance writes a checkpoint. Document this in `docs/reference/loops.md`; it is a scope limitation, not a bug.

## Implementation Steps

1. Add `_NO_ACCEPTANCE_TERMINATIONS`, `BEST_EFFORT_FILENAME`, and `write_best_effort_checkpoint()` to `fsm/persistence.py` (atomic write, `ExecutionResult.to_dict()` + `metadata` wrapper with `loop_name`/`started_at`/`written_at`; `error` normalized to always-present).
2. Call it from `PersistentExecutor.run()`'s guarded tail (ENH-3472 landed in `949b08712`), before `save_state()`, only when `terminated_by` qualifies and `run_dir` is set; pass `self._executor.started_at`; wrap in its own `except Exception  # noqa: BLE001` + `logger.warning`. In the non-qualifying branch, `unlink(missing_ok=True)` any existing `run_dir / BEST_EFFORT_FILENAME` (same guard) so a resumed run that finishes cleanly does not archive a stale checkpoint.
3. Widen `archive_run()`'s copy list, both `evidence.py` tuples, and `_AUX_EXCLUDED_NAMES`, importing `BEST_EFFORT_FILENAME` rather than repeating the literal. Add `best_effort_present` to the `ll-loop audit` report next to the existing `summary.json` read (`audit.py:190`).
4. Tests, `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor` (post-construction method-assign convention — **stub `executor._executor.run` to return a hand-built `ExecutionResult`; do not drive real loops to a wall-clock `timeout:`**, which would sleep for whole seconds since `timeout` is integer seconds against `_now_ms()`):
   - One parametrized test over all five qualifying values → `best_effort.json` exists under the run dir, `json.loads` shows `metadata.best_effort is True`, `metadata.started_at == executor._executor.started_at`, `terminated_by` matches, `captured` matches `result.captured`, and `"error" in data`.
   - One parametrized test over the excluded values (`terminal` success, `terminal` with `failure_terminal=True`, `error`, `no_route`, `interrupted`, `handoff`) → **no** file.
   - One real-loop test (not stubbed): a loop with `max_steps: 2` and **no** `on_max_steps` → file present; the same loop with `on_max_steps:` pointing at a terminal state → no file, `terminated_by == "terminal"`. Pins the handler-routed-cap exclusion.
   - No `run_dir` in context → no file, no exception.
   - **Post-resume cleanup**: stub `_executor.run` to return `max_steps`, call `run()` → file present; re-stub to return `terminal`, call `run(clear_previous=False)` with the same `run_dir` → file gone. Pins the stale-checkpoint rule from Expected Behavior.
   - `write_best_effort_checkpoint` patched with `side_effect=RuntimeError` → `run()` still returns the result and `save_state`/`archive_run` are still called.
   - `archive_run()` copies `best_effort.json` when present / omits it when absent — the `test_archive_run_copies_probe_files_from_run_dir` (:772-792) / `..._omits_probe_files_when_absent` (:810-823) pair shape.
5. Tests elsewhere: `test_cli_loop_audit.py::TestAuditRun` — a `best_effort.json` in `run_dir` does not increment `aux_mutation_count` (today's only test, `test_aux_mutation_scan_counts_new_files` :176-184, proves only the positive case) and sets `best_effort_present: true` (absent → `false`); `test_feat3182_evidence_bundle.py` — the file is hashed and credential-scanned when present.
6. **Independent fix, own step**: `pre_compact_handoff.py::_build_fallback()` file pick → prefer `summary.json` → `state.json` → first sorted `*.json`. Own test in `test_pre_compact_handoff.py`: a run dir containing both `best_effort.json` and `summary.json` surfaces `summary.json`'s keys. `_build_fallback()` hardcodes the cwd-relative `Path(".loops/runs")`, so the test must `monkeypatch.chdir(tmp_path)` and build `tmp_path / ".loops/runs/<run>/"` — otherwise it silently reads the real repo's run dirs. (May be split into a standalone BUG; if so, remove this step and its Wiring entry rather than leaving them half-done.)
7. Update `docs/reference/loops.md`, `docs/guides/LOOPS_GUIDE.md` Safety Limits row, and `skills/audit-loop-run/SKILL.md` per Wiring; resync skill mirrors with `ll-adapt` if `test_verify_host_map.py` flags the SKILL.md edit.
8. `python -m pytest scripts/tests/test_fsm_persistence.py scripts/tests/test_cli_loop_audit.py scripts/tests/test_feat3182_evidence_bundle.py scripts/tests/test_pre_compact_handoff.py scripts/tests/test_audit_loop_run_skill.py -v` passes.

## Tests

- `test_fsm_persistence.py::TestPersistentExecutor` (~856-925) — `test_run_saves_final_state` (:915) is the construction template; `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects` (:928-968) is the method-assign template.
- `test_fsm_executor.py::test_finish_survives_record_loop_run_summary_failure` (:3679-3699) — failure-injection shape for "checkpoint write fails, run still returns."
- `test_cli_loop_audit.py::TestAuditRun::test_aux_mutation_scan_counts_new_files` (:176-184) — shape for the exclusion negative case.

## Scope Boundaries

- **In scope**: the `best_effort.json` write path and its five durable-artifact consumers; the `best_effort_present` audit flag; the handoff-fallback file-pick fix (bundled, separable); docs.
- **Out of scope**: any `terminated_by`/`map_final_status`/exit-code/outcome-bucket change (Decision 1); a generic scoring or "best of N" utility (Decision 4); checkpoints for handler-routed caps (`on_max_steps`/`on_max_iterations` — Decision 2), nested sub-loops, or the force-exit path; `PersistentExecutor._save_state()`'s existing single-file overwrite; context-compaction handling.

## Impact

- **Priority**: P2 - Matches frontmatter; sequenced after ENH-3472.
- **Effort**: Small-Medium - One writer function, one guarded call, four name additions, one glob-order fix, docs, and ~10 tests.
- **Risk**: Low - Additive file write on a path that already ends the run; no shared classification code is touched.
- **Breaking Change**: No.

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

Content, design decisions, and the proposal (Implementation Steps 1-4 read
against current code, per the ENH-3250 consequence check) are sound: no
fabricated evidence (`ll-verify-evidence` clean), no active decisions-log rules
violated, no PROPOSAL_UNSOUND findings — `ExecutionResult.to_dict()` exists
with matching fields, ENH-3472's guarded tail has landed (commit `949b08712`)
exactly where the Call Path assumes it, both `evidence.py` tuples are
independent copies as claimed, and `_AUX_EXCLUDED_NAMES` is a plain set. The
full "Confirmed Not Affected" ripple list and Decision 4's "no best-of-N
utility exists" claim were spot-checked and hold.

Nine line citations had drifted since last verification — a systematic +1
shift through most of `fsm/persistence.py` (from an unrelated single-line
insertion upstream of these anchors) plus two larger moves — and have been
corrected in place:

- `_save_state()`: `:1129-1159` → `:1130-1160`
- `archive_run()`: `:585-644` → `:586-645` (both citations; docstring
  `:590-600` → `:591-601`)
- `map_final_status()`: `:132-168` → `:132-169`; its callers `:1184,1246` →
  `:1185,1247`
- `StatePersistence.save_state()` atomic-write pattern: `:502-523` → `:503-524`
- `PersistentExecutor.run()`: `:1212` → `:1213`
- `archive_run_only()`: `:1161-1210` → `:1162-1211`
- `evidence.py` credential-scan tuple: `:211` → `:212`
- `evidence.py` sha256 hashing tuple: `:313` → `:312`
- `_execute_sub_loop()` child construction, `fsm/executor.py`: `:1226` →
  `:1245` (content claim — plain `FSMExecutor`, not `PersistentExecutor` —
  still correct)
- `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects`:
  `:960-968` → `:928-968` (method start, not just an end-line drift)

All other citations (docs, remaining tests, dependency chain) were confirmed
exact or within stated `~` tolerance; none needed correction. Dependency
`ENH-3472` (done, `verify_verdict: VALID`) and parent `ENH-3468` (done,
decomposed with ENH-3473 listed as a child) both check out — no DEP_ISSUES.

Graph: provider=`codegraph` freshness=`fresh` (available but not needed —
direct grep located every cited symbol).

## Resolution

- **Action**: improve
- **Completed**: 2026-09-16
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/persistence.py`: added `_NO_ACCEPTANCE_TERMINATIONS`, `BEST_EFFORT_FILENAME`, and `write_best_effort_checkpoint()` (atomic tempfile+`os.replace` write); wired the call into `PersistentExecutor.run()`'s ENH-3472 guarded tail — writes on qualifying terminations, `unlink(missing_ok=True)`-cleans a stale checkpoint otherwise (post-resume rule), guarded by its own `try/except`; widened `archive_run()`'s copy list and docstring to include `best_effort.json`.
- `scripts/little_loops/cli/loop/evidence.py`: added `BEST_EFFORT_FILENAME` to both the credential-scan and sha256-hashing tuples.
- `scripts/little_loops/cli/loop/audit.py`: added `BEST_EFFORT_FILENAME` to `_AUX_EXCLUDED_NAMES`; added `best_effort_present: bool` to `RunAuditStats`/`audit_run()`.
- `scripts/little_loops/hooks/pre_compact_handoff.py`: `_build_fallback()`'s run-dir file pick now prefers `summary.json`, then `state.json`, over an unordered `glob("*.json")[:1]` (bundled latent-bug fix per the issue's own scope).
- Tests: `test_fsm_persistence.py` (qualifying/excluded parametrized cases, a real `max_steps`-no-handler run, a real handler-routed-cap run, no-`run_dir` skip, post-resume cleanup, write-failure survival, `archive_run()` copy/omit), `test_cli_loop_audit.py` (aux-mutation exclusion, `best_effort_present` true/false), `test_feat3182_evidence_bundle.py` (hashing + credential scan), `test_pre_compact_handoff.py` (file-pick preference) — 18 + 5 + 1 + 1 new tests, full suite green (24550 passed).
- Docs: `docs/reference/loops.md` (`best_effort.json` contrast alongside the existing `usage.jsonl` runner-written-files note), `docs/guides/LOOPS_GUIDE.md` Safety Limits `max_steps` row, `skills/audit-loop-run/SKILL.md` Step 6b verdict-table note.
- Issue file: added a `### Deviations` note under `## Program Design` — Decision 2's "handler-routed caps end as terminal" premise does not hold against current executor code (BUG-158/BUG-2204 preserve `terminated_by="max_steps"` even when a cap-summary handler routes onward to a distinct terminal state); verified empirically, corrected in the docs and in the Implementation Step 4 test spec. This does not change the implementation — handler-routed caps still correctly receive a checkpoint today, since `max_steps` stays in the qualifying set regardless.

## Status

**Done** | Created: 2026-09-13 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-09-16T02:23:11 - `7a435e29-efad-4c49-9f3c-8d2f500cf069.jsonl`
- `/ll:ready-issue` - 2026-09-16T02:00:19 - `08af2728-1ccc-47f4-b6ce-b975b40fc2ed.jsonl`
- `/ll:verify-issues` - 2026-09-16T01:56:09 - `8ceae464-de93-4b46-be10-32f91e3836a6.jsonl`
- Manual review - 2026-09-15 - folded in: post-resume stale-checkpoint cleanup (unlink on non-qualifying termination, since `cmd_resume` reuses `run_dir` and `max_steps` is resumable) + its test; `docs/reference/loops.md:122` is a blockquote that says `usage.jsonl` is *not* archived, so the new entry is a contrast; `_build_fallback()` test needs `monkeypatch.chdir`; `messages`/`captured` not truncated; ENH-3483 cross-referenced as the deferred follow-on to Decision 2.
- `/ll:confidence-check` - 2026-09-16T01:45:36 - `0e2ad4cc-596f-4932-ac24-5ff12a55354d.jsonl`
- Manual review - 2026-09-15 - folded in: handler-routed caps (`on_max_steps`/`on_max_iterations`) end as `terminal` and get no checkpoint (Decision 2 + docs); file-shape reconciled with `to_dict()`'s conditional keys, `error` normalized always-present, `metadata.started_at` added; `timeout` test rewritten to stub `_executor.run` instead of a wall-clock `timeout:`; handoff-fallback fix isolated into its own step/test as separable; `best_effort_present` flag added to `ll-loop audit`; stall/cycle low-value note.
- `/ll:verify-issues` - 2026-09-16T01:33:11 - `e8d5b8ef-5cc6-4d72-bc00-83f4241c6356.jsonl`
- `/ll:confidence-check` - 2026-09-15T23:20:00 - `4aed0df2-a263-4d28-ae34-d555931852b6.jsonl`
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
