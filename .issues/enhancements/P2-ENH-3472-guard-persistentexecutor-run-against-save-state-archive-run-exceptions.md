---
id: ENH-3472
title: 'Guard PersistentExecutor.run() so a save_state/archive_run exception cannot discard an already-computed ExecutionResult'
type: ENH
priority: P2
status: open
discovered_date: '2026-09-13'
labels: []
parent: ENH-3468
---

## Summary

`PersistentExecutor.run()` (`fsm/persistence.py:1212`) wraps `FSMExecutor.run()` and, once that inner call returns a fully-formed `ExecutionResult`, calls `StatePersistence.save_state()` (`:502`) and `StatePersistence.archive_run()` (`:585`). Neither call is exception-guarded except inside the `terminated_by == "workdir_vanished"` branch (which only catches `OSError`). If either raises (e.g. disk full) outside that branch, the exception propagates out of `PersistentExecutor.run()` unhandled and discards the result — including the `events.jsonl`/`usage.jsonl` traces `archive_run()` was about to copy into `.loops/.history/`. This issue closes that gap: an already-computed result must survive a persistence-layer failure.

This child is independent of its siblings (ENH-3471, ENH-3473) — it does not touch `terminated_by` vocabulary or checkpoint artifacts, only the persistence call site's own exception safety.

## Current Behavior

`PersistentExecutor.run()` calls `StatePersistence.save_state()` and `StatePersistence.archive_run()` after `FSMExecutor.run()` returns; only the `terminated_by == "workdir_vanished"` branch is exception-guarded, and only against `OSError`. The `else` branch (`fsm/persistence.py:1279-1281`) has no exception handling at all — a `save_state()`/`archive_run()` failure (e.g. disk full) raises out of `PersistentExecutor.run()` uncaught, discarding the already-computed `ExecutionResult` along with the `events.jsonl`/`usage.jsonl` traces `archive_run()` was about to copy into `.loops/.history/`.

## Expected Behavior

A `save_state()`/`archive_run()` exception raised from the unguarded `else` branch is caught, logged, and does not propagate — `PersistentExecutor.run()` still returns the already-computed `ExecutionResult` to its caller, following the `except Exception  # noqa: BLE001` precedent cited in Design.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 2** in full, including its dedicated wiring/test item.

## Design

This codebase's convention for guarding a risky I/O/persistence call that "must never fail the run" is a final broad `except Exception` carrying a `# noqa: BLE001` comment stating the rule, after narrower exception types where relevant:
- `fsm/persistence.py:904` (`promote_run_artifact()`, three-tier `except (ManifestError, DataValidationError)` / `except OSError` / `except Exception  # noqa: BLE001 - promotion must never fail the run`, each branch logging and returning `None`)
- `fsm/persistence.py:85` (`# noqa: BLE001 — additive enrichment; default on`)
- `session_store/db.py:579,609` (`cli_event_context`, documented at `:504-511`)
- `cli/harness.py:83,112,118,1200`; `learning_tests/gate.py:79`; `worktree_utils.py:847`; `skill_expander.py:163`; `parallel/worker_pool.py:1945,1970`; `cli/sprint/run.py:303`

