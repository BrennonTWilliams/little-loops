---
id: BUG-2731
title: FSM treats exit-143-after-result as a terminal action failure instead of retryable
  infra teardown, discarding in-flight subagent work
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
confidence_score: 95
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
decision_needed: false
size: Very Large
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

## Current Behavior

When a headless `claude -p` session ends its turn while subagents are still
running, the CLI SIGTERMs its still-running subagent children and exits 143.
`classify_failure()` (`issue_lifecycle.py:93`) is purely text-pattern-based
against `error_output.lower()` and has no branch for exit code 143 (a clean
SIGTERM leaves no distinguishing stderr text to match). Every 143-after-result
kill falls through to the final `return (FailureType.REAL, "Implementation
error")` at line 238. `fsm/executor.py`'s dispatch chain in `_execute_state()`
then treats that `REAL` classification like an ordinary non-infra failure —
none of the `TRANSIENT`-only retry branches (`_handle_rate_limit`,
`_handle_api_error`) match, so it falls to the `else` at lines 1444-1449, the
queue advances, and the in-flight subagent work is discarded.

## Expected Behavior

The FSM should recognize the exit-143-after-`result`-event teardown signature
(SIGTERM following a captured stream-json `result` event, i.e. the subagent
had already produced output when it was reaped) and classify it as retryable
infra teardown rather than a terminal action failure: re-run the action
(plain re-run, not session-ID-resume — see Scope Note below) and ledger a
distinct reason code instead of `refine_failed`, so the in-flight work is
retried rather than silently discarded.

## Steps to Reproduce

1. Run an FSM loop state that dispatches a headless `claude -p` action which
   spawns subagents (e.g. `autodev.yaml`'s `refine_issue` state via
   `ll-parallel`/`ll-auto`).
2. Have the top-level session end its turn (emit a `result` stream-json
   event) while one or more subagents are still executing — the CLI SIGTERMs
   the process group and the action's subprocess exits with code 143.
3. Observe: `classify_failure(error_output, 143)` returns
   `(FailureType.REAL, "Implementation error")` (no branch matches exit code
   143), and `_execute_state()`'s dispatch chain routes this to the ordinary
   failure path — the queue advances past the issue and the in-flight
   subagent work (e.g. a partially-completed refine pass) is discarded rather
   than retried.

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

## Root Cause

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `classify_failure()`, line 93 (signature `def
  classify_failure(error_output: str, returncode: int) -> tuple[FailureType,
  str]:`)
