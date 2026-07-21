---
id: FEAT-2710
type: FEAT
title: Message Batches API request path (50% discount on batchable automation)
priority: P2
status: open
captured_at: '2026-07-21T02:03:13Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- caching
- orchestration
- sdk
relates_to:
- EPIC-2456
- FEAT-2673
- FEAT-2598
- ENH-2687
learning_tests_required:
- anthropic
confidence_score: 80
outcome_confidence: 68
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 15
score_change_surface: 18
---

# FEAT-2710: Message Batches API request path (50% discount on batchable automation)

## Summary

Add a `"batch"` request path alongside FEAT-2673's SDK code path (`orchestration.request_path == "sdk"`). The Anthropic Message Batches API applies a flat **50% discount to both input and output tokens** and stacks with prompt caching. Neither token-cost plan document considered it (all "batch" references are the Tier 0 edit-batching hook) — yet it is a larger guaranteed saving than most individual F-features, applying to every request routed through it rather than only to ≥8K prompts (F4) or cache-hit prefixes (F1).

## Motivation

little-loops has a large latency-insensitive surface that already runs asynchronously: `ll-auto` backlog processing, verification / adversarial-verify loops, eval harness runs, `ll-queue run` dequeues, and FEAT-2598's soft-threshold background summarizer. None of these need sub-minute responses; all of them pay full-price tokens today. A guaranteed 50% on that whole surface likely exceeds any single remaining EPIC-2456 child.

## Current Behavior

All requests — interactive and background — go through the CLI shell path or (post-FEAT-2673) the synchronous SDK path at full per-token price.

## Expected Behavior

An opt-in `orchestration.request_path == "batch"` (or per-loop/per-state `request_path: batch` override) submits eligible requests via `client.messages.batches.create()`, polls for completion, and feeds results back through the same result-parsing path. Interactive sessions and latency-sensitive states are unaffected.

## Proposed Solution

