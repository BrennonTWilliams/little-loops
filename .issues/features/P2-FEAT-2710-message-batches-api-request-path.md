---
id: FEAT-2710
type: FEAT
title: Message Batches API request path (50% discount on batchable automation)
priority: P2
status: done
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
confidence_score: 88
outcome_confidence: 75
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
decision_needed: false
completed_at: '2026-07-21T04:45:17Z'
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

### Codebase Research Findings (refine-issue re-run, 2026-07-20)

_Added by `/ll:refine-issue` — corrections and additional findings from re-verifying prior research against current code:_

> ⚠ Line-number drift: `build_anthropic_request()` now spans `host_runner.py:1341-1420` (was `1282-1361` when last refined); `State.model: str | None = None` now sits at `fsm/schema.py:629` inside the `StateConfig` dataclass (`StateConfig` class spans lines 528-636), not line 566. Re-verify exact lines before editing.

- **Correction — `config-schema.json` already has a real JSON Schema enum for `request_path`**: the earlier finding that it's "only documented in description text, not a JSON Schema enum" is wrong. `config-schema.json:1568-1573` already declares `"type": "string", "enum": ["cli", "sdk"], "default": "cli"` for `orchestration.request_path` — this is a *different* location from the `627`/`639` lines cited elsewhere, which are unrelated description strings inside the `cache`/`deferred_tools` blocks that merely mention the `== "sdk"` gate condition in prose. Adding `"batch"` support is simpler than previously scoped: append `"batch"` to the existing enum array at `1568-1573`, not "add schema validation from scratch."
- **`orchestration.request_path` is entirely inert in production code today, not just missing the network call**: a full grep for `request_path ==` / `.request_path` across `scripts/little_loops/` (excluding tests/docstrings/schema) finds **zero conditional branches** anywhere — not in `host_runner.py`, `fsm/executor.py`, or any CLI entry point. `CacheConfig`/`DeferredToolsConfig`'s "only consulted when `request_path == 'sdk'`" gating (`config/features.py:566,591`) is aspirational docstring/schema prose only; `build_anthropic_request()` doesn't reference `orchestration` config at all. This confirms and sharpens the Confidence Check concern below: both the `"sdk"` and `"batch"` dispatch paths need to be built from scratch together — there is no live `"sdk"` behavior to diverge from.
- **Naming collision to resolve before implementation**: the proposed `StateConfig.request_path` per-state field (`fsm/schema.py`) shares its exact name with the pre-existing global `orchestration.request_path` config key (`config/orchestration.py:81`, `config-schema.json:1568-1573`, from FEAT-2673). No existing per-state override in `fsm/schema.py` currently shadows a global `orchestration.*` key by identical name — decide explicitly whether the per-state field overrides the same global knob (state value wins over config default) or is a logically distinct setting that happens to share a name, to avoid ambiguous precedence semantics.
- **`session_store.py` exact anchor**: `_backfill_usage_events()` is defined at `session_store.py:2636`; its positional `estimate_cost_usd()` call is at lines `2678-2684`.
- **`${context.run_dir}` consumption pattern to mirror for `batch_id` persistence**: `PersistentExecutor._handle_event()` (`fsm/persistence.py:719-767`) reads `run_dir = self.fsm.context.get("run_dir", "")` (line 732) and appends JSONL records to `Path(run_dir) / "usage.jsonl"` (line 734) / `"messages.jsonl"` (~758) via `_append_jsonl` on `action_complete`/`messages_append` events — a `batch_id.json`-style file would follow this same append point. Note `run_dir` itself is *not* set inside `persistence.py` — it's seeded upstream at `cli/loop/lifecycle.py:523` and `cli/loop/run.py:198` (both `<loops_dir>/runs/<instance_id>/`) and propagated to child-loop FSMs via `fsm/executor.py:835,897-898`.
- **`RateLimitCircuit` is a structural precedent only, not a behavioral one**: it's a 429 coordination record (single monotonically-merged recovery-window estimate), not a literal submit→poll-job pattern — no existing code polls an external job ID on an interval with backoff. Mirror its file-locking mechanics (`fcntl.flock` + `tempfile.mkstemp`/`os.replace` atomic write, `_write_atomic` at lines 121-134), not its data shape. Its test file `scripts/tests/test_rate_limit_circuit.py` has directly reusable test shapes: `test_atomic_write_crash_safety` (crash-safety with concurrent reader/writer threads), `test_concurrent_access` (thread-safety), `test_stale_detection` (staleness cutoff).
- **`TestModelStateConfig` (`test_fsm_schema.py:2391-2440`) is the literal template to copy for a new `TestRequestPathStateConfig`** — 6 test methods: `test_state_config_model_defaults_to_none`, `test_state_config_accepts_model`, `test_to_dict_includes_model_when_set`, `test_to_dict_excludes_model_when_none`, `test_from_dict_with_model`, `test_from_dict_without_model_defaults_none`, plus `test_round_trip_model`.

