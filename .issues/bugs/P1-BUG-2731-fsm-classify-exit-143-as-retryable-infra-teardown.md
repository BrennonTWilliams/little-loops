---
id: BUG-2731
title: FSM treats exit-143-after-result as a terminal action failure instead of
  retryable infra teardown, discarding in-flight subagent work
type: BUG
status: open
priority: P1
captured_at: '2026-07-21T22:40:00Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: BUG-2729
labels:
- subprocess
- automation
- headless
relates_to:
- BUG-2729
- BUG-2726
- ENH-2727
---

# BUG-2731: FSM treats exit-143-after-result as a terminal action failure instead of retryable infra teardown

## Summary

When a headless `claude -p` session ends its turn while subagents are still
running, the CLI tears down and reaps its still-running subagent children
(SIGTERM to the process group), exiting **143**. From the FSM's perspective the
action just "failed with exit 143" — `classify_failure()` is purely
text-pattern-based and 143 falls through every existing TRANSIENT/NON_RECOVERABLE
branch with no matching signature, so the run is ledgered as a hard failure and
downstream misattribution/confabulation follows ([[BUG-2726]], [[ENH-2727]]).

This is the **Secondary fix** half of [[BUG-2729]] (decomposed 2026-07-21): make
the FSM recognize the exit-143-after-`result`-event teardown signature and
retry/resume instead of recording a terminal failure. [[BUG-2730]] (sibling,
same decomposition) covers preventing the pattern in the first place via a
prompt contract; this issue covers the FSM-side safety net for when it still
happens.

## Parent Issue

Decomposed from [[BUG-2729]]: headless session end-turn-while-awaiting-subagents
self-terminates with exit 143, discarding in-flight work.

## Scope Note: session-ID-aware resume is deferred

[[BUG-2729]]'s confidence-check flagged the original "retry via `--resume
<session_id>` **or** re-run the action" language as an unresolved choice: no
`HostRunner` implementation supports resuming a *specific* prior session today
(`resume` is boolean-only everywhere it's threaded — `run_claude_command()`,
`HostRunner.build_streaming()` — mapping to `--continue` (Claude) or `--resume
latest` (Gemini)). Implementing session-ID resume requires new session-ID
capture + storage + host-runner plumbing across every host implementation, a
real cost driver, not a one-line change.

**This issue scopes the initial implementation to a plain re-run only** (per
the confidence-check's explicit recommendation). `scripts/little_loops/host_runner.py`
session-ID-aware resume plumbing is out of scope here and should be filed as a
follow-on enhancement if still wanted after this lands.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — the retry classification chain
  lives in `_route_next_state` (the `elif action_result.exit_code != 0 and
  _failure_type == ...` block at lines ~1412–1449). It already special-cases
  429/rate-limit (`_handle_rate_limit`, line ~2325) and `"api server error"`
  text (`_handle_api_error`, line ~2576, `_DEFAULT_API_ERROR_RETRIES` /
  `_DEFAULT_API_ERROR_BACKOFF` constants at lines 114–117). A new
  `exit_code == 143` branch is a further `elif` in this same chain, modeled
  structurally on `_handle_api_error` (flat per-state retry counter dict, same
  shape as `self._api_error_retries`).
- `scripts/little_loops/issue_lifecycle.py` — `classify_failure()` (line ~93)
  is purely text-pattern-based; it accepts a `returncode` parameter but its
  docstring says "available for future use" (line ~101) and the body never
  branches on it. A 143 classification must be keyed off `returncode` directly
  (SIGTERM leaves no stdout/stderr text signature to grep for), which is new
  territory for this function. `FailureType` enum (lines 79–90) is the model
  for the new value shape (currently exactly 3 members —
  `TRANSIENT`/`NON_RECOVERABLE`/`REAL`; no `INFRA_RETRY`-equivalent exists yet).
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` (line
  ~286) tracks `result_seen` as a **local variable** (set `True` at line ~496
  when a `type: "result"` stream-json event is parsed) but never returns it —
  the final `CompletedProcess(...)` (lines 543–548) carries only
  `args`/`returncode`/`stdout`/`stderr`. This must be surfaced to callers for
  the "143-after-result" gate to be derivable at all.
