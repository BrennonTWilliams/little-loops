---
id: ENH-3472
title: Guard PersistentExecutor.run() so a save_state/archive_run exception cannot
  discard an already-computed ExecutionResult
type: ENH
priority: P2
status: done
discovered_date: '2026-09-13'
completed_at: '2026-09-16T01:23:04Z'
labels: []
parent: ENH-3468
confidence_score: 100
outcome_confidence: 96
verify_verdict: VALID
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

## Summary

`PersistentExecutor.run()` (`fsm/persistence.py:1213`) wraps `FSMExecutor.run()` and, once that inner call returns a fully-formed `ExecutionResult`, calls `StatePersistence.save_state()` (`:503`) and `StatePersistence.archive_run()` (`:586`). Neither call is exception-guarded except inside the `terminated_by == "workdir_vanished"` branch (which only catches `OSError`). If either raises (e.g. disk full) outside that branch, the exception propagates out of `PersistentExecutor.run()` unhandled and discards the result — including the `events.jsonl`/`usage.jsonl` traces `archive_run()` was about to copy into `.loops/.history/`. This issue closes that gap: an already-computed result must survive a persistence-layer failure.

This child is independent of ENH-3471 (vocabulary). **ENH-3473 depends on this issue**: it adds a further write inside the same block, which must land after this guard exists.

## Current Behavior

`PersistentExecutor.run()` (`fsm/persistence.py:1266-1282`) has two branches after building `final_state`:
- `workdir_vanished` branch: `save_state()` + `archive_run()` inside one `try` … `except OSError` that logs a warning.
- `else` branch (`:1280-1282`): the same two calls with no exception handling at all.

A `save_state()`/`archive_run()` failure in the `else` branch raises out of `PersistentExecutor.run()` uncaught. Nothing above it intercepts: `run_foreground()` (`cli/loop/runner.py:467-489`) and `cmd_run()` (`cli/loop/run.py:659-673`) are `try/finally` only; `main_loop()` (`cli/loop/__init__.py:1088`) has no try/except. The process dies with a raw traceback and Python's default exit 1, the `ExecutionResult` is lost, and the `<instance>.state.json` file is left at `status: running`.

## Expected Behavior

- `save_state()` and `archive_run()` are each guarded **independently**: a failure in `save_state()` is logged and `archive_run()` is still attempted (it is the call that copies `events.jsonl`/`usage.jsonl` into `.loops/.history/`, which is the trace this issue protects).
- Both branches (`workdir_vanished` and `else`) share one guarded block. The broad guard is a strict superset of the existing `except OSError`, so the two-branch structure collapses to a single block whose warning message notes `workdir_vanished` when applicable.
- `PersistentExecutor.run()` returns the already-computed `ExecutionResult` regardless; `runner.py:585`'s `EXIT_CODES` lookup and the `failure_terminal` exit-code path are reached normally.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 2** in full, including its dedicated wiring/test item.

## Design

Two coexisting conventions in this codebase express "a sink failure must never fail the run":

- `except Exception as exc:  # noqa: BLE001 — <rule>` with a `logger.warning`/`logger.error` — `fsm/persistence.py:905` (`promote_run_artifact()`, "promotion must never fail the run"), `fsm/persistence.py:85`, `worktree_utils.py:847`, `learning_tests/gate.py:79`, `skill_expander.py:163`, `parallel/worker_pool.py:1945,1970`, `cli/sprint/run.py:303`, `cli/harness.py:88,113,142,148,1190,1828`.
- Bare `except Exception: pass` with a `# Non-fatal (ENH-NNNN)` prose comment and no `noqa` — `fsm/executor.py:2609-2628` (ENH-3204), `:4332-4353` (ENH-2463, `record_loop_run_summary`), `:4355-4380` (ENH-2724, `record_usage_event`), `runner_spec.py:318-333`. These are the guards `_finish()` already uses so an analytics-sink failure can't discard the run — the same shape as this issue's target, one layer down.

Use the first shape (logged, `noqa: BLE001` comment), since a silent `pass` would hide a disk-full condition the operator needs to see. `BLE` is not in the repo's enabled ruff rule set (`scripts/pyproject.toml` `select = ["E","F","W","I","UP","B","C4"]`), so the comment is documentation of intent, not lint-enforced.

Sketch of the guarded tail:

```python
_vanished_note = (
    " (working directory vanished)" if result.terminated_by == "workdir_vanished" else ""
)
try:
    self.persistence.save_state(final_state)
except Exception as exc:  # noqa: BLE001 — persistence must never discard the result
    logger.warning(f"could not save final state for '{self.fsm.name}': {exc}{_vanished_note}")
try:
    self.persistence.archive_run(run_dir=Path(run_dir_str) if run_dir_str else None)
except Exception as exc:  # noqa: BLE001 — persistence must never discard the result
    logger.warning(f"could not archive run for '{self.fsm.name}': {exc}{_vanished_note}")
return result
```

In the `workdir_vanished` case both calls typically fail, producing two warnings instead of today's one. That is acceptable: each names the call that failed, and the note suffix explains why.

`promote_run_artifact()` (called earlier in the same method, `:1225-1240`) already guards itself internally and needs no change.

### Codebase Research Findings (retained, condensed)

- `cli_event_context` lives in `session_store/writers.py:497-621` (not `session_store/db.py`); its `except Exception` sites at `:579`/`:609` carry no `noqa`. It implements a different contract (guards analytics enter/exit, re-raises the body) and is not the template here.
- `cli/loop/signals.py:58-62` guards `PersistentExecutor.archive_run_only()` at the *call site* with `except OSError: pass` ("a failed archive must not prevent exit") — same rule, narrower catch, outside this issue's scope.
- `cli/artifact/*` handlers use a trailing broad `except` that *surfaces* the failure (`logger.error; return 1`) — a different flavor, not a template.

## Program Design

### Signatures
- `PersistentExecutor.run(self, clear_previous: bool = True) -> ExecutionResult` (`scripts/little_loops/fsm/persistence.py:1213`) — the tail block at `:1266-1284` is restructured per the Design sketch.
- `StatePersistence.save_state(self, state: LoopState) -> None` (`:503`), `StatePersistence.archive_run(self, run_dir: Path | None = None) -> Path | None` (`:586`) — unchanged.
- `record_loop_run_summary(...)` (`session_store/writers.py:1791`) — already written inside `_finish()`, before this block; only the filesystem archive is at risk here, not the DB row.

### Call Path
`PersistentExecutor.run()` → `run_foreground()` (`cli/loop/runner.py:479`) → `cmd_run()` (`cli/loop/run.py:659-673`) → `main_loop()` (`cli/loop/__init__.py:1088`) → `ll-loop` console-script boundary (`pyproject.toml:84`). After this fix the chain always receives the `ExecutionResult`.

`PersistentExecutor.resume()` (`:1286-1354`) ends with `return self.run(clear_previous=False)`, so the resume path shares the same tail and is covered by the same guard. There is no second tail to restructure.

### On-disk status after a failed final `save_state()`
The final `save_state(final_state)` is not the only write to `<running_dir>/<instance>.state.json`. `_save_state()` (`fsm/persistence.py:1130-1160`) runs on every `state_enter` event (`:1066-1067`), and `FSMExecutor.run()` emits `state_enter` (`executor.py:866`) *before* the terminal check (`:801`). `_save_state()` stamps `status="completed"` whenever the entered state is terminal (`:1132-1136`). Consequently, when the final save fails the file is left in one of two states:

- **Terminal exits** (`terminated_by == "terminal"`, including `failure_terminal=True`): the file already reads `completed`. `_reconcile_stale_running()` (`:280-306`) returns early at `:295` because status is not `running`, so nothing self-heals. For a `failure_terminal=True` run this leaves disk at `completed` rather than `failed` — a pre-existing quirk of `_save_state()`, not something this guard introduces. Out of scope here (see Scope Boundaries); ENH-3473 rewrites this block and is the natural place to fix it.
- **Non-terminal exits** (`max_iterations`, `error`, `timeout`, `workdir_vanished`, …): the file stays at `running`. `_reconcile_stale_running()` flips it to `interrupted` on the next `cmd_status`/`list_running_loops` read once the resolved PID is dead or `updated_at` is older than `STALE_RUNNING_THRESHOLD_S` (`:259`, 6h; BUG-3317). No new reconciliation logic is needed. The regression test for this case must use a non-terminal termination.

