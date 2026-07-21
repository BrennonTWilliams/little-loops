---
id: FEAT-2716
type: FEAT
title: Wire live Anthropic SDK/Batches API dispatch into fsm/executor.py
priority: P2
status: done
captured_at: '2026-07-21T03:44:09Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
relates_to:
- FEAT-2673
- FEAT-2710
- EPIC-2456
confidence_score: 96
outcome_confidence: 66
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 14
completed_at: '2026-07-21T04:17:39Z'
---

# FEAT-2716: Wire live Anthropic SDK/Batches API dispatch into fsm/executor.py

## Summary

Neither `orchestration.request_path == "sdk"` (FEAT-2673) nor `== "batch"`
(FEAT-2710) has a live network call wired into `fsm/executor.py`'s state
dispatch. `host_runner.build_anthropic_request()` and
`host_runner.build_batch_request()` only build request kwargs — nothing in
`scripts/little_loops` calls `anthropic.Anthropic().messages.create(**kwargs)`
or `.messages.batches.create(**kwargs)` anywhere. FEAT-2673 is marked `status:
done` without this call ever having been added.

## Context

Discovered while implementing FEAT-2710. Its Confidence Check had already
flagged this exact gap as Concern #1 (re-verified true via a fresh grep for
`messages.create\|messages.batches` across `host_runner.py` — the only hit is
a docstring mention). FEAT-2710's implementation stopped at the same
infrastructure maturity level FEAT-2673 established (request-building +
config/schema/pricing/bookkeeping, no live dispatch) rather than
retrofitting the missing call under FEAT-2710's title, since building it well
is a materially larger, separate change to the core loop-execution path that
every FSM loop run goes through — not a "transport-only" tweak.

## Current Behavior

`fsm/executor.py`'s state-execution path (`FSMExecutor.action_runner.run(...)`,
called around line 1592) always dispatches prompt-mode states through the CLI
shell subprocess via `self.action_runner`, regardless of
`orchestration.request_path`. `state.request_path`/`orchestration.request_path`
are fully inert config values today — a full grep for `request_path ==` /
`.request_path` across `scripts/little_loops/` (excluding tests/docstrings/
schema) finds zero conditional branches anywhere.

## Expected Behavior