- Extend `build_anthropic_request()` in `host_runner.py` (FEAT-2673) with a batch submission wrapper — request shape is identical; only transport differs.
- Polling loop with backoff; persist batch IDs under `${context.run_dir}/` so an interrupted run can resume polling rather than resubmit.
- Eligibility guard: only states/loops explicitly marked batchable (config or loop YAML flag); never default-on.
- Cost telemetry: emit the discounted pricing through the existing F5/F6 surfaces (`observability/tracing.py`, per-state cost table) so `ll-ctx-stats` shows the batch discount explicitly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`build_anthropic_request()` is greenfield for dispatch**: `host_runner.py:1282-1361` only assembles Anthropic Messages API request kwargs (a plain `dict[str, Any]`) — it never calls `anthropic.Anthropic().messages.create(**kwargs)`. No code anywhere in `scripts/little_loops` currently performs that network call, so there is no existing "sdk" dispatch path to fork into a "batch" variant; both would need to be added together (or this issue should assume FEAT-2673's dispatch call lands first).
- **`orchestration.request_path` is unvalidated today**: `config/orchestration.py:81` declares `request_path: str = "cli"` with no enum validation in `from_dict()` (lines 85-93); `config-schema.json:627,639` only documents `"cli"`/`"sdk"` in description text, not a JSON Schema `enum`. Adding `"batch"` means adding schema validation, not just a new accepted string.
- **No polling/backoff-loop precedent exists in the codebase** (`grep -r "time.sleep|backoff|exponential"` across `scripts/little_loops` returns nothing production-side). The closest analog is `fsm/rate_limit_circuit.py`'s `RateLimitCircuit` class (lines 30-135): file-backed state with `fcntl.flock`-guarded atomic read-modify-write (tempfile + `os.replace()`), a monotonic `max()`-merged `estimated_recovery_at`, and a 1h `is_stale()` cutoff. A batch-status poller could mirror this bookkeeping shape (batch_id + submitted_at + estimated_recovery_at in a small JSON file) while keeping the actual Anthropic API poll call in a separate transport module — mirrors this module's existing split between detection (`issue_lifecycle.classify_failure`) and backoff bookkeeping (`RateLimitCircuit`).
- **`${context.run_dir}` persistence precedent**: `fsm/persistence.py`'s `StatePersistence`/`PersistentExecutor` (class starting line 391/629) already reads `context.get("run_dir", "")` to locate per-run artifacts (`usage.jsonl`, `messages.jsonl`, `summary.json`). `loops/rn-refine.yaml`'s `init` state (lines 63-109) shows the established resume convention: three-way branch on `(resume flag set?, prior state dir exists?)` — resume+exists → reuse; not-resume+exists → hard error refusing to clobber (BUG-2610 precedent); neither → fresh seed. A `batch_id.json` under `${context.run_dir}/` should follow this same branch shape on resume.
- **`pricing.py` has no multiplier mechanism to extend**: `MODEL_PRICING` (lines 10-55) is a flat per-model dict of four token-type dollar rates (`input`/`output`/`cache_read`/`cache_creation`); `estimate_cost_usd()` (lines 58-78) does a weighted sum and returns `None` (not a raise) on an unrecognized model. There is no existing `0.5 *` multiplier pattern anywhere in the file — the codebase's convention is to bake discount ratios directly into the per-token-type rate table (e.g. `cache_read` ≈ 0.1× `input`). A batch discount likely needs either a parallel `batch` rate table (doubling the dict) or a new multiplier parameter threaded through `estimate_cost_usd()`'s signature — worth an explicit decision before implementation (see Implementation Steps below).
- **`fsm/schema.py` per-state override precedent**: `State` dataclass already carries `model: str | None = None` at line 566 as a per-state escape hatch over loop/config-level defaults, with `to_dict()` (line 574+) conditionally including it only when non-`None`. A new `State.request_path: str | None = None` field should follow this identical shape.
- **No mocked-SDK test precedent — tests assert on returned dict shape instead**: `test_cache_control.py`'s `TestBuildAnthropicRequest` class constructs real lightweight collaborators (`FragmentStore()`, `ToolDefinition`) and asserts directly on `build_anthropic_request()`'s returned dict (e.g. `request["tools"][-1]["cache_control"]`) rather than patching `anthropic.Anthropic`. One test (line 273) imports real SDK type modules (`anthropic.types.tool_search_tool_bm25_20251119_param`) to validate shape compatibility. Batch-transport tests should follow the same convention — assert on request/poll-state shape, import real `anthropic.types.message_batch_*` types if they exist, rather than mocking the client.
- **Learning-test precedent (FEAT-2681)**: `.ll/learning-tests/anthropic.md` records `pass`/`untested` assertions for the `anthropic` SDK target, appended (never overwritten) to the existing record. Live network round-trips that can't be exercised without `ANTHROPIC_API_KEY` are recorded as `untested`, not `fail` — the batch submit→poll→retrieve learning test should follow this same pattern: prove SDK-side request/param shape acceptance as `pass`, record the live batch round-trip as `untested` if no API key is available in the proving environment.

## Implementation Steps

1. Learning test proving batch submit → poll → retrieve round-trip with the pinned `anthropic` SDK (mirror FEAT-2681's pattern at `.ll/learning-tests/anthropic.md` — append new assertions, don't overwrite; expect `untested` for the live round-trip without an API key).
2. Batch transport wrapper in `host_runner.py` alongside `build_anthropic_request()` (lines 1282-1361) + `orchestration.request_path` enum extension in `config-schema.json` (currently unvalidated free-text at `config/orchestration.py:81`, `config-schema.json:627,639`).
3. Loop-YAML `request_path` per-state override in `fsm/schema.py` — follow the existing `State.model: str | None = None` pattern (line 566) and its conditional `to_dict()` inclusion.
4. Batch-status poll/backoff bookkeeping — new module or extension mirroring `fsm/rate_limit_circuit.py`'s `RateLimitCircuit` (lines 30-135: `fcntl.flock`-guarded atomic file writes, monotonic recovery-time merge); persist `batch_id`/`submitted_at` under `${context.run_dir}/`, following `loops/rn-refine.yaml`'s init-state resume branch (resume+exists / not-resume+exists=error / neither=fresh).
5. Pricing: batch multiplier in `pricing.py` — decide between a parallel `batch` rate table (mirrors existing `MODEL_PRICING` per-token-type shape) vs. a multiplier parameter threaded through `estimate_cost_usd()` (lines 58-78); no existing precedent for either, since all current discounts are baked into flat per-token-type rates.
6. Tests: transport unit tests asserting on returned request/poll-state dict shape (mirror `test_cache_control.py`'s `TestBuildAnthropicRequest` — no SDK client mocking); resume-polling regression in `test_fsm_persistence.py`; pricing multiplier tests in `test_pricing.py`; per-state schema tests in `test_fsm_schema.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Extend `estimate_cost_usd()`'s new batch-multiplier parameter with a **default value appended at the end of the signature** (not inserted) — `fsm/cost_graph.py:234` and `session_store.py`'s `_backfill_usage_events()` both call it positionally and would break on an inserted param.
8. Add a `request_path` property block to `fsm/fsm-loop-schema.json` (separate schema from `config-schema.json`, covers loop-YAML `StateConfig`) alongside the existing `model` block — easy to miss since it's a sibling file, not the one already listed as "Files to Modify".
9. Route `fsm/executor.py`'s state-execution path and `cli/loop/run.py`'s loop invocation to the batch transport when `request_path == "batch"`; wire batch-poll lifecycle (start/resume/teardown) through `cli/loop/lifecycle.py` alongside the existing `RateLimitCircuit` lifecycle hooks.
10. Update `docs/reference/CONFIGURATION.md`'s two `request_path == "sdk"` gate-condition sentences (cache-marking oracle, deferred-tools blocks) to account for `"batch"` as a third value; update the `OrchestrationConfig.request_path` docstring in `config/orchestration.py` and the mirrored `config-schema.json:627,639` description strings.
11. Add `"batch"` enum coverage to `test_config.py`'s `TestOrchestrationConfig`/`TestBRConfigOrchestration` and `test_config_schema.py` (mirror `test_orchestration_host_cli_in_schema`); add a `test_rate_limit_circuit.py`-style test for batch_id bookkeeping.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/host_runner.py` — add batch-submission wrapper alongside `build_anthropic_request()` (lines 1282-1361)
- `scripts/little_loops/config/orchestration.py:81,85-93` — add `"batch"` to `request_path` and validate against an enum
- `scripts/little_loops/config-schema.json:627,639` — add `"batch"` to the `orchestration.request_path` JSON Schema enum
- `scripts/little_loops/fsm/schema.py` — add `State.request_path: str | None = None` (pattern: `State.model` at line 566)
- `scripts/little_loops/pricing.py:10-78` — add batch discount (parallel rate table or multiplier param)
- `scripts/little_loops/fsm/persistence.py` (`StatePersistence`/`PersistentExecutor`, class starting line 391/629) — persist/read `batch_id` under `${context.run_dir}/`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — sibling JSON Schema for FSM loop YAML `StateConfig`; needs a new `"request_path"` property block alongside the existing `"model"` block (lines 516-519), following its "which action types it applies to / WARNING if set on inapplicable type" convention

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/cost_graph.py:229-238` — calls `estimate_cost_usd()` per invocation row; any pricing signature change must be threaded through here **positionally-safe only if the new param is appended with a default**, not inserted
- `scripts/little_loops/session_store.py` (`_backfill_usage_events()`) — also calls `estimate_cost_usd()` positionally while backfilling `usage_events` rows from transcript `message.usage` blocks; same positional-signature risk as `cost_graph.py`. Batch-discount awareness here needs either a new `usage_events` column (e.g. `is_batch`) or inference from context, since raw transcript usage blocks are the only per-turn source
- `scripts/little_loops/observability/tracing.py` — token-field-agnostic OTel shaping; needs batch response parsing to land token counts in the same four-field shape (`input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_creation_tokens`) to work unmodified
- `scripts/little_loops/fsm/executor.py` — creates `PersistentExecutor` instances and reads `State`; the state-execution path that must route to the new batch transport when `request_path == "batch"`
- `scripts/little_loops/cli/loop/run.py` — wires `OrchestrationConfig` and `PersistentExecutor` together for loop runs; the CLI entry point where a batch-mode run is actually invoked

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — manages `RateLimitCircuit`/persistence lifecycle; batch-poll bookkeeping likely needs equivalent lifecycle hooks (start/resume/teardown)
- `scripts/little_loops/cli/loop/_helpers.py` — assembles the per-state cost table CLI output from `cost_graph.py`; should surface the batch discount in its displayed cost breakdown

### Similar Patterns
- `scripts/little_loops/fsm/rate_limit_circuit.py:30-135` (`RateLimitCircuit`) — file-backed backoff bookkeeping to mirror for batch-poll state
- `scripts/little_loops/loops/rn-refine.yaml:63-109` — `${context.run_dir}` resume-branch convention to mirror for batch_id persistence
- `scripts/tests/test_config_schema.py:724-743` (`test_orchestration_host_cli_in_schema`) — the exact structural-assertion pattern to mirror for a new `test_orchestration_request_path_batch_in_schema` test (checks `"batch" in orch["properties"]["request_path"]["enum"]`)
- `scripts/tests/test_fsm_schema.py:2391-2440` (`TestModelStateConfig`) — the 7-test shape (`defaults-to-None` / `accepts-value` / `to_dict`-includes-when-set / excludes-when-none / `from_dict`-with-value / without-value / round-trip) to duplicate for `State.request_path`

### Tests
- `scripts/tests/test_cache_control.py` (`TestBuildAnthropicRequest`, `TestDefaultBehaviorUnchanged` lines 291-305) — existing coverage of `build_anthropic_request()` and the `request_path` two-value enum pattern (`"cli"`/`"sdk"`) to extend with `"batch"`; extend or add sibling `test_host_runner.py` batch tests without SDK client mocking
- `scripts/tests/test_pricing.py`, `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_fsm_schema.py`, `scripts/tests/test_fsm_persistence.py` — existing coverage for the components this issue extends

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` (`TestOrchestrationConfig` line 3093, `TestBRConfigOrchestration` line 3155) — direct dataclass tests for `OrchestrationConfig.request_path`, missed by the original refine-issue pass; needs a `"batch"` case
- `scripts/tests/test_config_schema.py` — general schema validation tests; needs a `"batch"` enum acceptance case once `config-schema.json`'s `request_path` enum is extended (mirror `test_orchestration_host_cli_in_schema`)
- `scripts/tests/test_rate_limit_circuit.py` — closest existing test template (construct → mutate file-backed state → assert persisted read-back) for the new batch-poll/`batch_id` bookkeeping tests; no existing scaffold for `batch_id` in `fsm/persistence.py` today
- `scripts/tests/test_host_runner.py` — confirmed test file for `build_anthropic_request()`/host dispatch; add batch-transport-wrapper coverage here
- `scripts/tests/test_fsm_executor.py` — executor tests covering persistence + rate-limit circuit interplay; needs a batch-mode execution-routing case

### Configuration
- `scripts/little_loops/config-schema.json` — `orchestration.request_path` enum
- `scripts/little_loops/fsm/fsm-loop-schema.json` — per-state `request_path` property (separate schema file from `config-schema.json`; easy to miss)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — two existing gate-condition sentences hard-code "only when `orchestration.request_path == 'sdk'`" for the cache-marking oracle and deferred-tools blocks; these become inaccurate once `"batch"` is a third disjoint value. No dedicated `## orchestration` section currently documents `request_path`'s enum values — worth adding one covering `cli`/`sdk`/`batch` together
- `scripts/little_loops/config/orchestration.py` (`OrchestrationConfig.request_path` docstring, lines 71-77) — currently documents only `"cli"`/`"sdk"`; needs an equivalent explanatory paragraph for `"batch"`, since `config-schema.json`'s description fields mirror this docstring nearly verbatim
- `scripts/little_loops/config-schema.json:627,639` — two `"description"` strings hard-code "Only consulted when orchestration.request_path == 'sdk'"; need rewording once `"batch"` exists as a third mode (batchable requests may also want tool-deferral/cache-control semantics)

## Acceptance Criteria

- [ ] `orchestration.request_path: batch` submits via the Batches API and returns results through the existing parse path.
- [ ] Batch requests are priced at 0.5× in the F6 cost table and F5 telemetry.
- [ ] Interrupted runs resume polling from persisted batch IDs (no double-submit).
- [ ] Default behavior unchanged; batch is opt-in per config/loop/state.

## Impact

- **Priority**: P2 — largest guaranteed unconsidered saving; blocked only by FEAT-2673 (done).
- **Effort**: Medium (~150 LOC + tests); transport-only change, no prompt-assembly changes.
- **Risk**: Low-Medium — new async lifecycle (submit/poll/expire) needs careful resume semantics.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- FEAT-2673 is marked `done`, but this issue's own research finding notes `build_anthropic_request()` (`host_runner.py:1282-1361`) never calls `anthropic.Anthropic().messages.create(**kwargs)` — there is no working "sdk" dispatch path today to fork into a "batch" variant. Either the sdk dispatch call needs to land first, or both dispatch paths need to be built together in this issue.
- The pricing discount mechanism (parallel `batch` rate table vs. a multiplier parameter threaded through `estimate_cost_usd()`) is explicitly flagged in the issue's own research as needing "an explicit decision before implementation," with no existing precedent for either approach.
- `learning_tests_required: [anthropic]` is `proven`, but its recorded assertions (`.ll/learning-tests/anthropic.md`) cover general SDK shape (client construction, cache_control on tools) — none exercise the `messages.batches` namespace specifically. The batch submit→poll→retrieve round-trip is still unverified against the real SDK surface.

## Session Log
- `/ll:confidence-check` - 2026-07-20T00:00:00 - `819dd253-ff86-4243-bc28-e7e8590b180f.jsonl`
- `/ll:wire-issue` - 2026-07-21T02:23:39 - `e690f789-037c-4f8e-a379-0612e34215a8.jsonl`
- `/ll:refine-issue` - 2026-07-21T02:14:15 - `b5f22567-4b6a-4cc4-8c54-126edf9b5373.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