### Codebase Research Findings (refine-issue re-run, 2026-07-20 later pass)

_Added by `/ll:refine-issue` — additional findings from a fresh research pass; all prior line numbers re-confirmed exact (no further drift)._

- **Two additional atomic-persistence primitives exist beyond `RateLimitCircuit`, not previously cited**: `scripts/little_loops/file_utils.py` provides `atomic_write_json(path, data)` (tempfile + `os.replace()`, no locking) and `acquire_lock(path, timeout=10.0)` — a `fcntl.flock`-based context manager with a fixed 0.05s poll loop (lines 60-96), usable as an off-the-shelf substitute for hand-rolling `RateLimitCircuit`-style locking. If a single process owns the batch-poll loop (no concurrent writers), `atomic_write_json()` alone is simpler than mirroring `RateLimitCircuit`'s full locking scheme. `scripts/little_loops/state.py`'s `StateManager` class (lines 84-237) is a fuller dataclass+manager+`EventBus`-emission shape (`save()`/`load()`/`_emit()`) but has no `fcntl.flock` locking — useful only if the batch tracker wants lifecycle event emission, not concurrent-write safety.
- **Precise `StateConfig.model` `to_dict()`/`from_dict()` anchors** (previously only approximated as "line 574+"): `to_dict()`'s conditional inclusion is at `fsm/schema.py:704-705` (`if self.model is not None: result["model"] = self.model`); `from_dict()`'s read is at line 800 (`model=data.get("model")`). Use these exact lines, not `574+`, when adding the mirrored `request_path` field.
- **`orchestration.host_cli` is a second live precedent for the enum-field pattern** (`config-schema.json:1565`, `enum: ["claude-code", "codex", "opencode", "pi"]`) — confirms the `test_orchestration_host_cli_in_schema` structural-assertion style (`test_config_schema.py:724-743`) already cited is the right template, not a one-off.
- **`config-schema.json` has no repo-root copy** — it exists only at `scripts/little_loops/config-schema.json` (package data). All prior line citations already point to the correct package-data path; no action needed, just a confirmation to avoid editing a nonexistent root file.

## Open Questions

1. **`request_path` precedence.** ✅ **RESOLVED** (2026-07-20 via `/ll:decide-issue`)
   Does the per-state `StateConfig.request_path`
   (new field, `fsm/schema.py`) override the global `orchestration.request_path`
   config key (`config/orchestration.py:81`) when both are set, or is it a
   logically distinct setting that happens to share a name?
   - (a) State overrides global — state value wins over the config default,
     mirroring how other per-state escape hatches (e.g. `State.model`) shadow
     their loop/config-level equivalent.
   - (b) Distinct settings — the per-state field is independent of the global
     orchestration mode and does not shadow it.

   > **Selected: (a) State overrides global.** `fsm/executor.py:1600` already
   > resolves `model` this exact way (`state.model or self.run_model` —
   > per-state value shadows the loop default, empty falls through). Giving
   > `StateConfig.request_path` the same field name as `orchestration.request_path`
   > but different (non-shadowing) semantics would mean two config keys with
   > identical names and different meanings — a footgun with no offsetting
   > benefit. `orchestration.request_path` has zero consumers today (confirmed
   > via grep across `scripts/little_loops/`), so there's no existing behavior
   > to preserve; wire it as `state.request_path or self.orchestration_config.request_path`,
   > mirroring the `model` resolution exactly.

