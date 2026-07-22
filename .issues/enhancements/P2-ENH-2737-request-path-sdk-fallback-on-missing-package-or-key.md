---
id: ENH-2737
type: ENH
title: 'orchestration.request_path: fall back to cli on missing anthropic package
  or API key'
priority: P2
status: done
captured_at: '2026-07-22T00:00:00Z'
completed_at: '2026-07-22T19:28:14Z'
discovered_date: '2026-07-22'
discovered_by: issue-size-review
parent: EPIC-2456
relates_to:
- ENH-2720
- EPIC-2456
- ENH-2719
labels:
- token-cost
- caching
- configuration
size: Medium
learning_tests_required:
- anthropic
confidence_score: 100
outcome_confidence: 92
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2737: orchestration.request_path — fall back to cli on missing anthropic package or API key

## Summary

Add a safe downgrade path inside `_resolve_request_path()` so that a config or
state resolving to `"sdk"`/`"batch"` never hard-fails a run when the `anthropic`
SDK is unimportable or `ANTHROPIC_API_KEY` is unset. This is a prerequisite for
flipping the global default (ENH-2720) but is independently shippable and
unblocked — it does not depend on ENH-2719's parity gate.

## Parent Issue

Decomposed from ENH-2720: Default-flip tranche — orchestration.request_path
cli → sdk/batch after parity verification.

## Motivation (from parent's codebase research)

`anthropic` is a hard runtime dependency (`scripts/pyproject.toml:48`) with no
`try/except ImportError` around any of the three `import anthropic` call sites
in `host_runner.py` (lines 1540, 1583, 1630). `dispatch_anthropic_request` only
catches `anthropic.APIError` (which `AuthenticationError` subclasses) and
converts that into the *state's* failed `ActionResult(exit_code=1)` rather than
rerouting to `"cli"`. `dispatch_batch_request` has no try/except at all — its
caller's bare `except Exception` also just fails the state. Any exception
outside those catches (e.g. a hypothetical `ImportError`) propagates uncaught
to the executor's top-level handler (`executor.py:772-773`) and ends the
**entire run** in `"error"` status. No API-key presence check happens before
attempting the SDK call anywhere today.