- **Cause**: `classify_failure()` accepts `returncode` as a parameter but its
  docstring (line 101) literally reads "available for future use" — the
  function body (lines 106-238) never branches on it. Every classification is
  driven exclusively by regex/substring matching against
  `error_output.lower()`. No pattern anywhere in the function references
  "143", SIGTERM, or process-group teardown, so a 143-after-result kill (which
  leaves no distinguishing stderr text — it's a clean SIGTERM, not a crash)
  falls through every branch to the final `return (FailureType.REAL,
  "Implementation error")` at line 238. That `REAL` classification then
  reaches `fsm/executor.py`'s dispatch chain (`_execute_state`, elif chain at
  lines 1416-1449) and matches none of the `TRANSIENT`-only retry branches
  (`_handle_rate_limit`, `_handle_api_error`), so it falls to the `else` at
  lines 1444-1449 and is treated as an ordinary non-infra failure — the queue
  advances and the in-flight subagent work is discarded rather than retried.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — the retry classification chain
  lives inline in `_execute_state()` (the method starts at line 1227; there is
  **no separate `_route_next_state` function** — that name in earlier drafts
  of this issue was descriptive, not literal). The `elif action_result.exit_code
  != 0 and _failure_type == ...` chain runs at lines ~1416–1449, keyed off
  `classify_failure(_combined, action_result.exit_code)` at line 1418. It
  already special-cases 429/rate-limit (`_handle_rate_limit`, line 2325) and
  `"api server error"` text (`_handle_api_error`, line 2576,
  `_DEFAULT_API_ERROR_RETRIES` / `_DEFAULT_API_ERROR_BACKOFF` constants at
  lines 114–117). A new `exit_code == 143` branch is a further `elif` in this
  same chain, modeled structurally on `_handle_api_error` (flat per-state
  retry counter dict, same shape as `self._api_error_retries` at line 322).

  > ⚠ Anchor correction: prior text named `_route_next_state` as the
  > containing function; verified against source — no such function exists.
  > The chain is inline in `_execute_state`.
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

  > _Wiring pass added by `/ll:wire-issue`:_ `runners.py` has **six**
  > `ActionResult(...)` construction sites total (lines ~179, ~186, ~192, ~272,
  > ~281, ~361), not just the one at ~192. Lines 272/281 are the shell-command
  > branch (never goes through `run_claude_command()`, so `result_seen` is
  > inherently `False`/undefined there); line 361 is `SimulationActionRunner.run()`
  > (simulation-only path, also never touches `run_claude_command()`). All six
  > must get an explicit `result_seen=` value (not left to dataclass default by
  > accident) or the new field silently reads as unset for non-slash-command
  > paths. `scripts/little_loops/cli/loop/testing.py:76` (`ll-loop test`) is a
  > seventh, CLI-only construction site with the same decision to make.
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
- `StateConfig.retryable_exit_codes` (`executor.py:1457-1471`, field defined
  `fsm/schema.py:614`) — an existing **opt-in per-state** exit-code allowlist
  primitive. This does not by itself solve AC 3's "classifies as retryable
  infra teardown" requirement (it's opt-in/per-loop-author, not automatically
  populated with infra-signal codes) — the fix needs global default behavior,
  not per-loop opt-in.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `ActionResult.exit_code` (`fsm/types.py:69-87`) is already threaded
  end-to-end from every runner (`DefaultActionRunner`, `SimulationActionRunner`,
  `MockActionRunner`). Classifying exit 143 does **not** require a new
  `ActionResult` field to *read* the exit code — `_handle_api_error`'s call
  site already keys off `action_result.exit_code` the same way. A new field is
  only needed for the separate `result_seen` signal (see Integration Map
  above), not for the exit code itself.
- `self._last_action_exit_code` (ENH-2522, `executor.py:249`, set at lines
  1270 and 1323, consumed ~413-415) is a precedent for tracking a runner
  outcome as instance state and consuming it later in an unrelated helper —
  relevant if `result_seen` ends up threaded the same way rather than through
  `ActionResult`. Negative/signal exit codes already get special handling at
  line 1276 (`if result.exit_code is not None and result.exit_code < 0:`).
- `peak_rss_mb` (`fsm/types.py`, ENH-2453) is the closest precedent for the
  "add an optional field with a default, populate it from the runner, consume
  it in the executor" shape needed for `ActionResult.result_seen` — set at
  `executor.py:1785`/`1794`, read at `1661-1668`.
- New DES event variants (e.g. `InfraRetryVariant`) must be added to the
  `DES_VARIANTS` registration tuple at `observability/schema.py:571` onward
  (existing four entries at lines 611-614) in addition to defining the
  `@dataclass(frozen=True)` class — `_extract_type_defaults()` (line 646)
  walks `DES_VARIANTS`, so a defined-but-unregistered variant is silently
  invisible.
- `StateConfig` also has a generic `on_retry_exhausted` field (`fsm/schema.py`)
  alongside `retryable_exit_codes` — an existing per-state exhaustion-target
  pattern (tested around `test_retryable_exit_codes_none_has_no_effect`,
  `test_fsm_executor.py:5061`) worth checking for reuse before adding a new
  bespoke exhaustion field for the 143 case.