2. **Batch pricing mechanism.** ✅ **RESOLVED** (2026-07-20 via `/ll:decide-issue`)
   How should the 50% batch discount be
   represented in `pricing.py`, which has no existing multiplier precedent
   (all current discounts are baked into flat per-token-type rates)?
   - (a) Parallel `batch` rate table — doubles `MODEL_PRICING` (lines 10-55),
     mirrors its existing per-model/per-token-type dict shape.
   - (b) Multiplier parameter threaded through `estimate_cost_usd()` (lines
     58-78) — single function, new discount-ratio arg appended (positionally
     safe, per the wiring note on `cost_graph.py`/`session_store.py` callers)
     to the signature.

   > **Selected: (b) Multiplier parameter, appended at the end of the
   > signature** (e.g. `is_batch: bool = False`). Both existing call sites
   > (`fsm/cost_graph.py:234`, `session_store.py:2678`) call
   > `estimate_cost_usd()` positionally with 5 args, so an appended
   > default-valued param is a strict superset — zero risk to callers. The
   > alternative (a parallel `batch` table) duplicates 7 models × 4 rate
   > fields that must be hand-kept in sync with `MODEL_PRICING` forever;
   > a missed second edit on a future price update silently mis-prices batch
   > requests with no test to catch the drift. A multiplier derives from the
   > existing table by construction and has no such failure mode.

## Implementation Steps