This is the applicable precedent for guarding `save_state()`/`archive_run()` in `PersistentExecutor.run()`'s unguarded `else` branch — log and continue, do not re-raise.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Correction: `cli_event_context` is not defined in `session_store/db.py` — that file exists but is only 133 lines and contains no `except Exception`/`noqa` at all. `cli_event_context` is actually defined in `scripts/little_loops/session_store/writers.py:497-621`, and its two `except Exception as exc:` sites are at `writers.py:579` and `writers.py:609` (the line numbers cited happen to match; only the file path is incorrect). Neither of those two `except` clauses carries a `# noqa: BLE001` comment — confirmed by grepping that file. `cli_event_context` instead implements a distinct contract: it separately guards the enter/exit analytics writes (each independently `logger.warning`-logged) while explicitly re-raising the wrapped body's own exceptions via `except BaseException: exit_code = 1; raise`.
- Additional `except Exception  # noqa: BLE001`-style guard sites beyond those cited, confirming the same convention: `worker_pool.py:456-459,920-923,1702-1706` use `with suppress(Exception):` (no logging) around `record_session_lifecycle_event`/`record_orchestration_run` calls; `cli/loop/signals.py:58-62`'s `_loop_signal_handler()` guards `PersistentExecutor.archive_run_only()` — the very same `save_state()`/`archive_run()` pair this issue targets — with a narrower `except OSError: pass` at the *call site* (outside `PersistentExecutor`), commented "a failed archive must not prevent exit." `FSMExecutor._finish()` (`fsm/executor.py:4292-4309`, `:4315-4336`) already guards its own analytics-sink writes (`record_loop_run_summary`, `record_usage_event`) with bare `except Exception: pass` (no log, no noqa) specifically so a sink failure at that point can't discard the already-computed run state — the same shape this issue's `else` branch fix follows.
- Note: `BLE` (flake8-blind-except, the rule `# noqa: BLE001` comments reference) is not in this repo's enabled ruff rule set (`scripts/pyproject.toml` `[tool.ruff.lint]` `select = ["E", "F", "W", "I", "UP", "B", "C4"]`) — the `# noqa: BLE001` comments are documentation of intent, not lint-enforced.

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- Additional guard-sites of the `except Exception ...  # noqa: BLE001` shape beyond those already enumerated: `cli/harness.py` — actual current lines are `88,113,142,148,1190,1828` (six sites, not four; the previously cited `83,112,118,1200` have drifted). `cli/artifact/{templatize.py:988,1286,1554; status.py:163; design_md.py:135; extract.py:231,317,323; dashboard.py:481; render.py:158,166; policy_builder.py:105}` — a CLI-handler sub-convention (`cmd_<name>(args, logger) -> int`) whose trailing broad except *surfaces* the failure (`logger.error(str(exc)); return 1`) rather than suppressing it — a different flavor from the log-and-continue shape this issue needs; not a template to copy.
- A second, closer-sibling convention exists that the issue's Design section does not yet cite: bare `except Exception: pass` with a `# Non-fatal (ENH-NNNN)` comment and no `noqa` marker, used in the same `fsm/` package `PersistentExecutor` wraps — `fsm/executor.py:2565-2584` (ENH-3204, credential-scope audit write), `fsm/executor.py:4288-4309` (ENH-2463, `record_loop_run_summary`), `fsm/executor.py:4311-4314` (ENH-2724, `record_usage_event`), and `runner_spec.py:318-333` (same ENH-3204 write, mirrored verbatim). Each carries a prose comment stating "a sink failure must never fail the loop run" immediately above the `try`, matching this issue's own rule, but without a `noqa: BLE001` marker — both this shape and the `noqa: BLE001` shape coexist in the codebase for the same underlying rule.
- Citation correction: the `# noqa: BLE001 - promotion must never fail the run` comment at `fsm/persistence.py:904` sits inside `_promote_template_artifact()` (def at :816), a helper `promote_run_artifact()` (def at :741) calls only for `artifact_mode == "template"` — not inside `promote_run_artifact()` itself, which has its own narrower `except OSError` at :809 with no bare `except Exception` of its own.
- `worktree_utils.py:137` carries a `# noqa: BLE001 — skip malformed files` guard distinct from this issue's cited `worktree_utils.py:847` (`merge_epic_branch_to_base()`, `# noqa: BLE001 — never let completion crash the caller`) — two separate sites in the same file, not one.
- Confirmed: `BLE` (flake8-blind-except) is absent from `scripts/pyproject.toml`'s only ruff config (`[tool.ruff.lint] select = ["E", "F", "W", "I", "UP", "B", "C4"]`) — repo-wide search found no other ruff config file. The `noqa: BLE001` comments remain documentation of intent, not lint-enforced.

## Program Design

### Signatures
- `PersistentExecutor.run(self, clear_previous: bool = True) -> ExecutionResult` (`scripts/little_loops/fsm/persistence.py:1212`) — wraps `FSMExecutor.run()` then calls `StatePersistence.save_state(self, state: LoopState) -> None` (`:502`) and `StatePersistence.archive_run(self, run_dir: Path | None = None) -> Path | None` (`:585`); the target of this change is the unguarded `else` branch at `:1279-1281`.
- `record_loop_run_summary(...)` (`scripts/little_loops/session_store/writers.py:1791`) — already writes its `loop_runs` row inside `_finish()`, which returns *before* the block this issue guards runs — so only the filesystem archive step (`state.json`/`events.jsonl` copy) is at risk here, not the DB row.