### Test-injection constraint
Because `_save_state()` calls the same `self.persistence.save_state` mid-run, a blanket `save_state = MagicMock(side_effect=RuntimeError(...))` raises on the first `state_enter` inside `FSMExecutor.run()` — which is unguarded — and `run()` never reaches the tail. The failure must be injected only for the *final* call: wrap the original method and raise when the passed `state.status != "running"` (the tail always passes a `map_final_status()` value; mid-run saves pass `running` except on terminal entry, which passes `completed` — so for terminal-exit tests raise on the second non-`running` call, or simply count calls and raise on the last one, established by a baseline run as `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects` (:960-968) does). `archive_run` is only called from the tail, so a plain `MagicMock(side_effect=...)` is fine there.

## Integration Map

### Observed-classification side effects (no code change required)

- `scripts/little_loops/parallel/worker_pool.py` (`:111-126`) — the proof-first-task gate distinguishes `FAILURE_TERMINAL_EXIT_CODE` (2) from other nonzero exits. Today a persistence crash coinciding with `failure_terminal=True` surfaces as exit 1 ("exited 1" warning); once guarded, exit 2 ("gate: blocked") is reached as intended.
- `scripts/little_loops/learning_tests/gate.py` (`:328-370`) — the `proof-first-task` fallback returns `"passed"` for any exit other than 2. **Today a persistence crash on a `failure_terminal=True` run is silently misclassified as `"passed"**; this fix corrects that as a side effect.
- `scripts/little_loops/cli/queue.py` (`:402`, `:432`) — `RunnerResult.error = "terminal failure" if returncode == 2 else None`; today's crash yields `error=None`. Corrected once guarded.

Call these out in the PR description.

### Tests

- `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor` (~856-925) — `test_run_saves_final_state` (:915) and `test_run_archives_to_history_on_completion` (:1509) are the happy-path templates for the `save_state()` and `archive_run()` halves respectively. No existing test injects a failure into either from inside `run()`'s tail block.
- `scripts/tests/test_ll_loop_execution.py` (`:1030`, `:1061`) and `scripts/tests/test_cost_ceiling_enforcement.py`, `scripts/tests/test_usage_journal.py` — construct a real `PersistentExecutor` and call `.run()` end-to-end; must pass unchanged.
- `scripts/tests/test_fsm_executor.py::TestWorkdirVanished::test_persistent_executor_cwd_deletion_reports_clean_abort` — exercises the `workdir_vanished` branch being collapsed; must pass unchanged.

### Confirmed Not Affected

- No documentation describes the current crash-on-persistence-failure behavior; `docs/reference/API.md:4449-4450,6780,6787` and `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:1196-1204,1234` narrate the happy-path contract, which is preserved.
- `PersistentExecutor.archive_run_only()` (`:1162-1211`) and `cli/loop/lifecycle.py::_stop_instance()` (`:466-493`) share the unguarded assumption but are separate call chains, guarded at their own call sites — out of scope.
- `mcp_server/tasks.py::handle_tasks_get` and `cli/loop/lifecycle.py::read_run_status()` read persisted status; unaffected.

## Implementation Steps

1. Restructure the tail of `PersistentExecutor.run()` (`fsm/persistence.py:1266-1284`) per the Design sketch: one code path for both branches, `save_state()` and `archive_run()` each in their own `try`/`except Exception  # noqa: BLE001`, `logger.warning` with the `workdir_vanished` note when applicable, always `return result`.
2. Add tests in `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor` using the file's post-construction method-assign convention (`test_drain_inbound_spoof_does_not_trigger_persistence_side_effects`, :960-968). Per the **Test-injection constraint** above, `save_state` failures must be injected on the final call only (a wrapper around the real method that raises once the tail is reached), never as a blanket `MagicMock(side_effect=...)`:
   - Final `save_state` raises `RuntimeError("disk full")` → `run()` returns an `ExecutionResult` with `terminated_by == "terminal"`, **and** `archive_run` was still called once (`archive_run = MagicMock(wraps=...)` or a spy).
   - `archive_run = MagicMock(side_effect=RuntimeError("disk full"))` → `run()` returns the result; the final `save_state` succeeded (`load_state().status == "completed"`).
   - A `failure_terminal=True` loop (shape: `test_final_status_failed_on_failure_terminal`, :1376-1400) with the final `save_state` failing → `result.failure_terminal is True` (pins the exit-code side effect). Assert nothing about on-disk status here; it reads `completed` from the mid-run `_save_state()` (see Program Design).
   - A non-terminal exit (looping FSM with `max_iterations=1` or equivalent) with the final `save_state` failing → on-disk status is still `running`; then, using a **fresh** `StatePersistence` (the mocked one would raise again inside `_reconcile_stale_running()` at `:305`), a `_reconcile_stale_running()` read flips it to `interrupted`. Drive liveness via a dead PID written to `<stem>.pid` or an `updated_at` older than `STALE_RUNNING_THRESHOLD_S` — the test process's own PID is alive, so `state.pid` alone will not do.
   - Optional: the collapsed `workdir_vanished` path logs the "(working directory vanished)" note — `TestWorkdirVanished::test_persistent_executor_cwd_deletion_reports_clean_abort` already covers survival; add a `caplog` assertion there only if cheap.