- `TestAPIErrorRetries` (`test_fsm_executor.py:7292-7439`) is the direct test
  class template — `_make_fsm()`/`_server_error_result()` helpers,
  `patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0)` to avoid
  wall-clock waits, and `MockActionRunner.always_return()` /
  `.set_result(action, exit_code=N)` for exhaustion vs. retry-then-succeed
  sequences.
- **Freshness re-check (2026-07-22)**: re-verified all four core anchors
  against current source given `executor.py`'s heavy recent edit volume — no
  drift. `classify_failure()` (line 93, `FailureType` enum unchanged at 3
  members: `TRANSIENT`/`NON_RECOVERABLE`/`REAL`, still ends at line 238 with
  `return (FailureType.REAL, "Implementation error")`), `_execute_state()`
  (line 1227, `classify_failure(...)` call now precisely at line 1418, the
  `NON_RECOVERABLE` branch at line 1437), `ActionResult` (`fsm/types.py:69`,
  still no `result_seen` field), and `run_claude_command()`'s unreturned local
  `result_seen` (`subprocess_utils.py:402/496/514/520`) are all confirmed
  as described above. [[ENH-2727]] is still `open` with the same unresolved
  two-way choice (new `skip_inflight_infra` state vs. single state with an
  interpolated reason) — the coordination note above remains accurate, no
  decision has landed on the sibling side yet.
- **Second freshness re-check (2026-07-22, `/ll:refine-issue`)**: re-verified
  all five core anchors again given continued edit volume on `executor.py`.
  No drift — `classify_failure()` (line 93, still falls through to
  `FailureType.REAL` at line 238), `_execute_state()`'s `classify_failure()`
  call site (line 1418) and elif chain (1419-1449), `ActionResult`
  (`fsm/types.py:69`, still no `result_seen` field), `run_claude_command()`'s
  unreturned local `result_seen` (`subprocess_utils.py:402/496/514/520`), and
  `_handle_api_error()`/constants (`executor.py:115,117,322,2576`) are all
  confirmed unchanged. A repo-wide grep for literal `143` in `executor.py`
  and `issue_lifecycle.py` still returns zero matches — the gap this issue
  targets remains exactly as described.

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

  > _Wiring pass added by `/ll:wire-issue`:_ confirmed via search — this
  > call site currently has **zero** direct tests (no `classify_failure`/
  > `FailureType` reference anywhere in `test_issue_manager.py` today), so this
  > is a genuinely new test, not an update to an existing one.
- `scripts/tests/test_ll_logs.py::TestScanFailures` (~2376+) — _Wiring pass
  added by `/ll:wire-issue`:_ the test file covering `cli/logs.py:1127-1130`'s
  `FailureType` exhaustiveness tuple (the third `classify_failure()` consumer
  named in "Dependent Files" above) was missing from this section entirely.
  `test_scan_failures_suppresses_transient_errors` (~2722) and
  `test_scan_failures_suppresses_non_recoverable_auth_errors` (~2751) are the
  existing behavioral tests (via CLI stdout assertions, not direct
  `FailureType` construction) to extend with a sibling case once the new
  member exists — otherwise `ll-logs scan-failures --capture` silently keeps
  clustering/filing bugs for 143-kill signatures with no regression coverage.
- `scripts/tests/test_fsm_executor.py::MockActionRunner` (~lines 35-115) —
  _Wiring pass added by `/ll:wire-issue`:_ the mock's three `ActionResult(...)`
  construction sites (indexed-order match ~82-88, pattern match ~93-99,
  default fallback ~101-107) don't currently accept or pass through a
  `result_seen` value. This must be wired (e.g. `result_data.get("result_seen",
  ...)`) before any new 143-classification test can script
  `result_seen=True, exit_code=143` via `MockActionRunner.set_result(...)` —
  otherwise the AC 2 regression test has no way to set up its own precondition.