### Call Path
`PersistentExecutor.run()` → `run_foreground()` (`cli/loop/runner.py:476`, `try/finally` only, no `except`, `:467-489`) → `cmd_run()` (`cli/loop/run.py:659-673`, `try/finally` only) → `main_loop()` dispatch (`cli/loop/__init__.py:1088`, zero try/except) → `ll-loop` console-script boundary (`pyproject.toml:84`). Nothing intercepts a `save_state()`/`archive_run()` exception anywhere in this chain today — it surfaces as a raw traceback with default nonzero exit.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)

- `scripts/little_loops/parallel/worker_pool.py` (:111-126) — the proof-first-task gate check classifies `FAILURE_TERMINAL_EXIT_CODE` (2) vs. any other nonzero exit differently. Today, a `save_state`/`archive_run` crash coinciding with `failure_terminal=True` never reaches `runner.py`'s exit-code decision and surfaces as Python's default exit 1, logged as a generic "exited 1" warning instead of the expected "gate: blocked" info line; once guarded, the correct exit code 2 is reached [Agent 2 finding]
- `scripts/little_loops/learning_tests/gate.py` (:328-370) — the `ready-to-implement-gate` branch buckets non-0/non-2 exits as `"infra_failed"`, and the `proof-first-task` fallback branch (:365-370) falls through to an unconditional `return "passed"` for any exit code other than `FAILURE_TERMINAL_EXIT_CODE`. **Today this means a persistence crash coinciding with a `failure_terminal=True` result is silently misclassified as `"passed"`**; guarding the else branch fixes this misclassification as a side effect [Agent 2 finding]
- `scripts/little_loops/cli/queue.py` (:402, :432) — `RunnerResult.error = "terminal failure" if returncode == FAILURE_TERMINAL_EXIT_CODE else None`; today's crash yields `error=None` (indistinguishable from success at this field), corrected to `"terminal failure"` once guarded [Agent 2 finding]

No code change is required in these three files — they already handle exit code 2 correctly. Listed here because their *observed classification* of an existing edge case changes as a side effect of this fix; worth a one-line callout in the PR description.

### Tests