3. Run `scripts/tests/test_cost_ceiling_enforcement.py`, `scripts/tests/test_usage_journal.py`, `scripts/tests/test_ll_loop_execution.py`, and `scripts/tests/test_fsm_executor.py::TestWorkdirVanished` to confirm no regression.
4. `python -m pytest scripts/tests/test_fsm_persistence.py scripts/tests/test_cost_ceiling_enforcement.py scripts/tests/test_usage_journal.py scripts/tests/test_ll_loop_execution.py scripts/tests/test_fsm_executor.py -v` passes.

## Tests

- Failure-injection shape to mirror: `test_fsm_executor.py::test_finish_survives_record_loop_run_summary_failure` (:3679-3699) and `::test_finish_survives_record_usage_event_failure` (:3764-3787) — inject `side_effect=RuntimeError(...)`, call `run()`, assert on the returned `ExecutionResult`'s fields.
- `test_cli_loop_background.py::test_second_signal_swallows_archive_oserror` (:156-172) — asserts both survival and `assert_called_once_with(...)`; the "archive still attempted after save failure" assertion follows this.

## Scope Boundaries

- **In scope**: the tail of `PersistentExecutor.run()` only, plus regression tests.
- **Out of scope**: `terminated_by` vocabulary (ENH-3471); the checkpoint write (ENH-3473, which lands inside this guarded block after this issue); `archive_run_only()` and `_stop_instance()`'s separate call chains; the pre-existing `_save_state()` behavior that stamps `completed` on entering a `failure: true` terminal state (so a failed final save leaves disk at `completed` rather than `failed`) — surfaced by this guard, not caused by it; hand to ENH-3473 or file separately.

## Impact

- **Priority**: P2 - Matches frontmatter; a prerequisite for ENH-3473.
- **Effort**: Small - One restructured block plus four regression tests.
- **Risk**: Low - Additive exception handling; behavior-preserving on the success path.
- **Breaking Change**: No.

## Verification Notes

Re-verified 2026-09-15: **VALID**. All line-number citations in Summary, Current
Behavior, Design, Program Design, Integration Map, and Tests (`fsm/persistence.py`
`:503`, `:586`, `:905`, `:1213`, `:1266-1284`, `:1280-1282`, `280-306`, `1162-1211`;
`worker_pool.py:111-126`; `learning_tests/gate.py:328-370` (proof-first-task fallback
returns `"passed"` for any exit ≠ 2, confirmed at `:365-370`); `cli/queue.py:402,432`;
all cited test defs in `test_fsm_persistence.py`, `test_fsm_executor.py`,
`test_cli_loop_background.py`) checked against current HEAD and match exactly. Both
`parent: ENH-3468` and the declared `ENH-3473` dependency resolve to existing files.
Decisions log queried clean (no active required rules); `ll-verify-evidence` reports
no unverifiable quotes. No corrections needed this pass.

Verdict at time of prior check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of what
was wrong and fixed, not an outstanding action item)

- All substantive claims confirmed current: the `else` branch of
  `PersistentExecutor.run()` still has no exception handling, the `workdir_vanished`
  branch still catches only `OSError`, all three callers up the chain (`run_foreground`,
  `cmd_run`, `main_loop`) remain unguarded for this exception, and every cited test
  (`test_run_saves_final_state`, `test_run_archives_to_history_on_completion`,
  `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects`,
  `test_finish_survives_record_loop_run_summary_failure`,
  `test_finish_survives_record_usage_event_failure`,
  `test_second_signal_swallows_archive_oserror`) exists as described. Integration Map
  claims (`worker_pool.py`, `learning_tests/gate.py`, `cli/queue.py`) also confirmed.