This means today, flipping the default to `"sdk"` would be unsafe on any host
missing the package or key — exactly the risk ENH-2720's Expected Behavior
section calls out as a hard requirement ("must never hard-break a host that
only has the CLI").

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (all line numbers
below re-verified current as of this pass, no drift from the figures above):_

- `_resolve_request_path()` has exactly two call sites in `executor.py`: the
  dispatcher branching condition (`elif action_mode == "prompt" and
  self._resolve_request_path(state) in ("sdk", "batch"):`, line 1584) and
  inside `_dispatch_live()` itself (`request_path =
  self._resolve_request_path(state)`, line 2040). The fallback only needs to
  change the single source-of-truth function (line 2006-2019); both call
  sites consume its return value unchanged.
- The **sdk** and **batch** paths fail differently today, which the fix must
  handle uniformly: `dispatch_anthropic_request`'s `import anthropic` (line
  1540) is fully unguarded — an `ImportError` there propagates past the
  function's only `except anthropic.APIError` clause, past `_dispatch_live`
  (no wrapping try/except around the direct sdk-path call), and up to the
  executor's top-level `except Exception as exc: return self._finish("error",
  ...)` handler, ending the **entire run**. The **batch** path's `import
  anthropic` (line 1583, inside `dispatch_batch_request`, itself unguarded) is
  one frame less severe: `_dispatch_live`'s batch-submission call site already
  wraps it in `try/except Exception as exc:` (comment: `# anthropic.APIError
  and friends`), converting the `ImportError` into a nonzero-exit
  `ActionResult` — that only fails the individual **state**, not the whole
  run, but still doesn't downgrade to `"cli"` and still surfaces as an
  unexpected failure rather than a working fallback.
- `ANTHROPIC_API_KEY` is never read directly anywhere in `host_runner.py` (or
  elsewhere in `little_loops`) — no call site does an explicit
  `os.environ.get("ANTHROPIC_API_KEY")` presence check today. Key validation
  is delegated entirely to the `anthropic` SDK's own `Anthropic()`
  constructor/API-call machinery, which itself reads `ANTHROPIC_API_KEY` from
  the environment by convention. This confirms the Proposed Solution's env-var
  presence check is a correct, cheap proxy for "will the SDK actually work"
  without needing to invoke the SDK or a live API round-trip.
- Config source locations for the two `request_path` fields referenced above:
  `OrchestrationConfig.request_path` (`scripts/little_loops/config/orchestration.py:86`,
  default `"cli"`) and `StateConfig.request_path`
  (`scripts/little_loops/fsm/schema.py:630`, default `None`).

## Decision (inherited from parent's `/ll:decide-issue` pass)

**Selected: Option A — fallback check inside `_resolve_request_path()`.**

Reuses the codebase's established "resolve, then dispatch once" idiom —
`_resolve_request_path()` already mirrors `state.model or self.run_model`, and
parallels `apply_host_cli_from_config()`/`resolve_host()`'s env-then-config-
then-probe resolution shape (`host_runner.py:1254-1327`). There is also a
direct precedent for the import-probe-and-downgrade mechanic itself:
`format_analysis_yaml`'s `try/except ImportError` fallback
(`issue_history/formatting.py:94-100`).

The rejected alternative (wrapping `_dispatch_live()` call sites in a
try/except-and-retry) has no structural precedent in the codebase for
retrying with a different dispatcher, and introduces duplicate-call and
state-mutation risk via the batch tracker's persisted `batch_id.json` write
mid-dispatch — do not build it that way.

## Proposed Solution

1. In `scripts/little_loops/fsm/executor.py:2006-2019` (`_resolve_request_path`),
   before returning `"sdk"`/`"batch"`, probe:
   - `anthropic` importability
   - `ANTHROPIC_API_KEY` presence (env var, matching
     `apply_host_cli_from_config`'s env-first precedent,
     `host_runner.py:1302-1327`)
   On either probe failing, downgrade the resolved value to `"cli"` before
   dispatch begins, so the state falls through the pre-existing
   `ActionRunner`/host-CLI subprocess branch untouched (`executor.py:1586-1618`).
2. Keep the probe cheap — import + env check, not a live API round-trip.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation — they are not optional cleanup:_

3. Update `_resolve_request_path`'s own docstring (`executor.py:2007-2014`,
   currently "Mirrors `state.model or self.run_model`") to describe the new
   probe/downgrade behavior.
4. Give the 5 pre-existing `TestRequestPathDispatchWiring` tests that assert
   `"sdk"`/`"batch"` dispatch actually occurs (`test_fsm_executor.py:9376,
   9408, 9470, 9508, 9544`) an explicit `ANTHROPIC_API_KEY` env fixture (e.g.
   `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")`) so the new probe
   doesn't silently downgrade them to `"cli"` and break their
   `mock_dispatch.called` / `mock_runner.calls == []` assertions in any shell
   lacking a real key. Without this, "remain green" (Acceptance Criteria) is
   only true by accident of the ambient test-runner environment.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` (`_resolve_request_path`, lines 2006-2019, including its docstring)

### Similar Patterns
- `scripts/little_loops/host_runner.py:1302-1327` (`apply_host_cli_from_config`) — env-then-config-then-probe resolution shape.
- `scripts/little_loops/issue_history/formatting.py:94-100` (`format_analysis_yaml`) — `try/except ImportError` downgrade precedent.
- `scripts/tests/test_issue_history_formatting.py:138-155` (`test_yaml_fallback_to_json`) — the closest existing test model for this exact fallback shape: calls the fallback-bearing function directly under a `patch("builtins.__import__", side_effect=mock_import)` block and asserts on the fallback return value, rather than exercising the whole executor pipeline.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` (`TestRequestPathDispatchWiring`, lines 9358-9578) — add fallback-specific tests: missing `anthropic` package (mock via `patch("builtins.__import__", side_effect=...)`, matching `test_transport.py:693,852` and `test_issue_history_formatting.py:138-152`'s convention — not `sys.modules` deletion) and missing `ANTHROPIC_API_KEY` (via `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)`), each asserting the resolved path downgrades to `"cli"` and the state completes via the normal `ActionRunner` path rather than erroring the run.
- `scripts/tests/test_fsm_executor.py` — **update, not just add**: the 5 existing tests `test_request_path_sdk_calls_dispatch_not_cli` (9376), `test_state_level_request_path_overrides_orchestration_default` (9408), `test_request_path_batch_submits_polls_and_clears_tracker` (9470), `test_request_path_batch_resumes_without_double_submit` (9508), `test_request_path_batch_timeout_leaves_tracker_for_resume` (9544) construct `OrchestrationConfig(request_path="sdk"|"batch")` and assert the SDK/batch dispatch mock was actually called — none currently sets `ANTHROPIC_API_KEY` or mocks anthropic-importability. Add a `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)` fixture to each so they keep exercising the sdk/batch path post-fallback instead of silently degrading to `"cli"` in key-less environments.
- `scripts/tests/test_host_runner_dispatch.py` — existing `test_api_error_returns_nonzero_exit_code` (line 88) mocks generic `anthropic.APIError`, not the missing-package/missing-key scenarios this issue adds; no change needed here since the downgrade now happens upstream in `_resolve_request_path`, before `host_runner` is ever called.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `_resolve_request_path()` / dispatch section currently states dispatch is "gated on `state.request_path or orchestration_config.request_path` resolving to `"sdk"`/`"batch"`... Default (`"cli"`) behavior is unaffected" with no mention of the new probe; add a sentence describing the importability/key-presence downgrade.
- `docs/ARCHITECTURE.md` — `### SDK/Batches Dispatch Path (orchestration.request_path)` section describes the `"cli"`/`"sdk"`/`"batch"` selection with no fallback mention; add the downgrade behavior.
- `docs/reference/CONFIGURATION.md` — `orchestration.request_path` description (~line 1149-1168) and the `deferred_tools`/cache-marking config note ("only consulted when `orchestration.request_path` is `"sdk"` or `"batch"`", ~lines 1508-1514) should note that a configured `"sdk"`/`"batch"` value can silently resolve to `"cli"` at runtime if the package/key probe fails, so those blocks can go inert without a config change.
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig` class docstring (lines 62-83) documents `request_path` semantics (`"cli"` default — unchanged behavior... `"sdk"`... `"batch"`...) with no mention of the automatic downgrade; update the prose.

## Acceptance Criteria

- A state/config resolving to `"sdk"` or `"batch"` when `anthropic` is not
  importable resolves to `"cli"` instead, and the run completes normally
  (no run-ending `"error"` status).
- Same behavior when `ANTHROPIC_API_KEY` is unset.
- New tests cover both cases; existing `TestRequestPathDispatchWiring` /
  `TestDispatchAnthropicRequest` / `TestDispatchBatchRequest` tests remain
  green — including the 5 pre-existing sdk/batch-path tests once they gain an
  explicit `ANTHROPIC_API_KEY` fixture (see Wiring Phase / Tests above).

## Impact

- **Priority**: P2 — unblocks ENH-2720's default flip; independently valuable as a safety net regardless of when the flip lands.
- **Effort**: Small — one function, two new test cases, plus updating 5 pre-existing tests with an `ANTHROPIC_API_KEY` fixture and a few doc/docstring touch-ups (no functional risk beyond the core change).
- **Risk**: Low — additive fallback only, no behavior change when the package/key are present.

## Labels

`token-cost`, `caching`, `configuration`

## Status

**Open** | Created: 2026-07-22 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-22T00:00:00Z - `ff0d9bfc-785a-4935-9790-005b2de0d1b8.jsonl`
- `/ll:ready-issue` - 2026-07-22T19:16:32 - `b117e310-a0fa-4b3a-8242-b6033d166e8d.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:00:00Z - `6bc04f7f-a66f-44b7-b307-e9347039f73e.jsonl`
- `/ll:wire-issue` - 2026-07-22T19:13:55 - `760dae9c-7068-45bc-a12b-75379a6c798d.jsonl`
- `/ll:refine-issue` - 2026-07-22T19:08:45 - `708a6680-4ab0-4055-8bdd-50eb31f153bf.jsonl`
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `04044445-94db-4521-b724-9e512c0e4211.jsonl`