- `scripts/tests/test_fsm_persistence.py::test_run_archives_to_history_on_completion` (:1509) — a second happy-path structural template for the same code path, complementary to the already-cited `test_run_saves_final_state` (:915); the former exercises the `archive_run()` half of the guarded pair, the latter the `save_state()` half [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` (:1030, :1061) — existing end-to-end tests that construct a real `PersistentExecutor` and call `.run()` (unlike `test_cli_loop_lifecycle.py`/`test_cli_loop_background.py`, which fully mock the class); confirm these still pass unchanged since this fix is behavior-preserving on the success path [Agent 1 finding]

### Confirmed Not Affected (no action needed)

- No documentation anywhere describes the current crash-on-persistence-failure behavior, so no doc file goes stale from this fix [Agent 2 finding]
- No test asserts the current (pre-fix) propagation behavior, so nothing needs inverting or removing [Agent 3 finding]
- Other unguarded `else`-branch-shaped call sites exist in `fsm/persistence.py` (`archive_run_only()` :1161-1210, `_reconcile_stale_running()` :279-305, `save_state()` at :709) but are explicitly out of this issue's Scope Boundaries — reported for awareness only, not proposed as scope additions [Agent 2 finding]

## Implementation Steps

1. Guard `PersistentExecutor.run()`'s `save_state()`/`archive_run()` calls (`fsm/persistence.py:1279-1281`) following the `except Exception  # noqa: BLE001` precedent above — log the failure and return the already-computed `ExecutionResult` rather than letting the exception propagate.
2. Add a test in `scripts/tests/test_fsm_persistence.py` covering this branch (no existing test does — `TestWorkdirVanished` in `test_fsm_executor.py` (:14155+) only exercises a raw `FSMExecutor`, never `PersistentExecutor`). Follow the file's own post-construction method-assign convention (see `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects`, :960-968): set `executor.persistence.save_state = MagicMock(side_effect=RuntimeError("disk full"))` before calling `executor.run()`, and assert the result is still returned rather than an exception propagating.
3. `python -m pytest scripts/tests/test_fsm_persistence.py -v` passes.

## Tests

- `scripts/tests/test_fsm_persistence.py::test_run_saves_final_state` (:915) — closest existing structural template to extend from, though the new test targets the failure path rather than the happy path.
- Inline `side_effect=RuntimeError(...)` patching convention already used in `test_fsm_executor.py` (`test_survives_db_failure_during_summary` ~:3693-3699, a same-shape test ~:3780-3786, `test_survives_write_failure` :3888-3898) is the pattern to mirror for asserting the run still completes normally despite the injected failure.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Confirmed: no existing test in `test_fsm_persistence.py` patches `self.persistence.save_state`/`self.persistence.archive_run` with a `side_effect` from inside `PersistentExecutor.run()`'s final-state block (lines ~1250-1281) — only `test_drain_inbound_spoof_does_not_trigger_persistence_side_effects` (:928-968, a call-count integrity test, not failure-injection) touches persistence internals there.
- Closest precedent for injecting a failure on a `PersistentExecutor`-shaped archive/save method and asserting the caller survives it: `test_cli_loop_background.py::test_second_signal_swallows_archive_oserror` (:156-172) — sets `mock_executor.archive_run_only.side_effect = OSError("disk full")` directly on a `MagicMock()` attribute, then asserts both survival (`SystemExit(1)` still raised) and `assert_called_once_with(...)`. `FSMExecutor._finish()`'s own sink-failure tests (`test_finish_survives_record_loop_run_summary_failure` :3679-3699, `test_finish_survives_record_usage_event_failure` :3764-3787, `test_survives_write_failure` :3888-3898) all `patch("<fully-qualified-target>", side_effect=RuntimeError("db unavailable"))` around the whole `executor.run()` call and assert on the returned `ExecutionResult` field proving normal completion (`result.terminated_by`/`result.final_state`) — the shape to mirror for this issue's new `PersistentExecutor`-level test, patching at the target's defining module path.

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- Closest existing test template for this exact failure-injection shape: `test_fsm_executor.py::test_finish_survives_record_loop_run_summary_failure` and `::test_finish_survives_record_usage_event_failure` — both `patch("little_loops.session_store.record_<x>", side_effect=RuntimeError(...))` around the whole `executor.run()` call, then assert on the returned `ExecutionResult` (e.g. `result.terminated_by == "terminal"`) to prove the run still completed. Same package (`fsm/`), same "guarded call wraps the tail of the run and must not disturb the returned result" shape as this issue's target.
- Other same-shape failure-injection precedents: `test_advisor.py::test_failing_write_does_not_alter_outcome` (patches `write_advisor_consult` with a `side_effect`, asserts the returned outcome's fields are unaffected); `test_worker_pool.py::test_setup_worktree_failure_does_not_raise_recorder_error` and the inline-comment variant at `test_worker_pool.py:4533-4538` (patches a recorder function with `side_effect=RuntimeError(...)`, calls the guarded function with only a trailing `# must not raise` comment — no shared "assert does not raise" helper exists anywhere in the codebase; this shape relies on the absence of `pytest.raises`).
- Confirmed absence: `test_fsm_persistence.py::TestPersistentExecutor` (lines ~856-925) has tests for `test_run_creates_state_file`, `test_run_creates_events_file`, `test_run_saves_final_state`, etc., but none patches `save_state`/`archive_run` with a `side_effect` to exercise the currently-unguarded `else` branch — confirming Implementation Step 2's claim that no existing test covers this branch.

## Scope Boundaries

- **In scope**: Guarding the `save_state()`/`archive_run()` calls in `PersistentExecutor.run()`'s unguarded `else` branch (`fsm/persistence.py:1279-1281`) with a broad catch-and-log per the precedent cited in Design; the accompanying regression test.
- **Out of scope**: `terminated_by` vocabulary changes (ENH-3471), checkpoint/best-effort artifacts (ENH-3473), the already-guarded `workdir_vanished`/`OSError` branch.

## Impact

- **Priority**: P2 - Matches frontmatter; scoped to one call site's exception safety, independent of siblings ENH-3471/ENH-3473
- **Effort**: Small - One guard clause plus one regression test, per Implementation Steps
- **Risk**: Low - Additive exception handling around an existing unguarded branch; behavior-preserving for the success path
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-13 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-09-15T22:18:25 - `a0a3cae8-46b6-4741-b032-8859dea7a727.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:29:41 - `8cf1df9b-8fca-46d9-b751-f28d170c6572.jsonl`
- `/ll:refine-issue` - 2026-09-14T19:32:05 - `93b68600-9c57-4c65-a431-1e887e42f117.jsonl`
- `/ll:format-issue` - 2026-09-14T19:18:27 - `e03a4d3e-6e32-492e-b751-6c3a912f41aa.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:25 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`
