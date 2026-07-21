---
id: FEAT-2716
type: FEAT
title: Wire live Anthropic SDK/Batches API dispatch into fsm/executor.py
priority: P2
status: open
captured_at: '2026-07-21T03:44:09Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
relates_to:
- FEAT-2673
- FEAT-2710
- EPIC-2456
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

## Acceptance Criteria

- [ ] `orchestration.request_path: sdk` actually dispatches via
      `anthropic.Anthropic().messages.create()` instead of the CLI
      subprocess, for eligible prompt-mode states.
- [ ] `orchestration.request_path: batch` submits via the Batches API, polls
      to completion, and returns results through the existing parse path
      (completes FEAT-2710's unmet AC).
- [ ] Interrupted batch runs resume polling from a persisted `batch_id`
      instead of double-submitting (completes FEAT-2710's unmet AC).
- [ ] Default (`"cli"`) behavior is byte-identical to today — verified by a
      regression test asserting the CLI dispatch path is untouched when
      `request_path` resolves to `"cli"` or is absent.
- [ ] F5/F6 telemetry (`observability/tracing.py`, per-state cost table)
      correctly reflects the 0.1x/1.25x cache discount and 0.5x batch
      discount for requests that actually took the SDK/batch path.

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
- `/ll:capture-issue` - 2026-07-21T03:44:09Z - `4ea8aa10-aefa-44df-b782-f67007fcc175.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