- `scripts/tests/test_builtin_loops.py` — literal `"refine_failed"` string
  assertions that may need updating if `skip_inflight` branches to a distinct
  reason code for the 143 case: `test_skipped_breakdown_...` (~2893-2904,
  breakdown dict counts), a ledger-line format assertion at ~4752 (`"ENH-0001
  refine_failed" in skipped`, note two-space separator matching the `echo`
  action's literal format).

  > _Wiring pass added by `/ll:wire-issue`:_ three additional tests in this
  > file assert the `refine_failed` *state name* itself (not the ledger
  > string): `test_refine_failed_is_terminal` (~5502-5505),
  > `test_refine_issues_on_failure_routes_to_refine_failed` (~5525-5530),
  > `test_refine_issues_on_error_routes_to_refine_failed` (~5533-5537). These
  > are unaffected if the fix adds a parallel `infra_retry` reason but would
  > break if it renames/replaces the `refine_failed` state itself — relevant
  > because [[ENH-2727]] (the coordinating sibling for this same
  > `skip_inflight` site) proposes exactly that alternative
  > (`skip_inflight_infra` new state). Whichever approach lands here should
  > stay consistent with ENH-2727's choice.

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
- `docs/reference/API.md` (~lines 5375-5384, `#### ActionResult` heading) —
  _Wiring pass added by `/ll:wire-issue`:_ a hand-maintained verbatim
  reproduction of the `ActionResult` dataclass, already stale today (missing
  `usage_events`/`peak_rss_mb` that exist in current source). A new
  `result_seen` field is a further drift point on this snippet; update it
  alongside the dataclass change rather than letting it drift further.

## Proposed Solution

Treat `exit_code == 143` + `result_seen` (usage captured) as `infra_retry`
rather than a terminal action failure: **re-run the action** (not
session-ID-resume — see Scope Note above), and ledger a distinct reason code
(coordinates with [[ENH-2727]]).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The `skip_inflight` reason-code branching design (coordinating with
[[ENH-2727]]) has two viable resolutions, per ENH-2727's own Proposed Fix:

> **Selected:** Option A — new `skip_inflight_infra` state, per `/ll:decide-issue`
> evidence-based scoring (10/12 vs. 7/12; see Decision Rationale below).

**Option A**: Route `on_error` (and the new 143-classification path) to a
distinct state (e.g. `skip_inflight_infra`) that ledgers a different reason
code (`infra_error` or `refine_killed`), mirroring the ENH-2005
artifact-channel guidance that infra crashes be attributed separately.

> **Reason-code string decided (2026-07-22, `/ll:refine-issue`):**
> `refine_failed_infra` — neither `infra_error` nor `refine_killed`. See the
> "reason-code string resolved" research addendum below: it is the one
> precedent-aligned choice (stem-suffix on the existing `refine_failed`
> token, matching `record_gate_error`'s `GATE_FAILED_INFRA` convention,
> case-matched to `skip_inflight`'s lowercase format).

**Option B**: Keep the single `skip_inflight` state but interpolate a reason
string derived from the sub-loop verdict/exit code (e.g. `infra_retry` vs
`refine_failed`), avoiding a new state while still producing a distinct
ledger reason.

> ⚠ Correction (`/ll:decide-issue`, evidence-based): the "Recommended: Option
> B" note originally drafted here was based on a mistaken belief that the
> `refine_failed`-state-name tests (`test_refine_failed_is_terminal`,
> `test_refine_issues_on_failure_routes_to_refine_failed`,
> `test_refine_issues_on_error_routes_to_refine_failed`) belong to
> `skip_inflight`. Codebase evidence confirms those three tests exercise an
> unrelated `refine_failed` state in a different sub-loop
> (`refine-to-ready-issue.yaml`), not `autodev.yaml`'s `skip_inflight` — so
> Option A does not actually touch them. See Decision Rationale below for the
> corrected, scored comparison.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-22.

**Selected**: Option A — new `skip_inflight_infra` state

**Reasoning**: The codebase has four repeated, explicitly-tested precedents
for exactly this shape — `record_sub_loop_crash` (ENH-2005,
`rn-implement.yaml`), `record_crash` (`sprint-refine-and-implement.yaml`),
`record_node_crash` (`rn-refine.yaml`), and `record_gate_error`
(`rn-remediate.yaml`, FEAT-2552) — all splitting an infra/crash outcome into
a dedicated state distinct from its logic-failure sibling, converging on the
same downstream routing target, with a ready-made parametrized test template
(`test_diagnostic_record_states_tag_and_continue`). No comparable precedent
exists in `loops/*.yaml` for Option B's single-state-with-interpolated-reason
shape; the closest analog (`mark_deferred` in `rn-implement.yaml`) is a
different loop and would require `skip_inflight` to gain its first-ever
conditional branch while preserving a test that pins the literal echo output
(`test_skip_inflight_shell_action_writes_skipped_and_clears_inflight`,
`test_builtin_loops.py:4794-4820`) verbatim as its default case.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — new `skip_inflight_infra` state | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| B — interpolated reason string | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Option A: 4 direct precedents (`record_sub_loop_crash`, `record_crash`,
  `record_node_crash`, `record_gate_error`) all use the new-state shape for
  infra-vs-logic splits; reuse score 3/3. Touches ~10 `skip_inflight`-name
  test routing expectations, but none of the `refine_failed`-state-name
  tests (those belong to a different, unrelated state).
- Option B: only a cross-loop analog (`mark_deferred`); `skip_inflight` has
  no existing conditional structure to extend; reuse score 2/3.

### Codebase Research Findings (refine pass, 2026-07-22 continued) — reason-code string resolved

_Added by `/ll:refine-issue` — resolves the "still names two candidate
reason-code strings without picking one" open item from Confidence Check
Notes below._

Surveyed the literal token written by every existing infra-vs-logic split
`record_*` state in `loops/*.yaml`: `record_sub_loop_crash` writes
`SUB_LOOP_CRASH` (`rn-implement.yaml:1269`), `record_scores_missing` writes
`SCORES_MISSING` (`rn-implement.yaml:1281`), `record_node_crash` writes
`CRASH` (`rn-refine.yaml:373`), `record_crash` writes `crashed`
(`sprint-refine-and-implement.yaml`), and `record_gate_error` writes
`GATE_FAILED_INFRA` (`rn-remediate.yaml:590-591`). All four
non-`sprint-refine-and-implement` precedents use UPPERCASE tokens — a
different casing convention than `skip_inflight`'s own existing
`"${ID}  refine_failed"` (lowercase snake_case, `autodev.yaml:160`), so the
`record_*` precedents govern *shape* (a distinct state, per the Decision
Rationale above) but not casing.

`record_gate_error`'s `GATE_FAILED_INFRA` is the one precedent that derives
its infra token by suffixing `_INFRA` onto its sibling logic-failure state's
own token stem (`GATE_FAILED` → `GATE_FAILED_INFRA`) rather than inventing an
unrelated word — this is the closer structural analog to BUG-2731's
situation, where the sibling logic-failure token (`refine_failed`) already
exists and needs an infra counterpart. Applying the same stem-suffix
convention, case-matched to `skip_inflight`'s existing lowercase format,
yields **`refine_failed_infra`** — neither of the two originally-drafted
candidates (`infra_error`, `refine_killed`), and not adopted from ENH-2727
verbatim. Recommend `refine_failed_infra` as the literal string
`skip_inflight_infra` ledgers, over the two candidates named in Proposed
Solution above, on precedent-alignment grounds. This does not change the
already-decided Option A state-split shape — it only resolves the specific
string literal.

## Impact

- **Priority**: P1 — every headless FSM action that spawns subagents
  (`autodev.yaml`'s `refine_issue`, and any other loop state dispatching
  `claude -p` with subagent fan-out) is exposed; a misattributed `REAL`
  failure silently discards in-flight work and misleads downstream failure
  analysis ([[BUG-2726]], [[ENH-2727]]) rather than merely delaying it.
- **Effort**: Large — threading `result_seen` across 7 `ActionResult`
  construction sites, new returncode-driven branching in a previously
  text-only `classify_failure()`, and consistent updates across 3 independent
  consumers (`fsm/executor.py`, `issue_manager.py`, `cli/logs.py`); see
  Integration Map above.
- **Risk**: Moderate — broad change surface with partial existing test
  coverage (two of the three `classify_failure()` consumers have zero direct
  tests today), but the fix is additive (new classification branch + new
  state) rather than a rewrite of existing retry logic, per `outcome_confidence: 56`
  in Confidence Check Notes below.

## Acceptance Criteria

- [ ] FSM classifies exit-143-after-result as retryable infra teardown with a
      distinct ledger reason (not `refine_failed`), with at least one retry
- [ ] Regression coverage: a simulated 143-after-result action routes to
      retry, not `on_error` terminal failure

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-21 (supersedes the 2026-07-21 note below the
`decide-issue` pass; re-verified all core anchors against current source, no drift found)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Outcome Risk Factors
- Moderate depth: threading `result_seen` across 7 `ActionResult` construction
  sites (cross-module shared state) plus new returncode-driven branching in
  `classify_failure()`, a currently text-only function taking on new territory.
- Broad change surface: 3 independent `classify_failure()` consumers
  (`executor.py`, `issue_manager.py`, `cli/logs.py`) and 7 `ActionResult`
  construction sites all need consistent updates, or the fix silently degrades
  on some paths.
- Reason-code branching is now fully resolved: `/ll:decide-issue` selected
  Option A (new `skip_inflight_infra` state, see Decision Rationale above),
  and the specific literal string is decided as `refine_failed_infra` (see
  the "reason-code string resolved" addendum under Proposed Solution) — no
  remaining open detail on this axis.
- Partial test coverage: `issue_manager.py`'s `classify_failure()` call site
  has zero existing tests today, and `cli/logs.py`'s FailureType
  exhaustiveness check has no regression coverage against `ll-logs
  scan-failures --capture`.

## Session Log
- `/ll:refine-issue` - 2026-07-22T02:53:11 - `7f3d9a33-9486-4122-8fd1-85fd59741abd.jsonl`
- `/ll:refine-issue` - 2026-07-22T02:29:50 - `7f3d9a33-9486-4122-8fd1-85fd59741abd.jsonl`
- `/ll:format-issue` - 2026-07-22T02:22:40 - `7ea1a881-92d6-422c-9c30-8553cb4e5bac.jsonl`
- `/ll:confidence-check` - 2026-07-21T23:20:00Z - `15ba6c8e-64eb-4e39-8901-5c5beaed525a.jsonl`
- `/ll:decide-issue` - 2026-07-22T01:32:33 - `eb732e0f-1fa2-4a36-bfd1-0fe9dff17cf1.jsonl`
- `/ll:refine-issue` - 2026-07-22T01:28:07 - `eb732e0f-1fa2-4a36-bfd1-0fe9dff17cf1.jsonl`
- `/ll:refine-issue` - 2026-07-22T01:25:57 - `f517734b-992e-472a-a422-6cb494d8620d.jsonl`
- `/ll:confidence-check` - 2026-07-21T22:50:00Z - `7ff26f6b-a531-4e0e-a679-67ace91583a3.jsonl`
- `/ll:wire-issue` - 2026-07-22T01:18:47 - `857114c3-c203-4236-8314-9735ece15812.jsonl`
- `/ll:refine-issue` - 2026-07-22T01:12:25 - `a884d839-8182-429a-886b-8ab0b07b3e64.jsonl`
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
- `/ll:issue-size-review` - 2026-07-21T23:15:00Z - `5d306492-7288-421c-83db-83a5420b5516.jsonl`