- `orchestration.request_path == "sdk"` (state-level override wins per
  FEAT-2710's resolved Open Question 1: `state.request_path or
  self.orchestration_config.request_path`, mirroring `state.model or
  self.run_model`) routes eligible prompt-mode state execution through a real
  `anthropic.Anthropic().messages.create(**build_anthropic_request(...))` call
  instead of the CLI subprocess, parsing the SDK response into the same result
  shape the CLI path produces today (`action_runner.run()`'s return contract).
- `orchestration.request_path == "batch"` submits via
  `anthropic.Anthropic().messages.batches.create(**build_batch_request(...))`,
  persists the returned `batch_id` via `fsm/batch_tracker.py`'s
  `BatchTracker.record_submitted()`, and polls for completion (with backoff)
  before feeding the result back through the same parse path. An interrupted
  run resumes polling from `BatchTracker.get_batch_id()` instead of
  double-submitting.
- Both paths thread `is_batch`/actual token usage through to
  `estimate_cost_usd()` (FEAT-2710 already added the `is_batch` param) and the
  F5 telemetry surfaces (`observability/tracing.py`) so cost/usage accounting
  stays accurate.
- Default (`request_path == "cli"`) behavior is completely unchanged.

## Motivation

This blocks the acceptance criteria of both parent features:
- FEAT-2673's promised 0.1x-read/1.25x-write prompt-caching discount can only
  be realized once requests actually flow through the SDK path with
  `cache_control` attached — today `build_anthropic_request()` is dead code
  from a runtime-behavior perspective.
- FEAT-2710's two unmet acceptance criteria (live batch submission, and
  resume-polling with no double-submit) are both blocked directly on this.

Until this lands, EPIC-2456's F1 cache-marking discount and the 50% batch
discount both exist as tested-but-unreachable code paths, not as realized
token-cost savings.

## Proposed Solution

- Introduce a real SDK dispatch call site — likely a new function alongside
  `build_anthropic_request()` in `host_runner.py` (e.g.
  `dispatch_anthropic_request()`) that calls
  `anthropic.Anthropic().messages.create(**request)` and normalizes the
  response into `action_runner.run()`'s existing return shape (output text,
  exit code equivalent, usage token counts).
- In `fsm/executor.py`, resolve the effective request_path per state
  (`state.request_path or self.orchestration_config.request_path`) and branch
  to the SDK/batch dispatch functions instead of `self.action_runner.run(...)`
  when it resolves to `"sdk"`/`"batch"` and `action_mode == "prompt"`.
- For `"batch"`: add the submit → persist `batch_id` → poll-with-backoff →
  retrieve → parse lifecycle, likely as a new module (poll loop) that uses
  `fsm/batch_tracker.py`'s `BatchTracker` for bookkeeping. Wire
  start/resume/teardown hooks through `cli/loop/lifecycle.py` alongside the
  existing `RateLimitCircuit` lifecycle hooks (per FEAT-2710's original wiring
  analysis).
- Eligibility guard: only latency-insensitive states/loops should opt into
  `"batch"` given its asynchronous nature — document this clearly, but don't
  hard-block it in code (config/loop-author's judgment call, same as today's
  `"sdk"` opt-in).

## Implementation Steps

1. Add a real `messages.create()` dispatch function for `request_path ==
   "sdk"`, response-shape-normalized to match `action_runner.run()`'s
   contract. Prove SDK response shape against the pinned `anthropic` SDK via
   a learning test first (mirror FEAT-2681's `.ll/learning-tests/anthropic.md`
   pattern).
2. Wire `fsm/executor.py`'s state-execution path to branch on the resolved
   `request_path`, dispatching to the new SDK call when eligible
   (`action_mode == "prompt"`, `request_path == "sdk"`).
3. Add the batch submit→poll→retrieve lifecycle using
   `host_runner.build_batch_request()` + `fsm/batch_tracker.py`'s
   `BatchTracker`, following `loops/rn-refine.yaml`'s init-state resume-branch
   convention (resume+exists → reuse; not-resume+exists → error; neither →
   fresh).
4. Wire `request_path == "batch"` into the same executor branch point, and
   the poll lifecycle into `cli/loop/lifecycle.py`.
5. Thread `is_batch=True` through to `estimate_cost_usd()` calls
   (`fsm/cost_graph.py`, `session_store.py`) for batch-originated usage
   events, and confirm `observability/tracing.py` shapes batch responses into
   the same four-field token-count shape SDK/CLI responses use.
6. Tests: SDK/batch dispatch integration tests (mock or real-shape response
   fixtures, no live network calls in CI); resume-polling regression;
   end-to-end request_path routing test in `test_fsm_executor.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Establish the `anthropic.Anthropic()` client mock boundary at
   `patch("little_loops.host_runner.anthropic.Anthropic")` — no existing test
   mocks this SDK client anywhere in the suite; follow the
   module-dotted-path-patch convention from `test_fsm_runners.py`'s
   `subprocess.Popen` mocking.
8. Add `TestCmdResumeSdkDispatchWiring` to `test_cli_loop_lifecycle.py`,
   mirroring `TestCmdResumeCircuitWiring`'s `mock_exec_cls.call_args.kwargs`
   assertion style, to prove the new dispatch object is threaded into
   `PersistentExecutor(...)`.
9. Add an `is_batch=True` end-to-end case to
   `test_session_store.py::TestBackfillUsageEvents` and extend
   `test_ll_loop_execution.py::TestEndToEndExecution` with a
   `request_path: sdk`/`batch` loop-YAML case asserting `mock_popen` is
   **not** called and the SDK mock is — the strongest regression guard for
   this issue's "default cli path is byte-identical" Acceptance Criterion.
10. Reword the stale gate-condition description strings in
    `config-schema.json` (lines 627, 639) and `docs/reference/CONFIGURATION.md`
    (`## deferred_tools`) that describe `request_path == "sdk"/"batch"` as if
    dispatch were already live; add the `## orchestration` section
    `CONFIGURATION.md` is still missing.
11. Add a `dispatch_anthropic_request()` entry to `docs/reference/API.md`'s
    `## little_loops.host_runner` section, and a note in `docs/ARCHITECTURE.md`'s
    `## Host Runner Layer` distinguishing the new SDK-client dispatch path
    from the existing `HostRunner`/subprocess mechanism.
12. Cross-link this issue from `EPIC-2456`'s children/success-metrics section
    and add a closure note to `FEAT-2673` acknowledging the live-dispatch gap
    it left open.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — `_run_action()`'s dispatch branch at
  the `self.action_runner.run(...)` call site (line 1592) needs to resolve
  `state.request_path or self.orchestration_config.request_path` and branch to
  the new SDK/batch dispatch before falling through to the CLI path.
  `_action_mode()` (line 1966) branches only on `action_type` today — confirmed
  via grep that `fsm/executor.py` has **zero** references to `.request_path`,
  `build_anthropic_request`, `build_batch_request`, or `BatchTracker`.
- `scripts/little_loops/host_runner.py` — add a new `dispatch_anthropic_request()`
  (or similar) alongside `build_anthropic_request()` (lines 1341–1420) and
  `build_batch_request()` (lines 1423–1466), which both explicitly document
  that they build kwargs only and perform no network call. Confirmed via grep
  that there is **no existing runtime `anthropic.Anthropic()` client
  instantiation anywhere in `scripts/little_loops`** — only docstring mentions
  (`host_runner.py:1357`) and test/spike-only references. This is genuinely
  the first production `anthropic` SDK client call site.
- `scripts/little_loops/fsm/batch_tracker.py` — `BatchTracker` (already built
  by FEAT-2710) is currently referenced nowhere outside its own module; its
  `record_submitted()`/`get_batch_id()`/`clear()` need live call sites.
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()`'s
  `RateLimitCircuit` construction block (lines 569–576:
  `circuit = RateLimitCircuit(...) if config.commands.rate_limits.circuit_breaker_enabled else None`,
  then injected as `PersistentExecutor(..., circuit=circuit, ...)`) is the
  exact config-gated-construction + constructor-injection pattern a new batch
  poll lifecycle hook should mirror.
- `scripts/little_loops/pricing.py:66` — `estimate_cost_usd(..., is_batch: bool = False)`
  already exists (appended, not inserted, so existing positional callers are
  unaffected) but both current call sites omit it.
- `scripts/little_loops/fsm/cost_graph.py:234` and
  `scripts/little_loops/session_store.py:2678` — both call `estimate_cost_usd()`
  with 5 positional args, omitting `is_batch`; neither site currently has any
  signal that a usage row came from the batch API.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/runners.py` — `ActionRunner` Protocol (line 36) /
  `DefaultActionRunner.run()` (line 95) define the `ActionResult` contract any
  new SDK/batch dispatch must normalize into.
- `scripts/little_loops/fsm/types.py:68` — `ActionResult` dataclass:
  `output, stderr, exit_code, duration_ms, usage_events, peak_rss_mb`.
  `usage_events` entries carry the four-field flat token shape
  (`input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_creation_tokens`
  + `model`) that `_run_action()` aggregates (executor.py:1620–1630).
- `scripts/little_loops/config/orchestration.py:86` —
  `OrchestrationConfig.request_path` (default `"cli"`) is fully modeled and
  schema-validated but unconsumed.
- `scripts/little_loops/fsm/schema.py:630` — `StateConfig.request_path`
  round-trips through `to_dict()`/`from_dict()` but is never read anywhere.
- `scripts/little_loops/observability/tracing.py` — `_FIELD_TO_OTEL` /
  `OTelAttributes.from_usage()` / `StampUsageEvent.usage_event()` all consume
  the same four-field flat usage shape; a live dispatch result must match it
  to interoperate without changes to these consumers.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `ActionRunner`,
  `ActionResult`, `FSMExecutor`, `RateLimitCircuit`, `PersistentExecutor`; no
  code change expected, but any renamed/new public symbol from this issue
  (e.g. a new `MockSDKDispatcher`-equivalent, or `dispatch_anthropic_request`
  if it should be publicly re-exported) needs adding here to stay consistent
  with existing re-export conventions.
- `scripts/little_loops/fsm/rate_limit_circuit.py` — `RateLimitCircuit` is the
  structural analog (`fcntl.flock`-guarded, atomic file-backed state) the new
  batch-poll lifecycle state should mirror; already referenced under Similar
  Patterns below, listed here as a dependency for the poll-lifecycle module.
- `scripts/little_loops/fsm/persistence.py`, `scripts/little_loops/cli/loop/run.py`,
  `scripts/little_loops/cli/loop/_helpers.py`, `scripts/little_loops/parallel/worker_pool.py`,
  `scripts/little_loops/parallel/orchestrator.py`, `scripts/little_loops/runner_spec.py`,
  `scripts/little_loops/subprocess_utils.py` — indirect consumers of
  `FSMExecutor`/`action_runner` dispatch or `host_runner` factories; none call
  `_run_action()`'s branch logic directly, so no code change is expected, but
  each is a regression-risk surface if `ActionResult`'s contract shifts and
  should be smoke-tested (existing test suites for each already exist and
  should stay green, not new coverage).

### Similar Patterns

- `host_runner.py`'s `build_*` factory convention — free functions returning
  plain dict kwargs, no network call, documented boundary ("that lifecycle is
  the caller's responsibility") — model the new dispatch function on this.
- `fsm/rate_limit_circuit.py`'s `RateLimitCircuit` — `fcntl.flock`-guarded,
  atomic (`tempfile.mkstemp` + `os.replace`) file-backed state; `BatchTracker`'s
  own docstring already says it mirrors this mechanism.
- `executor.py`'s circuit-breaker wiring shape — constructor injection
  (`circuit: RateLimitCircuit | None = None`, line 171) → pre-action check
  (`self._maybe_wait_for_circuit(state)`, ~line 2370) → post-error record
  (`self._circuit.record_rate_limit(...)`, ~lines 2259–2271) — the exact
  end-to-end pattern a batch-poll lifecycle hook should follow.
- `loops/rn-refine.yaml`'s `init` state (lines 64–121) — a single shell
  state's `if`/`elif`/`else` distinguishing `RESUME set AND dir exists` (reuse),
  `RESUME unset AND dir exists` (hard error, `exit 1`, BUG-2610 guard), and
  neither (fresh seed) — the closer structural analog for "already have
  `batch_id.json`? resume-poll : submit fresh" than `check_resume`'s two-gate
  binary-evaluator chaining (lines 123–178).

### Tests

- `scripts/tests/test_fsm_executor.py` — `MockActionRunner` (lines 33–109)
  satisfies the `ActionRunner` Protocol structurally; a new SDK/batch dispatch
  path needs an equivalent mock at the
  `anthropic.Anthropic().messages.create`/`.messages.batches.create` boundary,
  since FEAT-2716 branches *before* reaching `action_runner.run()`
  (executor.py:1592).
- `scripts/tests/test_batch_request_path.py` — existing FEAT-2710 batch
  request-path tests to extend with live-dispatch coverage.
- `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_pricing.py` —
  need `is_batch` coverage.
- `scripts/tests/test_fsm_schema.py`'s `TestModelStateConfig` (lines 2391–2440)
  — template for a new `TestRequestPathStateConfig`.
- `scripts/tests/test_rate_limit_circuit.py` — atomic-write/concurrent-access
  test patterns to mirror for the new batch poll state file.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeCircuitWiring`
  (line 1929) and `TestCmdResumeTransportWiring` (line 2007) are the exact
  `mock_exec_cls.call_args.kwargs`-inspection pattern to mirror for a new
  `TestCmdResumeSdkDispatchWiring` class, asserting whatever new
  circuit/dispatcher-like object this issue introduces is threaded into
  `PersistentExecutor(...)`.
- `scripts/tests/test_fsm_runners.py` — `TestDefaultActionRunnerShellPath`
  (line 214) mocks `little_loops.fsm.runners.subprocess.Popen` at the
  *importing module's* dotted path; the same convention applies to a new
  `patch("little_loops.host_runner.anthropic.Anthropic")` mock boundary,
  since no test in the suite currently mocks the `anthropic` SDK client at
  all (confirmed: zero `import anthropic` in any source file, no `conftest.py`
  stub) — this is a genuinely new mocking seam, not an extension of an
  existing one.
- `scripts/tests/test_session_store.py` — `TestBackfillUsageEvents` (line
  3124) covers the `estimate_cost_usd()` call site inside
  `_backfill_usage_events()` (session_store.py:2678); needs an `is_batch=True`
  coverage case alongside `test_pricing.py`/`test_fsm_cost_graph.py`.
- `scripts/tests/test_ll_loop_execution.py` — `TestEndToEndExecution` (line
  54) patches `little_loops.fsm.executor.subprocess.Popen` for a true
  end-to-end `ll-loop run` test; needs a new case with `request_path: sdk` (or
  `batch`) in the loop YAML, patching the SDK boundary instead of
  `subprocess.Popen`, asserting `mock_popen` is **not** called and the SDK
  mock is called instead — this is the strongest regression guard that the
  default `"cli"` path stays byte-identical per this issue's Acceptance
  Criteria.
- `scripts/tests/test_config_schema.py::test_orchestration_request_path_batch_in_schema`
  — existing schema-conformance test; if Implementation Step 3's
  poll-with-backoff introduces new config sub-keys, a corresponding new
  schema test is needed (not just the existing enum test).

### Documentation

- `.ll/learning-tests/anthropic.md` — already has `proven` claims for client
  construction and `cache_control` request-building; the two claims marked
  `untested` (live `messages.create()` round-trip; live cache-hit) are exactly
  what Implementation Step 1's learning test needs to newly prove.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — the `## deferred_tools` section (~line
  1495) and equivalent cache-marking-oracle prose both state *"Only consulted
  when `orchestration.request_path` is `"sdk"` or `"batch"` (FEAT-2710)"* in
  language written when both modes were schema-legal-but-inert; FEAT-2710's
  own Documentation section already flagged this as needing a dedicated
  `## orchestration` section covering `request_path`'s three values,
  eligibility rules, and (once this issue lands) the batch-poll lifecycle —
  that gap is still open and this issue is the natural trigger to close it.
- `scripts/little_loops/config-schema.json` lines 627 and 639 — the same
  stale gate-condition description strings (deferred-tools /
  cache-marking-oracle blocks) as above, at the schema-description level
  rather than the doc-prose level; both need rewording once "sdk"/"batch"
  are live dispatch modes instead of merely schema-valid.
- `docs/ARCHITECTURE.md` — the `## Host Runner Layer` section (~line 841)
  documents `host_runner.py` exclusively in terms of the `HostRunner`
  Protocol / CLI-subprocess `HostInvocation` shape; it doesn't mention
  `build_anthropic_request()`, `build_batch_request()`, or the new
  `dispatch_anthropic_request()`, which are a structurally distinct,
  non-`HostRunner`, non-subprocess dispatch path living in the same module.
  Needs a note distinguishing the two mechanisms once a real SDK client call
  site exists there.
- `docs/reference/API.md` — the `## little_loops.host_runner` section
  (~line 8124) needs a `dispatch_anthropic_request()` entry alongside the
  existing `build_anthropic_request()`/`build_batch_request()` documentation.
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` — has zero references
  to FEAT-2716 despite `relates_to: EPIC-2456` being set on this issue; the
  epic's F1/F5/F6 success-metric section implicitly assumes live dispatch
  exists. Add a reciprocal cross-link so the epic reflects the real blocking
  dependency.
- `.issues/features/P2-FEAT-2673-f1-cache-control-ephemeral-integration-and-cache-marking-cost-oracle.md`
  — marked `status: done` but contains no acknowledgment that its promised
  live SDK dispatch never shipped; consider a closure-note cross-link to
  FEAT-2716 once this issue lands, so the historical record is accurate.

### Configuration

- `config-schema.json:1568` — `orchestration.request_path` enum already
  includes `cli`/`sdk`/`batch` (added under FEAT-2710, asserted by
  `test_config_schema.py::test_orchestration_request_path_batch_in_schema`) —
  no schema change needed for the `batch` value itself.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — a second, independent
  schema surface for the per-state `request_path` override (separate file
  from `config-schema.json`, already flagged in FEAT-2710's Configuration
  section as "easy to miss"); confirm it stays in sync if any new
  sub-properties (e.g. batch polling backoff config) are added.

## Acceptance Criteria

- [x] `orchestration.request_path: sdk` actually dispatches via
      `anthropic.Anthropic().messages.create()` instead of the CLI
      subprocess, for eligible prompt-mode states. `FSMExecutor._dispatch_live()`
      (`fsm/executor.py:1997-2085`) branches to `host_runner.dispatch_anthropic_request()`
      when `_resolve_request_path(state) == "sdk"`; verified by
      `test_request_path_sdk_calls_dispatch_not_cli` and
      `test_state_level_request_path_overrides_orchestration_default`.
- [x] `orchestration.request_path: batch` submits via the Batches API, polls
      to completion, and returns results through the existing parse path
      (completes FEAT-2710's unmet AC). Verified by
      `test_request_path_batch_submits_polls_and_clears_tracker`.
- [x] Interrupted batch runs resume polling from a persisted `batch_id`
      instead of double-submitting (completes FEAT-2710's unmet AC).
      Verified by `test_request_path_batch_resumes_without_double_submit`
      and `test_request_path_batch_timeout_leaves_tracker_for_resume`.
- [x] Default (`"cli"`) behavior is byte-identical to today — verified by a
      regression test asserting the CLI dispatch path is untouched when
      `request_path` resolves to `"cli"` or is absent. See
      `test_request_path_cli_default_unaffected`.
- [x] F5/F6 telemetry (`observability/tracing.py`, per-state cost table)
      correctly reflects the 0.1x/1.25x cache discount and 0.5x batch
      discount for requests that actually took the SDK/batch path.
      `fsm/cost_graph.py:227,234` reads `row["is_batch"]` and threads it
      into `estimate_cost_usd(..., is_batch=is_batch)`; verified by
      `test_is_batch_row_applies_discount` and
      `test_missing_is_batch_defaults_to_full_price`.

## Impact

- **Priority**: P2 — blocks realizing the token-cost savings both FEAT-2673
  and FEAT-2710 were built to deliver; without this they're tested-but-dead
  code paths.
- **Effort**: Medium-High — touches the core `fsm/executor.py` dispatch path
  every FSM loop run goes through, plus a new async poll lifecycle.
- **Risk**: Medium — changes to shared execution-loop dispatch logic need
  careful regression coverage to avoid affecting the default CLI path; the
  batch poll lifecycle introduces new failure modes (stuck batches, partial
  results) that need explicit handling.

## Session Log
- `/ll:ready-issue` - 2026-07-21T04:46:42 - `b84944fe-c817-4cd3-ba89-3c3da6b98373.jsonl`
- `ll-auto` - 2026-07-21T04:17:39 - `d4623838-b304-4773-a76e-441d55a3f4db.jsonl`
- `/ll:ready-issue` - 2026-07-21T04:01:51 - `f5aaf22c-811d-462b-b31d-6ae7c262f366.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00 - `e4fe1818-4578-4dc7-afe5-bfd31d710f44.jsonl`
- `/ll:wire-issue` - 2026-07-21T03:58:42 - `344674d0-b075-4e87-965a-e05515ce435d.jsonl`
- `/ll:refine-issue` - 2026-07-21T03:52:04 - `b741f46c-5420-4468-b15c-a9c227c5b58d.jsonl`
- `/ll:capture-issue` - 2026-07-21T03:44:09Z - `4ea8aa10-aefa-44df-b782-f67007fcc175.jsonl`

---

## Status

**Done** | Created: 2026-07-21 | Priority: P2


---

## Resolution

- **Action**: implement
- **Completed**: 2026-07-21
- **Status**: Completed
- **Implementation**: Live SDK/Batches dispatch wired into `FSMExecutor._dispatch_live()`

### Files Changed
- `scripts/little_loops/fsm/executor.py` — `_resolve_request_path()` / `_dispatch_live()`
- `scripts/little_loops/host_runner.py` — `dispatch_anthropic_request()`, `dispatch_batch_request()`, `poll_batch_result()`
- `scripts/little_loops/fsm/cost_graph.py` — threads `is_batch` into `estimate_cost_usd()`
- `scripts/little_loops/fsm/batch_tracker.py`, `scripts/little_loops/fsm/persistence.py`,
  `scripts/little_loops/cli/loop/lifecycle.py`, `scripts/little_loops/cli/loop/run.py`,
  `scripts/little_loops/subprocess_utils.py`

### Verification Results
- `test_host_runner_dispatch.py`: 10/10 passed
- `test_fsm_executor.py -k "request_path or batch"`: 6/6 passed
- `test_fsm_cost_graph.py` batch-discount cases: passed
- All 5 Acceptance Criteria confirmed met against `HEAD`, re-verified via `/ll:ready-issue` on 2026-07-21

### Commits
- `ce7174b4` — "wire FSM executor to live SDK/Batches API dispatch (FEAT-2716)"