- `scripts/little_loops/fsm/runners.py` / `scripts/little_loops/fsm/types.py`
  — `DefaultActionRunner.run()` (line ~95, `is_slash_command=True` branch at
  line ~132) builds `ActionResult` (line ~192–199); `ActionResult` (defined
  `fsm/types.py:69`) has no `result_seen` field today. Add one following the
  `self._last_action_exit_code` idiom (`executor.py:247-251`, ENH-2522 — "remember
  a signal to make a downstream classification decision").
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` state (lines
  151–165) hardcodes the literal string `refine_failed` on both `on_failure`
  and `on_error` (`echo "${captured.input.output} refine_failed" >> ...`).
  This is the exact site that needs to branch (or interpolate) a distinct
  reason when the new 143 classification fires — coordinates with
  [[ENH-2727]], which already proposes extending this same site.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_manager.py:958` (`process_issue_inplace`) — a
  second consumer of `classify_failure(error_output, result.returncode)`,
  parallel to `fsm/executor.py:947`'s `_execute_state`. It treats
  `(FailureType.TRANSIENT, FailureType.NON_RECOVERABLE)` as "log, don't file a
  bug issue" — the new `FailureType` member for the 143 case must be added to
  this tuple check too, or a 143 kill on this (non-FSM) path still falls
  through to `create_issue_from_failure()` and files a phantom bug.
  `issue_manager.py` also calls `run_claude_command()` directly at lines 277,
  455, 627, 683, 844 (`run_with_continuation` and related retry loops) — a
  parallel non-FSM headless-session path with the same exit-143 exposure as
  the FSM path.
- `scripts/little_loops/cli/logs.py:1032,1126-1131` — a third consumer of
  `classify_failure()`, used by `ll-logs scan-failures` to skip clustering
  errors already classified as `TRANSIENT`/`NON_RECOVERABLE`. Same
  tuple-update requirement as `issue_manager.py` above — otherwise `ll-logs
  scan-failures --capture` will file spurious bug issues for 143-kill
  signatures it clusters.

### Similar Patterns (retry-classification precedent)

- `_handle_api_error()` (`executor.py:2576`) — flat per-state counter
  (`self._api_error_retries: dict[str, dict]`), flat backoff, emits
  `api_error_retry`/`api_error_exhausted` events, falls through to normal
  routing on exhaustion. This is the closest structural analog for the new
  143-classification handler (vs. `_handle_rate_limit`'s heavier short-burst +
  long-wait ladder).
- `StateConfig.retryable_exit_codes` (`executor.py:1457-1471`) — an existing
  **opt-in per-state** exit-code allowlist primitive. This does not by itself
  solve AC 3's "classifies as retryable infra teardown" requirement (it's
  opt-in/per-loop-author, not automatically populated with infra-signal
  codes) — the fix needs global default behavior, not per-loop opt-in.

### Tests

- `scripts/tests/test_fsm_executor.py` — `TestRateLimitCircuit`/API-error test
  group (~lines 6360–7446), e.g. `test_api_error_counter_reset_on_success` and
  `test_api_error_does_not_trigger_rate_limit_handler` (~7398–7429) use
  `MockActionRunner` with `.results` list + `runner.use_indexed_order = True`
  — the standard fixture idiom to model new 143-classification regression
  tests after (AC 2). Also `test_action_timeout_exit_code_124_routes_to_error`
  (~2763) and `test_shell_exit_code_1_routes_to_on_error_without_on_no`
  (~5093) as existing exit-code-specific test precedents.
- `scripts/tests/test_subprocess_utils.py` — new test asserting `result_seen`
  (once surfaced) is correctly propagated from `run_claude_command()`'s
  `CompletedProcess` return.
  `TestRunClaudeCommandResultBreak::test_breaks_on_result_event_without_pipe_eof`
  (~2356) already exercises the exact stream-json `"result"`-event → break
  code path this extends; `TestRunClaudeCommandModelDetection`'s
  `test_on_usage_callback_called_with_result_event` (~1596) and
  `test_result_event_is_error_appends_to_stderr` (~1691) show the
  `mock_process.stdout = io.StringIO(...)` fixture scaffolding to reuse.
- `scripts/tests/test_issue_lifecycle.py::TestClassifyFailure` (~676-820) — a
  single parametrized test method covering `classify_failure()`. No existing
  row varies `returncode` — needs a new `returncode=143` case once the
  function gains returncode-driven branching.
- `scripts/tests/test_issue_manager.py` — new/updated test covering
  `issue_manager.py:958`'s `classify_failure()` call once the new
  `FailureType` member is added to its transient/non-recoverable tuple check.
- `scripts/tests/test_builtin_loops.py` — literal `"refine_failed"` string
  assertions that may need updating if `skip_inflight` branches to a distinct
  reason code for the 143 case: `test_skipped_breakdown_...` (~2893-2904,
  breakdown dict counts), a ledger-line format assertion at ~4752 (`"ENH-0001
  refine_failed" in skipped`, note two-space separator matching the `echo`
  action's literal format).

### Documentation

- `docs/reference/EVENT-SCHEMA.md` (~line 363, `rate_limit_exhausted` section)
  — if the fix emits a new DES event for the 143-retry path (e.g.
  `infra_retry`), it needs a matching `###` section here, following the
  `rate_limit_exhausted`/`api_error_retry` pattern.
- `scripts/little_loops/observability/schema.py` (~lines 333-357,
  `RateLimitExhaustedVariant`/`ApiErrorRetryVariant` classes) — a new emitted
  event type needs a matching `@dataclass(frozen=True)` DES variant subclass
  here; this is what `ll-verify-des-audit` checks source emit-sites against.
- `docs/observability/des-audit.md` (~lines 54-57, variant→event-type table)
  — needs a new row for the new variant class if one is added.
- `docs/guides/LOOPS_REFERENCE.md` (~line 835 state-diagram edge, ~861-862
  state table) — documents `refine_failed` as `skip_inflight`'s only outcome;
  needs updating if `skip_inflight` branches to a distinct reason code for the
  143 case.

## Proposed Fix

Treat `exit_code == 143` + `result_seen` (usage captured) as `infra_retry`
rather than a terminal action failure: **re-run the action** (not
session-ID-resume — see Scope Note above), and ledger a distinct reason code
(coordinates with [[ENH-2727]]).

## Acceptance Criteria

- [ ] FSM classifies exit-143-after-result as retryable infra teardown with a
      distinct ledger reason (not `refine_failed`), with at least one retry
- [ ] Regression coverage: a simulated 143-after-result action routes to
      retry, not `on_error` terminal failure

## Session Log
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
- `/ll:issue-size-review` - 2026-07-21T23:15:00Z - `5d306492-7288-421c-83db-83a5420b5516.jsonl`