- `fsm/persistence.py` line numbers were all off by +1 (`3632187f3`, ENH-3471, added a
  net one line above line 502 on 2026-09-15 after this issue's last refine pass) —
  corrected throughout: `1212→1213`, `502→503`, `585→586`, `1265-1281→1266-1282`,
  `1279-1281→1280-1282`, `1265-1283→1266-1284`, `904→905`, `279-305→280-306`,
  `1161-1210→1162-1211`.
- Design section misattributed the `# noqa: BLE001 — "promotion must never fail the
  run"` guard to `_promote_template_artifact()`; it actually lives in the outer
  `promote_run_artifact()` (def at `:742`) — corrected.
- `cli/loop/runner.py:476` (Call Path, `run_foreground()`'s `executor.run()` call)
  corrected to `:479` (pre-existing minor drift, unrelated to the ENH-3471 shift).

## Resolution

- **Action**: improve
- **Completed**: 2026-09-16
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/persistence.py`: restructured `PersistentExecutor.run()`'s tail (`:1265-1285`) into one code path — `save_state()` and `archive_run()` each in their own `try`/`except Exception  # noqa: BLE001`, logged via `logger.warning` with the `workdir_vanished` note appended when applicable. Collapses the prior `workdir_vanished`/`else` branch split (the old `except OSError` was a strict subset). Matches the Design sketch and Program Design exactly — no deviations.
- `scripts/tests/test_fsm_persistence.py`: added four regression tests to `TestPersistentExecutor` per Implementation Step 2 — final `save_state()` failure still archives; `archive_run()` failure still saves final state; `failure_terminal=True` survives a final save failure; a non-terminal exit's final save failure leaves disk at `running` until `_reconcile_stale_running()` self-heals it.

### Verification Results
- Tests: PASS (`test_fsm_persistence.py`, `test_cost_ceiling_enforcement.py`, `test_usage_journal.py`, `test_ll_loop_execution.py`, `test_fsm_executor.py`, `test_cli_loop_background.py` — 830 passed; full suite `python -m pytest scripts/tests/` — 24471 passed, 50 skipped, 1 unrelated xdist worker-crash flake on `test_feat3323_sse_bridge.py` confirmed pre-existing and unrelated by re-running in isolation, where it passed)
- Lint: PASS (`ruff check`)
- Types: PASS (`mypy`)
- Format: PASS (`ruff format --check`)
- Integration: PASS (no other call sites reference the collapsed branch structure)

## Status

**Open** | Created: 2026-09-13 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-09-16T01:23:04 - `b06ee659-21ec-4b98-bb84-c79806e31e7c.jsonl`
- `/ll:verify-issues` - 2026-09-16T01:04:27 - `8bc49385-1641-422a-9ea4-71f61ae80d11.jsonl`
- Manual review rewrite - 2026-09-15 - corrected the stale-`running` claim (terminal exits already read `completed` via mid-run `_save_state()` on `state_enter`); added the test-injection constraint (blanket `save_state` mock crashes mid-run before the tail); rewrote Step 2 accordingly (final-call-only injection, non-terminal FSM + fresh persistence for the reconcile test); noted `resume()` shares the tail; completed the sketch's second warning; recorded the `failure_terminal`→`completed` on-disk quirk as out of scope.
- `/ll:verify-issues` - 2026-09-16T00:48:11 - `c5682d24-7c5a-42e9-b4d1-ac64f38c4408.jsonl`
- `/ll:confidence-check` - 2026-09-15T23:19:59 - `4aed0df2-a263-4d28-ae34-d555931852b6.jsonl`
- `/ll:verify-issues` - 2026-09-15T23:13:30 - `0f995d07-641d-467b-93d8-b6a178acbacb.jsonl`
- Manual review rewrite - 2026-09-15 - guard `save_state`/`archive_run` independently; collapse the two branches; add stale-`running` self-heal note and `failure_terminal` exit-code test; declare ENH-3473's dependency on this issue.
- `/ll:wire-issue` - 2026-09-15T22:32:31 - `74d0e714-5fa8-4d36-8d26-f70b1e11f439.jsonl`
- `/ll:refine-issue` - 2026-09-15T22:18:25 - `a0a3cae8-46b6-4741-b032-8859dea7a727.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:29:41 - `8cf1df9b-8fca-46d9-b751-f28d170c6572.jsonl`
- `/ll:refine-issue` - 2026-09-14T19:32:05 - `93b68600-9c57-4c65-a431-1e887e42f117.jsonl`
- `/ll:format-issue` - 2026-09-14T19:18:27 - `e03a4d3e-6e32-492e-b751-6c3a912f41aa.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:25 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`