1. Learning test proving batch submit → poll → retrieve round-trip with the pinned `anthropic` SDK (mirror FEAT-2681's pattern at `.ll/learning-tests/anthropic.md` — append new assertions, don't overwrite; expect `untested` for the live round-trip without an API key).
2. Batch transport wrapper in `host_runner.py` alongside `build_anthropic_request()` (⚠ now at lines `1341-1420`, not `1282-1361`) + `orchestration.request_path` enum extension in `config-schema.json` (⚠ the actual enum property is at `1568-1573`, `["cli", "sdk"]` — `627,639` are unrelated description strings in the `cache`/`deferred_tools` blocks; just append `"batch"` to the `1568-1573` array).
3. Loop-YAML `request_path` per-state override in `fsm/schema.py` — follow the existing `State.model: str | None = None` pattern (⚠ now at line `629`, not `566`; `StateConfig` class spans `528-636`) and its conditional `to_dict()` inclusion. Resolve the name collision with the global `orchestration.request_path` config key first (see Codebase Research Findings above).
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
- `scripts/little_loops/host_runner.py` — add batch-submission wrapper alongside `build_anthropic_request()` (⚠ lines `1341-1420`, not `1282-1361`)
- `scripts/little_loops/config/orchestration.py:81,85-93` — add `"batch"` to `request_path` and validate against an enum
- `scripts/little_loops/config-schema.json:1568-1573` — add `"batch"` to the `orchestration.request_path` JSON Schema `enum` array (⚠ not `627,639` — those are unrelated description strings in the `cache`/`deferred_tools` blocks)
- `scripts/little_loops/fsm/schema.py` — add `State.request_path: str | None = None` (pattern: `State.model` at ⚠ line `629`, not `566`; resolve naming collision with global `orchestration.request_path` first)
- `scripts/little_loops/pricing.py:10-78` — add batch discount (parallel rate table or multiplier param)
- `scripts/little_loops/fsm/persistence.py` (`StatePersistence`/`PersistentExecutor`, class starting line 391/629) — persist/read `batch_id` under `${context.run_dir}/`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — sibling JSON Schema for FSM loop YAML `StateConfig`; needs a new `"request_path"` property block alongside the existing `"model"` block (lines 516-519), following its "which action types it applies to / WARNING if set on inapplicable type" convention

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/cost_graph.py:229-238` — calls `estimate_cost_usd()` per invocation row; any pricing signature change must be threaded through here **positionally-safe only if the new param is appended with a default**, not inserted
- `scripts/little_loops/session_store.py:2636` (`_backfill_usage_events()`, positional `estimate_cost_usd()` call at lines `2678-2684`) — also calls `estimate_cost_usd()` positionally while backfilling `usage_events` rows from transcript `message.usage` blocks; same positional-signature risk as `cost_graph.py`. Batch-discount awareness here needs either a new `usage_events` column (e.g. `is_batch`) or inference from context, since raw transcript usage blocks are the only per-turn source
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

_Added by `/ll:refine-issue` (later pass, 2026-07-20) — additional reusable primitives found:_
- `scripts/little_loops/file_utils.py` (`atomic_write_json()`, `acquire_lock()` lines 60-96) — simpler single-process alternative to `RateLimitCircuit`'s locking if the batch-poll loop has no concurrent writers
- `scripts/little_loops/state.py` (`StateManager`, lines 84-237) — fuller dataclass+manager+`EventBus`-emission shape; lacks `fcntl.flock` locking, so only a fit if lifecycle-event emission matters more than concurrent-write safety

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

- [x] `orchestration.request_path: batch` submits via the Batches API and returns results through the existing parse path. **Met** (2026-07-21 via FEAT-2716, commit `ce7174b4`) — `FSMExecutor._dispatch_live()` (`fsm/executor.py:1997-2085`) routes `request_path == "batch"` prompt-mode states through `host_runner.dispatch_batch_request()` → `poll_batch_result()`.
- [x] Batch requests are priced at 0.5× in the F6 cost table and F5 telemetry. `estimate_cost_usd(..., is_batch=True)` applies `BATCH_DISCOUNT` (0.5), and is now actually invoked with `is_batch=True` since FEAT-2716 tags batch usage events accordingly.
- [x] Interrupted runs resume polling from persisted batch IDs (no double-submit). **Met** (2026-07-21 via FEAT-2716, commit `ce7174b4`) — `_dispatch_live()` checks `BatchTracker.get_batch_id()` before submitting; a non-`None` value resumes polling with the persisted `custom_id` instead of resubmitting. Verified by `test_fsm_executor.py::test_request_path_batch_resumes_without_double_submit`.
- [x] Default behavior unchanged; batch is opt-in per config/loop/state. `orchestration.request_path` still defaults to `"cli"`; `StateConfig.request_path` defaults to `None` (falls through to config default), following the exact `model` field precedent.

### Partial Implementation Notes (2026-07-21)

Delivered the full **infrastructure layer** at the same maturity level FEAT-2673
established for the "sdk" path (request-shape building only, no live network
call): pricing multiplier, config/schema enum + per-state override, transport
request-builder, and file-backed batch-ID bookkeeping — all tested (30 new
tests, `ruff`/`mypy` clean, zero regressions in the full suite; the 192
pre-existing failures on `main` are unrelated xdist worker-isolation flakiness,
confirmed via `git stash` bisection).

**Deliberately not attempted in this pass**: wiring a live
`messages.batches.create()`/poll/retrieve call into `fsm/executor.py`'s state
dispatch and `cli/loop/lifecycle.py`'s run lifecycle. That requires first
building the "sdk" path's live dispatch call (FEAT-2673 never added one — the
Confidence Check's Concern #1, re-verified true), which is a materially
larger and riskier change to the core loop-execution path than this issue's
"transport-only, no prompt-assembly changes" framing suggested. Recommend a
follow-up issue scoped explicitly to "wire live SDK/batch dispatch into
`fsm/executor.py`" that covers both request paths together, rather than
retrofitting it piecemeal under this issue's title.

## Resolution (2026-07-21)

The recommended follow-up, FEAT-2716, landed the live SDK/Batches dispatch
call in commit `ce7174b4` ("wire FSM executor to live SDK/Batches API
dispatch"), completing both ACs this issue had deferred. Verified directly
against `HEAD` during `/ll:ready-issue`:

- `test_host_runner_dispatch.py` — 10/10 passed
- `test_fsm_executor.py -k "request_path or batch"` — 6/6 passed, including
  `test_request_path_batch_resumes_without_double_submit`
- The 13 unrelated failures elsewhere in `test_fsm_executor.py` (signal
  handling, timeout defaults, stall detector) reproduce identically on `main`
  at `f4ef4a87`, before this issue or FEAT-2716 existed — pre-existing, not a
  regression from this work.

All four Acceptance Criteria are now met. Closing as already fixed via
FEAT-2716.

## Impact

- **Priority**: P2 — largest guaranteed unconsidered saving; blocked only by FEAT-2673 (done).
- **Effort**: Medium (~150 LOC + tests); transport-only change, no prompt-assembly changes.
- **Risk**: Low-Medium — new async lifecycle (submit/poll/expire) needs careful resume semantics.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-20 (re-run)_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

Both open questions (`request_path` precedence, batch pricing mechanism) were
resolved via `/ll:decide-issue` since the prior run, raising ambiguity
(15→22) and overall readiness (80→88) and outcome confidence (68→75). The
core dependency gap below is unchanged and re-verified against current code.

### Concerns
- Re-verified via fresh grep (`messages.create\|messages.batches` across
  `scripts/little_loops/host_runner.py`): still only one hit — the docstring
  mention at line 1357. FEAT-2673 is marked `done`, but no code anywhere in
  the codebase actually calls `anthropic.Anthropic().messages.create(**kwargs)`
  or `.messages.batches.create(...)`. Both the "sdk" and "batch" dispatch
  paths must be built together in this issue — larger scope than the issue's
  "transport-only change, no prompt-assembly changes" framing suggests.
- `learning_tests_required: [anthropic]` is `proven` (7/0/2), but its recorded
  assertions (`.ll/learning-tests/anthropic.md`) cover general SDK shape
  (client construction, `cache_control` on tools) — none exercise the
  `messages.batches` namespace specifically. The batch submit→poll→retrieve
  round-trip is still unverified against the real SDK surface.

## Session Log
- `/ll:ready-issue` - 2026-07-21T04:45:18 - `b84944fe-c817-4cd3-ba89-3c3da6b98373.jsonl`
- `/ll:manage-issue` (partial implementation — infra layer only, see Partial Implementation Notes) - 2026-07-21T03:40:13Z - `4ea8aa10-aefa-44df-b782-f67007fcc175.jsonl`
- `/ll:refine-issue` - 2026-07-21T03:23:28 - `46a0022c-3c8d-4a4a-8dd4-91d37d76136b.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00 - `97856e1e-43f1-4a41-b60e-e38c58d369df.jsonl`
- `/ll:decide-issue` - 2026-07-21T03:13:23 - `c292b3d1-1d24-45ed-9b15-dc634c923e2c.jsonl`
- `/ll:decide-issue` - 2026-07-21T03:08:30 - `c28737b4-7f98-48e2-afdf-cc4632e3a0b1.jsonl`
- `/ll:decide-issue` - 2026-07-21T03:04:33 - `a391cada-c2da-4b7f-9fe6-5b3f92da46b4.jsonl`
- `/ll:refine-issue` - 2026-07-21T02:48:16 - `4a047046-4ab7-4af2-ad21-51957f2960cf.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00 - `819dd253-ff86-4243-bc28-e7e8590b180f.jsonl`
- `/ll:wire-issue` - 2026-07-21T02:23:39 - `e690f789-037c-4f8e-a379-0612e34215a8.jsonl`
- `/ll:refine-issue` - 2026-07-21T02:14:15 - `b5f22567-4b6a-4cc4-8c54-126edf9b5373.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Done** | Created: 2026-07-21 | Priority: P2
