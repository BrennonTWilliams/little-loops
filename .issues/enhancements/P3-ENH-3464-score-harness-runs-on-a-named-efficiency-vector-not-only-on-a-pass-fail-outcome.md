---
id: ENH-3464
title: Score harness runs on a named efficiency vector, not only on a pass/fail outcome
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels:
- evals
blocked_by:
- 'ENH-3462'
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

`ll-harness` reports one of pass, fail, or abstain. Two runners that both satisfy the same semantic criterion are therefore indistinguishable, even when one spent several times the tool calls, tokens, and wall-clock of the other. That is the wrong verdict shape for anything that feeds a selection decision: a wasteful winner reads identically to an efficient one, so promoting on the verdict alone will happily carry the expensive candidate forward.

Add a small, named set of efficiency dimensions to the verdict — tokens, tool calls, and wall-clock at minimum — reported alongside the outcome rather than folded into it. The dimensions must be named in advance and stable, so that a downstream post-mortem matches a run against a taxonomy instead of free-associating about why it was slow.

## Current Behavior

`ll-harness` reports one of pass, fail, or abstain per run. Two runners that both satisfy the same semantic criterion are indistinguishable in the verdict, even when one spent several times the tool calls, tokens, and wall-clock of the other. Only wall-clock (`duration_ms`) is captured and persisted today. Tokens and tool calls are present in the host CLI's stdout that the harness already captures (stream-json `result`/`tool_use` events on the skill path, the single JSON blob's `usage` on the prompt path) but are never parsed, surfaced, or persisted.

## Expected Behavior

The verdict carries a small, named, stable set of efficiency dimensions — tokens, tool calls, and wall-clock at minimum — reported alongside (not folded into) the pass/fail/abstain outcome, attached to the run model shipped in ENH-3397 (an attempt recorded against task × repetition × subject). A run that passes expensively still passes; efficiency is reporting, not a second gate. A downstream post-mortem matches a run against this taxonomy instead of free-associating about why it was slow.

## Design

- Wall-clock is already captured (`duration_ms`); tokens and tool calls are present in captured stdout but never parsed. The work is (a) parsing them off `RunnerResult.stdout` in the runners, (b) threading them alongside `duration_ms` into the outcome and the persisted attempt row, and (c) surfacing them in `--output json`, the text summary, and the N-sample per-sample entries. Cross-run comparison semantics are **not** defined here (see Scope Boundaries).

### Decisions (resolved 2026-09-14, review pass)

1. **Capture is post hoc from stdout, not via streaming callbacks.** The two harness paths that invoke an LLM already capture the usage data: `_run_skill()`'s default blocking branch (`runner_spec.py:250-262`) runs `build_streaming()` so stdout is stream-json (a `result` event carrying `usage`, plus one `tool_use` content block per tool call); `_run_prompt()` (`:422-435`) runs `build_blocking_json()` so stdout is one JSON object carrying `usage` and `num_turns`. Parse those after `subprocess.run()` returns. Do **not** wire `on_usage`/`on_usage_detailed` into the runners: `_run_cmd()`/`_run_mcp()` never invoke a host CLI, and the skill/prompt paths would need a streaming restructure for no gain. The earlier wiring directive below is superseded by this decision.
2. **Where the numbers are born and how they flow.** New trailing fields `RunnerResult.input_tokens`, `output_tokens`, `cache_read_tokens`, `tool_calls` (all `int | None = None`) are populated inside `runner_spec.py` by the runner that knows its stdout format. `cli/harness.py` threads them to `_record_harness_event()` exactly the way `duration_ms` is threaded today (computed at the `_invoke()` wrapper, **bypassing** `_grade()`), and additionally stamps them onto `HarnessEvalOutcome` so `--output json` and the N-sample summary can show them. The "through `_grade()`" call path in Program Design is replaced by this.
3. **Token fields are split, not summed.** Mirror `TokenUsage` (`subprocess_utils.py`): `input_tokens`, `output_tokens`, `cache_read_tokens`. A single `tokens` sum is ambiguous (cache-read inclusion) and would not be "named and stable". Consumers derive totals.
4. **`tool_calls` on the PROMPT/DSL path is `None`.** `--output-format json` emits no `tool_use` events (only `num_turns`, which is not a tool-call count). Accept `None` rather than switching `_run_prompt()` to stream-json. CMD/MCP runners leave all four fields `None`; `_STOCHASTIC_RUNNERS` (`runner_spec.py:79`) is the existing predicate for "may be populated" vs "inherently `None`".
5. **Timed-out and errored runs leave the fields `None`.** `duration_ms` stays populated for the same row (it is measured by the caller). No partial capture is attempted.
6. **Subject-side cost only.** The judge call's `llm_latency_ms` (`fsm/evaluators.py`) and its tokens are excluded, matching what `duration_ms` measures today. Document this on the fields.
7. **Persistence is in scope for this issue** (not split the way ENH-3462 → ENH-3476 was). The stated consumer is history.db analytics, so a field with no column delivers nothing. Adds `harness_events` columns via a new `_MIGRATIONS` entry.
8. **One shared parsing helper.** Add `usage_from_stream_lines(lines) -> TokenUsage | None` and `tool_call_count_from_stream_lines(lines) -> int` (or one combined helper) to `subprocess_utils.py`, handling the Claude `result` shape and the Codex `turn.completed` shape, and refactor `_process_line`'s inline `result`/`turn.completed` handling to call it. The harness must not become the fourth inline tally (`cli/loop/audit.py`, `subprocess_utils.py`, `fsm/executor.py` each have their own today).
9. **Migration coordination with ENH-3476.** Both issues append a `harness_events` migration after v50. Whichever lands second renumbers to the next version; if implemented back-to-back, prefer one combined migration. Check `_MIGRATIONS`'s tail before writing.

- **Efficiency must not silently become a gate.** A run that passes expensively still passes; the dimension is reporting, not a second pass/fail hiding behind one.
- The dimensions attach to the run model shipped as ENH-3397 — an attempt recorded against a named cell (task × repetition × subject) is the unit these measurements belong to.
- The precedent is a tournament fitness function that is deliberately multi-dimensional, with three of its four named criteria (resource efficiency, advancement speed, composition) existing to catch candidates that win wastefully — on the stated grounds that a wasteful winner is the wrong parent for the next generation. Naming the failure modes in advance is also what makes a post-mortem legible: the analyst matches observations against a known taxonomy rather than free-associating.

## Why it matters

The instrument that certifies runner correctness is today silent on cost. Downstream cost-trend analytics over `.ll/history.db` need exactly this per-run record as input; without it, a selection decision can carry forward a candidate that satisfies the criterion at multiples of the cost of its alternative.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for wiring tokens/tool-calls onto `RunnerResult` and persisting them to `HarnessEvent`.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `ABResults.harness_pass_rate` (`scripts/little_loops/ab_writer.py:146`, on `class ABResults:` line 132) is a second, pre-existing precedent for a named scoring field carried on a run/comparison result — distinct from and already disambiguated against `history_reader.harness.harness_eval_pass_rate` in `docs/reference/API.md:9159`.
- No mechanical single source of truth ties `HarnessEvent`'s dataclass fields, `_HARNESS_EVENT_COLUMNS`'s column-name string, and `record_harness_event()`'s kwargs together — all three are independently hand-maintained and must be updated in lockstep by hand for any new field (confirmed by direct read of `history_reader/harness.py:53-108` and `session_store/writers.py:1210-1241`).
- `HarnessEventVariant(DESVariant)` (`scripts/little_loops/observability/schema.py:731-734`) carries only a `type: Literal["harness_event"]` discriminator field and no per-column fields at all — confirmed it needs no change for new `tokens`/`tool_calls` columns, same conclusion ENH-3476's research reached independently for `channels_json`/`side_effects_json`.
- `run_claude_command()`'s `TokenUsage` dataclass (built on a `"result"`/`"turn.completed"` event, `subprocess_utils.py`) carries `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`, `is_batch` — the exact shape available if `on_usage`/`on_usage_detailed` were wired into `runner_spec.py`'s runners.
- `_run_sample_loop()`, `_run_baseline_phase()`, and `_run_compare_arm()` (`cli/harness.py`) all consume the same `Callable[[], tuple[RunnerResult, int]]` contract from every `cmd_*` handler's `_invoke()` closure — widening what `_invoke()` returns to carry tokens/tool-calls would need to widen this shared tuple/callable contract across these three functions too, not just the four `cmd_*` handlers.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `cmd_dsl()` dispatches through the identical `RunnerType.PROMPT` path as `cmd_prompt()`, not a separate execution path: it calls `_run_prompt_action()` (`cli/harness.py:2455`, invoked at `:2721`), which builds `ActionSpec(runner=RunnerType.PROMPT, ...)` and calls `run_action()` (`runner_spec.py:467`) — `run_action()`'s own docstring confirms `RunnerType.DSL` is never a key in `_DISPATCH`; DSL is a caller-side batch loop over `PROMPT`, not a distinct runner implementation.
- `--trace-mode` is exposed only on `skill_p` (`_add_trace_flags()`, `cli/harness.py:689`, attached at `:738`) — `prompt_p` (`:764`) and `dsl_p` (`:778`) never receive this flag at the CLI-parser layer, independent of the already-noted gap that no `ActionSpec` construction site sets `"trace_mode"` in `args`.
- Additional stale-documentation sites beyond `docs/reference/API.md`/`EVENT-SCHEMA.md`/`ARCHITECTURE.md` already flagged: `docs/guides/HISTORY_SESSION_GUIDE.md`'s schema-version table also stops at `v49` (no `v50`/ENH-3435 row); `docs/guides/EVALUATION_GUIDE.md`'s "Across runs" section lists persisted `harness_events` columns illustratively with no tokens/tool_calls mention; `docs/reference/CLI.md`'s `### ll-harness` section (header at `:212`) has zero tokens/tool_calls references anywhere within it (a repo-wide search for those terms in this file returns 48 hits, all in unrelated `ll-ctx-stats`/`ll-init` sections).
- `scripts/tests/test_issue_manager.py::test_forwards_on_usage_detailed_to_ready_issue_call` (`:2252`) is a third existing `on_usage_detailed`-mocking test beyond the two already cited (`TestRunClaudeCommand::test_forwards_on_usage_detailed`, `TestRunWithContinuation::test_high_cumulative_usage_does_not_write_sentinel`).
- Confirmed zero hits for `tokens`/`tool_calls` as field names inside `RunnerResult`, `HarnessEvent`, or `HarnessEvalOutcome` (each dataclass body read directly), and zero code hits for the literal phrase "efficiency vector" outside this issue and its parent `EPIC-3475` — this is a net-new concept with no existing naming collision beyond the already-flagged `ab_writer.py` `harness_tokens`/`harness_duration_ms` precedent.

### Files to Modify
- `scripts/little_loops/runner_spec.py` — `_run_skill()` currently calls `run_claude_command()` without `on_usage`/`on_usage_detailed`; `_run_cmd()`/`_run_mcp()`/`_run_prompt()` don't call `run_claude_command()` at all — wiring tokens onto `RunnerResult` starts here, not at `_grade()`
- `scripts/little_loops/cli/harness.py` — `_grade()` (`:1224`) and each `cmd_*` call site's `duration_ms` threading pattern (computed via `time.monotonic()`, passed straight to `_record_harness_event`, bypassing `_grade()`) is the existing precedent for how a new quantity would flow
- `scripts/little_loops/history_reader/harness.py` — `HarnessEvent` dataclass (`:53`) and `_HARNESS_EVENT_COLUMNS`, which must stay in sync by hand
- `scripts/little_loops/session_store/schema.py` — `_MIGRATIONS` list (currently ends at v50/ENH-3435, `:1346-1414`) — a new efficiency-column migration appends here
- `scripts/little_loops/session_store/writers.py` — `record_harness_event()`/`record_attempt()` (`:1210-1265`, `:1367`) — new trailing-default kwargs mirroring the v49/v50 pattern

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:30`, `scripts/little_loops/history_reader/__init__.py:184` — importers of `history_reader/harness.py`, both would see any new `HarnessEvent` fields
- `scripts/tests/test_history_reader_harness.py:327,370` (`TestAuthoritativeAttempts`) — existing readers of `authoritative_attempt`/`authoritative_attempts` that a new field must not break
- `scripts/little_loops/cli/harness.py:1297` (`_compose_judge_evidence`), `evaluators.py:1298,1302` (`evaluate_llm_structured`), `fsm/verdicts.py:1309` (`is_abstention_verdict`) — existing callees inside `_grade()`, none of which currently read `RunnerResult.tool_trace` or any token field

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/queue_store.py:36`, `scripts/little_loops/cli/loop/run.py:135`, `scripts/little_loops/cli/action.py:218`, `scripts/little_loops/cli/queue.py:34,130,164,403,488,556` — importers of `runner_spec.py`'s `ActionSpec`/`RunnerType`/`RunnerResult`; would see new trailing `RunnerResult` fields
- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/fsm/runners.py` (`DefaultActionRunner`, a sibling FSM prompt-action runner with its own existing `on_usage`/`on_usage_detailed` wiring), `scripts/little_loops/fsm/executor.py:2387-2598,3698-3751` (ENH-2724 baseline-arm direct call), `scripts/little_loops/parallel/worker_pool.py:938-1238` — existing callers of `run_claude_command()`'s `on_usage`/`on_usage_detailed` callbacks, the pattern-to-model for wiring token capture into `runner_spec.py`'s runners
- `scripts/tests/test_runner_spec.py` — confirmed **zero existing coverage** of `trace_mode`/`stream_callback`/`run_claude_command` in this file; `_run_skill()`'s two `run_claude_command()`-calling branches (`:196-248`) are untested today, and three `TestRunActionDispatch` tests (`test_skill_dispatch_matches_legacy_shape`, `test_prompt_dispatch_matches_legacy_shape`, `:151-188`) use dataclass `==` equality against a `RunnerResult(...)` literal missing later fields — a real break risk once new trailing fields (tokens/tool_calls) populate with non-`None` values on these dispatch paths
- `scripts/little_loops/cli/session.py:11` — `ll-session recent --kind harness` renders rows generically (`", ".join(f"{k}={v}" ...)`), confirmed behavior-neutral; new fields surface automatically, no code change needed here
- `scripts/little_loops/observability/schema.py:730-734` (`HarnessEventVariant`), `scripts/little_loops/session_store/__init__.py:56,59,177,181,270,276` (re-exports) — additional consumers of the `HarnessEvent`/`record_harness_event` shape
- `scripts/tests/test_session_store_writers.py:2391-2723`, `scripts/tests/test_ll_session.py:1383-1400` — additional write-path/read-path tests beyond the three already-known
- Confirmed **not coupled**: `scripts/little_loops/ab_writer.py`/`fsm/executor.py`'s `baseline_complete` A/B system already uses field names `harness_tokens`/`baseline_tokens`/`harness_duration_ms` but has zero import/call coupling to `history_reader.harness`/`session_store.writers` — a separate event shape; worth a documentation note flagging the naming-collision risk (`docs/reference/API.md` already flags `harness_eval_pass_rate` vs. `ab_writer.ABResults.harness_pass_rate` similarly) but no code coupling exists

### Conventions in Force
- New `HarnessEvent` fields are always appended at the end, always `type | None = None`, with an inline comment citing the introducing issue — evidence: ENH-141/ENH-3407/ENH-3435 field blocks in `history_reader/harness.py:54-98`
- Schema changes are fix-forward only — `ALTER TABLE ADD COLUMN` with no `DEFAULT`, pre-migration rows keep `NULL`, no backfill — evidence: v49/v50 migration comments in `session_store/schema.py:1346-1414`
- A new reporting dimension is added as its own field on the outcome/event dataclass, never folded into the pass/fail verdict — evidence: `ChannelRecord`/`HarnessEvalOutcome.channels` (ENH-3462), `HarnessEvent.semantic_confidence` beside `semantic_passed`, `HarnessEvalOutcome.sample_pass_rate` (ENH-3415)
- Persisting a newly-added outcome field to `harness_events` is treated as a separate, explicitly tracked follow-up issue rather than bundled into the field's introduction — evidence: `ENH-3476` tracks persistence of ENH-3462's `channels` field separately from ENH-3462 itself

### Tests
- `scripts/tests/test_session_store_schema.py` — `TestSchemaV50BaselineConditions`-shaped triad (new-DB shape / upgrade-DB shape / NULL-on-old-rows) is the existing convention for a new migration
- `scripts/tests/test_history_reader_harness.py` — round-trip coverage for new `HarnessEvent` fields through `record_harness_event`/readers, e.g. `test_harness_event_carries_id_and_v49_fields` (`:270-279`)
- `scripts/tests/test_cli_harness.py` — `TestGradeEvidenceChannels` (`:3682`) is the closest existing test class exercising `_grade()` against synthetic `RunnerResult` fixtures

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_schema.py::TestSchemaV50BaselineConditions` (concrete 3-method template: `test_harness_events_gains_baseline_condition_columns`, `test_v49_db_upgrades_gains_baseline_condition_columns`, `test_baseline_match_index_exists`) — column-set assertions there use subset (`<=`), never exhaustive (`==`), against `PRAGMA table_info(harness_events)`; follow this convention, not exhaustive equality
- `scripts/tests/test_issue_manager.py::TestRunClaudeCommand.test_forwards_on_usage_detailed` and `TestRunWithContinuation.test_high_cumulative_usage_does_not_write_sentinel` — the two `on_usage`/`on_usage_detailed` mocking sub-patterns (forward-by-identity vs. `side_effect` invoking the callback) to follow when wiring token capture into `runner_spec.py`'s runners; patch target is `little_loops.subprocess_utils.run_claude_command` (module-local import inside `_run_skill()`, confirmed via `scripts/tests/test_action.py`'s equivalent patch site), not a module-level import
- `scripts/little_loops/cli/harness.py:832-872` (`ChannelRecord`/`HarnessEvalOutcome.channels`, ENH-3462) and its tests `scripts/tests/test_cli_harness.py::TestChannelRecordToDict`/`TestGradeEvidenceChannels` — precedent for "a field added, persistence tracked separately," including the `to_dict()`-vs-object test-class split
- `scripts/tests/test_runner_spec.py::TestRunActionDispatch::test_skill_dispatch_matches_legacy_shape`, `::test_prompt_dispatch_matches_legacy_shape` (`:151-188`) — existing tests to update: both assert `result == RunnerResult(...)` by dataclass equality and will break once new trailing fields populate with non-`None` values on these dispatch paths

## Program Design

### Types

- `RunnerResult` (`scripts/little_loops/runner_spec.py:100`): new trailing fields `input_tokens: int | None = None`, `output_tokens: int | None = None`, `cache_read_tokens: int | None = None`, `tool_calls: int | None = None`, populated by `_run_skill()` (default blocking branch, parsed from stream-json stdout) and `_run_prompt()` (parsed from the JSON blob's `usage`; `tool_calls` stays `None`). The existing `tool_trace` field is trace-mode-only and unrelated; leave it alone.
- `HarnessEvalOutcome` (`scripts/little_loops/cli/harness.py:863`): same four fields, trailing, `None` default, so `--output json` / N-sample entries carry them beside `passed`/`verdict`.
- `HarnessEvent` (`scripts/little_loops/history_reader/harness.py:53`): already tracks `duration_ms: int | None` (ENH-2741); append the same four fields with an `# ENH-3464` comment, and add the four column names to `_HARNESS_EVENT_COLUMNS` in the same order.
- `TokenUsage` (`scripts/little_loops/subprocess_utils.py`): reused as the return shape of the new shared parsing helper; no changes.

### Signatures

- `authoritative_attempt(db_path, cell_key, repetition)` / `authoritative_attempts(db_path, cell_key)` (`scripts/little_loops/history_reader/harness.py:170`, `:198`) — the existing cell-keyed (task × repetition × subject) lookup the efficiency dimensions attach to
- `usage_from_stream_lines(lines: Iterable[str]) -> tuple[TokenUsage | None, int | None]` (new, `scripts/little_loops/subprocess_utils.py`) — shared parser for the Claude `result`/`tool_use` and Codex `turn.completed` shapes; returns `(usage, tool_call_count)`; `_process_line` refactored to use it
- `_record_harness_event(..., duration_ms: int, ...)` (`scripts/little_loops/cli/harness.py:216`) — gains trailing `input_tokens=None, output_tokens=None, cache_read_tokens=None, tool_calls=None` kwargs, forwarded to `record_attempt()`/`record_harness_event()` (`session_store/writers.py`)
- `_grade(...)` (`scripts/little_loops/cli/harness.py:1224`) — **unchanged**; efficiency fields never enter grading

### Call Path

`_run_skill()`/`_run_prompt()` (`runner_spec.py`) parse captured stdout via `usage_from_stream_lines()` -> populate `RunnerResult.{input_tokens,output_tokens,cache_read_tokens,tool_calls}` -> each `cmd_*` `_invoke()` wrapper in `cli/harness.py` reads them off the result next to its `time.monotonic()` `duration_ms` -> passed to `_record_harness_event()` (10 call sites) and stamped onto `HarnessEvalOutcome` for `--output json` -> persisted as `harness_events` columns via `record_attempt()` -> read back on `HarnessEvent` via `authoritative_attempt()`/`authoritative_attempts()`. `_grade()`, `_band_samples()`, and `evaluate()` never read the fields.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Confirms `HarnessEvent.duration_ms` (`history_reader/harness.py`, field present since ENH-2741) is the only efficiency quantity currently persisted; the Design section's claim "most of the raw quantities are already logged" does not hold for tokens or tool-calls in the `ll-harness` pipeline — neither has a field anywhere in `RunnerResult`, `HarnessEvalOutcome`, or `HarnessEvent` today.
- `RunnerResult.tool_trace` (`runner_spec.py:113`) is populated only inside `_run_skill()`'s `if trace_mode:` branch, and that branch is unreachable from any current `ll-harness` command: `cmd_skill()`'s `_invoke()` builds its `ActionSpec` as `args={"runner_args": runner_args}` with no `"trace_mode"` key regardless of the parsed `--trace-mode` CLI flag, which today is read only by `_conditions_fp()` for baseline fingerprinting (`cli/harness.py`) — a repo-wide grep for `trace_mode` returns exactly these four sites and no caller ever sets `ActionSpec.args["trace_mode"]`.
- Token capture exists elsewhere in the codebase — `run_claude_command()`'s `on_usage`/`on_usage_detailed` callbacks (`subprocess_utils.py`) feed `TokenUsage` rows into the `usage_events` table, keyed by `run_id`/`session_id`/`state` (an FSM loop-run identity) — but no `ll-harness` runner (`_run_skill`, `_run_cmd`, `_run_mcp`, `_run_prompt` in `runner_spec.py`) passes either callback; `_run_mcp`/`_run_prompt` don't call `run_claude_command()` at all. Tokens and tool-calls both need new capture wiring in the harness runner path, not just new fields on `HarnessEvent`.
- `duration_ms` is computed per `cmd_*` call site via `time.monotonic()` deltas and passed straight to `_record_harness_event(..., duration_ms=duration_ms, ...)`, bypassing `_grade()`/`HarnessEvalOutcome` entirely — it is threaded around `_grade()`, not through it. A new tokens/tool_calls field needs to decide whether it follows this same bypass shape or is read off `RunnerResult` inside `_grade()` as this section's own Call Path describes.
- Existing precedent for the exact "add a named field to `HarnessEvalOutcome`, wire persistence as a separate follow-up issue" shape: `ChannelRecord`/`HarnessEvalOutcome.channels` (`cli/harness.py:831-872`, landed by ENH-3462), whose persistence to `harness_events` is tracked separately as ENH-3476 (sibling `EPIC-3475` child, still open).
- Schema convention for adding new `harness_events` columns: nullable, no `DEFAULT`, no backfill, appended at the end of the `_MIGRATIONS` list with the introducing issue ID in a comment, and covered by a three-part test (fresh-DB shape, upgrade-from-prior-version shape, read/write round trip) — evidence: v49 (ENH-3406/3407) and v50 (ENH-3435) entries in `session_store/schema.py:1346-1414`, `TestSchemaV50BaselineConditions` (`test_session_store_schema.py:3331-3389`).
- The "tournament fitness function" (resource efficiency / advancement speed / composition) this section's own Design cites as precedent is prose-only — a repo-wide unfiltered search for `tournament`/`fitness function`/these dimension names returns zero code hits; it is an argument-by-analogy from issue text (echoed in ENH-3415), not a locatable codebase artifact.
- Existing "reporting dimension, not a gate" precedent already in the codebase: `HarnessEvent.semantic_confidence` sits beside `semantic_passed` without deciding it, and `HarnessEvalOutcome.sample_pass_rate` (ENH-3415) is informational alongside the discrete verdict `_band_samples()` computes — both are the same non-gating shape this issue requires for the new efficiency dimensions.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Confirmed all four `ActionSpec(...)` construction sites in `cli/harness.py` (`cmd_skill`'s `_invoke()` at :2124, `cmd_cmd`'s at :2259, `cmd_mcp`'s at :2378, `cmd_prompt`'s `_run_prompt_action()` at :2462) never set a `"trace_mode"` key — pinpoints the exact four call sites that leave `RunnerResult.tool_trace` unreachable, confirming the earlier higher-level finding with per-site precision.
- Wall-clock (`duration_ms`) is captured unconditionally regardless of run outcome — `time.monotonic()` wraps the `_invoke()` call itself, so a timeout or error still produces a `duration_ms` value. Any token/tool-call capture done via streaming callbacks needs to match this: a callback that only fires on a completed `"result"` event may never fire before a timeout kill, so a timed-out run's tokens/tool-calls field should be expected to land `None` even though `duration_ms` is non-`None` for the same row.
- `_insert_harness_event()`'s three bool-typed kwargs (`semantic_passed`, `timed_out`, `dirty`) get explicit `None if x is None else int(x)` coercion; all other kwargs, including the numeric `duration_ms`, pass through with zero coercion — confirms the precedent for new `tokens`/`tool_calls` int fields is to pass through uncoerced, same as `duration_ms`.
- No literal write-side `HarnessEvent`-shaped row dataclass exists — `record_harness_event()`/`_insert_harness_event()` write directly via raw `conn.execute()` with positional parameter tuples; `HarnessEvent` (the dataclass with fields) exists only on the read side, in `history_reader/harness.py:54`.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Call path precision for the `PROMPT`/`DSL` runners: `cmd_dsl()` -> `_invoke_with_side_effects(functools.partial(_run_prompt_action, ...))` -> `_run_prompt_action()` (`cli/harness.py:2455`) -> `ActionSpec(runner=RunnerType.PROMPT)` -> `run_action()` (`runner_spec.py:467`) -> `_run_prompt()` (`runner_spec.py:422`) — identical to `cmd_prompt()`'s path, so a fix to `_run_prompt()`'s capture logic covers both call sites in one change.
- Timeout-survivability asymmetry the design must decide on: `_run_skill()`'s `trace_mode` branch keeps a live `on_tool_call=trace.append` callback, so a partial `tool_trace` survives `subprocess.TimeoutExpired` (`runner_spec.py:223-230`). `_run_prompt()` instead uses a blocking `subprocess.run()` with no live callback, so unlike `duration_ms` (measured by the caller, always populated even on timeout), no partial tokens/tool-calls could survive a timeout on the `PROMPT`/`DSL` path without restructuring that call to stream.
- Judge-side cost is a separate, currently-uncaptured quantity from subject-side cost: `evaluate_llm_structured()`'s `llm_latency_ms` (`fsm/evaluators.py:1125`, its own `time.monotonic()` measurement) is never threaded into `duration_ms` or any persisted field — the design must decide whether the new efficiency dimensions represent subject-only cost (as `duration_ms` already does today) or also account for the judge call.
- `_STOCHASTIC_RUNNERS` (`runner_spec.py:79`) already classifies `SKILL`/`PROMPT`/`DSL` as LLM-driven (`True`, capable of non-null tokens/tool-calls) versus `CMD`/`MCP` as deterministic (`False`, inherently `None`/zero) — an existing predicate the new fields' `None`-vs-populated expectation can key off directly instead of inventing a new one.
- Two distinct existing "reporting field must never gate" shapes are both in force in this codebase, not just the one already cited: (a) a field that simply never appears in any gate expression — the precedents already noted (`ChannelRecord`, `semantic_confidence`/`sample_pass_rate`); (b) a field that could participate but is explicitly excluded via a named allowlist or severity flag — `_ADVISORY_GAP_CLASSES` (`issue_parser.py:515`) plus `FormatGaps.has_gaps` vs. `has_blocking_gaps` (`:564`, `:598`), and `CheckResult.severity: Literal["error","informational"]` (`cli/doctor.py:61`) where `_exit_code_for()` (`:131`) only fails on `severity=="error"`. This issue's fields fit shape (a) since no gate will ever read them — naming this explicitly heads off an implementer defaulting to inventing an unnecessary severity flag.
- No dedicated tool-call-counting helper exists anywhere in production code; every existing counting site reimplements its own inline tally rather than sharing one: `cli/loop/audit.py:199-254` (local `tool_call_count` incremented per `action_complete` event), `subprocess_utils.py:558-603` (a separately-defined local `tool_call_count` incremented per `tool_use` block inside `_process_line`), `fsm/executor.py:3608-3641` (a `list[tuple[int,int]]` reduced with `sum()` for token totals). A structurally identical function, `extract_tool_calls()` (`scripts/tests/spike/eval_trace_capture/trace_capture.py:25`), exists but is spike-only and was never promoted into `scripts/little_loops/` — not importable as a shared helper.
- Existing convention for testing that a new field does not change an existing pass/fail decision: construct the outcome/result dataclass directly and assert both the new field's presence and the gating predicate/exit-code is unchanged in the same test — cleanest instance: `test_issue_parser.py::TestGapClassAdvisory::test_testable_only_gap_is_advisory_not_blocking` (`:4350`); gating-function-only instance: `test_cli_doctor.py::test_exit_code_ignores_informational_unsupported` (`:761`).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `HarnessEvent`/`recent_harness_events`/`harness_eval_pass_rate` section hand-transcribes the full field list and is already stale (missing the v50 `timeout_s`/`host_cli`/`subject_model`/`input_hash`/`conditions_fp` columns, pre-existing drift independent of this issue); needs the new `tokens`/`tool_calls` fields appended
- `docs/reference/CLI.md` — the `--output json` payload field list and the N-sample redundancy per-sample entry field list, both under `### ll-harness`, need new rows if efficiency dimensions surface there
- `docs/reference/EVENT-SCHEMA.md` — makes an explicit, load-bearing exhaustiveness claim ("Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column") that becomes factually stale once tokens/tool_calls become newly-persisted `RunnerResult`-derived columns
- `docs/ARCHITECTURE.md` — the History DB producer→consumer schema-migration table is the append point for a new migration row; the v50/ENH-3435 row is confirmed already missing from this table (a pre-existing gap this issue's migration would land into, not caused by it)
- `docs/guides/EVALUATION_GUIDE.md` — the "Across runs" section illustratively lists persisted `harness_events` columns; the natural place to mention the new efficiency dimensions since it specifically explains what gets written per run

## Implementation Steps

1. `subprocess_utils.py`: add `usage_from_stream_lines()` (Decision 8); refactor `_process_line`'s `result`/`turn.completed` branches to call it. Unit-test it directly against a Claude stream-json fixture (with two `tool_use` blocks), a Claude `--output-format json` blob fixture, a Codex `turn.completed` fixture, and non-JSON noise lines.
2. `runner_spec.py`: add the four trailing `RunnerResult` fields; populate them in `_run_skill()`'s default blocking branch and in `_run_prompt()` from captured stdout. Leave `_run_cmd()`/`_run_mcp()`/the `stream_callback`/`trace_mode` branches untouched. Update `test_runner_spec.py::TestRunActionDispatch`'s two dataclass-equality tests if they now see non-`None` values.
3. `session_store/schema.py`: append a migration adding nullable `input_tokens`, `output_tokens`, `cache_read_tokens`, `tool_calls` INTEGER columns to `harness_events` (no `DEFAULT`, no backfill, `# ENH-3464` comment). Check the tail of `_MIGRATIONS` for an ENH-3476 entry first (Decision 9). Add the `TestSchemaV50BaselineConditions`-shaped triad.
4. `session_store/writers.py`: trailing-default kwargs on `record_harness_event()`/`record_attempt()`/`_insert_harness_event()`, passed through uncoerced like `duration_ms`.
5. `history_reader/harness.py`: append the four fields to `HarnessEvent` and `_HARNESS_EVENT_COLUMNS`; add a round-trip test beside `test_harness_event_carries_id_and_v49_fields`.
6. `cli/harness.py`: add the four fields to `HarnessEvalOutcome`; extend `_record_harness_event()`'s signature; at each of the 10 call sites read the values off the `RunnerResult` and pass them alongside `duration_ms`; include them in the `--output json` payload, the per-sample entries of the N-sample summary, and the text summary line (e.g. `tokens in/out=1234/567 tool_calls=8 duration_ms=...`, omitting fields that are `None`).
7. Docs: `docs/reference/API.md` (`HarnessEvent` field list, backfilling missing v50 fields), `docs/reference/CLI.md` (`--output json` and per-sample field lists under `### ll-harness`), `docs/reference/EVENT-SCHEMA.md` (rewrite the "only `timed_out` is persisted" claim), `docs/ARCHITECTURE.md` (migration table row, backfilling the missing v50 row), `docs/guides/EVALUATION_GUIDE.md` ("Across runs" column list), `docs/guides/HISTORY_SESSION_GUIDE.md` (schema-version table).
8. Run `python -m pytest scripts/tests/` and the three focused files listed under Tests.

## Acceptance Criteria

- [ ] `RunnerResult`, `HarnessEvalOutcome`, and `HarnessEvent` each carry `input_tokens`, `output_tokens`, `cache_read_tokens`, `tool_calls` as trailing `int | None = None` fields.
- [ ] After `ll-harness skill ...` completes normally, the recorded `harness_events` row has non-`None` token fields and a non-`None` `tool_calls`; after `ll-harness prompt ...`/`dsl ...`, token fields are non-`None` and `tool_calls` is `None`.
- [ ] CMD and MCP runs, timed-out runs, and errored runs record all four fields as `None` while `duration_ms` is still populated.
- [ ] `--output json` and the N-sample per-sample entries include the four fields; the text summary shows them when present.
- [ ] No test asserting `passed`, `verdict`, `abstained`, or a `cmd_*` exit code changes. A new test constructs a `RunnerResult` with large token/tool-call values and asserts `_grade()`'s outcome and exit code are identical to the same result with the fields `None` (the `TestGapClassAdvisory::test_testable_only_gap_is_advisory_not_blocking` shape).
- [ ] New-DB shape / upgrade-from-v50 shape / NULL-on-pre-migration-rows triad passes in `test_session_store_schema.py`, using subset (`<=`) column assertions.
- [ ] `usage_from_stream_lines()` is the only stream-usage parser; `_process_line` calls it and its existing `on_usage`/`on_usage_detailed` behavior is unchanged (`test_issue_manager.py::TestRunClaudeCommand`, `TestRunWithContinuation` still pass).
- [ ] The six documentation files in step 7 are updated.
- [ ] `python -m pytest scripts/tests/` exits 0.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis. Items 1–9 below are findings that informed the steps above, not steps themselves; where they conflict with the Decisions in Design, the Decisions win (notably: item 1's `on_usage` framing and item 8's timeout concern are resolved by Decision 1)._

1. Token counts and tool-call counts are captured from a harness runner invocation — today neither reaches `RunnerResult` for any of `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt` (`runner_spec.py`); token capture exists only via `on_usage`/`on_usage_detailed` callbacks into `run_claude_command()`, which no harness runner passes.
2. Wall-clock, tokens, and tool-calls are named, stable fields on the outcome the run model attaches to — following the `ChannelRecord`/`HarnessEvalOutcome.channels` precedent (a field added first, persistence tracked as a distinct follow-up per the ENH-3462/ENH-3476 split) or threaded directly to `HarnessEvent` the way `duration_ms` already is.
3. A run that fails a semantic/exit-code check but has expensive efficiency numbers still fails for the same reason as today — `_grade()`'s exit-code path is untouched by the new fields.
4. A run that passes with expensive efficiency numbers still passes — no new branch in `_grade()`, `_band_samples()`, or `evaluate()` reads the new fields to decide `passed`/`verdict`.
5. `python -m pytest scripts/tests/test_history_reader_harness.py scripts/tests/test_session_store_schema.py scripts/tests/test_cli_harness.py -v` passes.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

6. `cmd_dsl()` needs no separate wiring: it dispatches through the identical `RunnerType.PROMPT` path as `cmd_prompt()` (via `_run_prompt_action()`, `cli/harness.py:2455,2721`, confirmed by `run_action()`'s own docstring that `RunnerType.DSL` is never in `_DISPATCH`) — a fix to `_run_prompt()`'s capture logic covers both call sites in one change.
7. `--trace-mode` is not reachable from `prompt`/`dsl` at the CLI-parser layer at all (`_add_trace_flags()`, `cli/harness.py:689`, is attached only to `skill_p:738`) — capturing tokens/tool-calls on the `PROMPT`/`DSL` path cannot piggyback on the existing `--trace-mode` flag; it needs either a new flag or unconditional capture.
8. A token/tool-call capture on `_run_prompt()` faces a timeout-survivability gap `_run_skill()`'s `trace_mode` branch doesn't have: `_run_prompt()`'s blocking `subprocess.run()` has no live callback, so unlike `_run_skill()`'s `trace.append` callback (which preserves a partial `tool_trace` through `subprocess.TimeoutExpired`, `runner_spec.py:223-230`), no partial usage data can survive a timeout on this path without restructuring it to stream.
9. `python -m pytest scripts/tests/test_runner_spec.py scripts/tests/test_issue_manager.py -v` passes (covers the `on_usage`/`on_usage_detailed` wiring pattern this issue's capture logic follows).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Wire `on_usage`/`on_usage_detailed` token capture into `runner_spec.py`'s `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt`~~ — **superseded by Design Decision 1** (2026-09-14 review): `_run_cmd`/`_run_mcp` never invoke a host CLI, and the skill/prompt paths already capture the usage data in stdout. Parse post hoc from `RunnerResult.stdout`; no callback wiring. The `TestRunClaudeCommand`/`TestRunWithContinuation` tests remain relevant only as regression coverage for the `_process_line` refactor.
- Add direct test coverage for `_run_skill()`'s default blocking branch (`runner_spec.py:250-262`) and `_run_prompt()` (`:422-435`) in `test_runner_spec.py`, patching `subprocess.run` to return fixture stdout (stream-json / JSON blob) and asserting the four new `RunnerResult` fields; the `trace_mode`/`stream_callback` branches stay untouched and out of scope
- Update `test_runner_spec.py::TestRunActionDispatch::test_skill_dispatch_matches_legacy_shape`/`::test_prompt_dispatch_matches_legacy_shape` (`:151-188`) if new trailing `RunnerResult` fields populate with non-`None` values on these dispatch paths, since both assert dataclass `==` equality
- Add the new `harness_events` migration to `docs/ARCHITECTURE.md`'s schema-migration table (also backfilling the missing v50/ENH-3435 row while there) and update `docs/reference/API.md`'s `HarnessEvent` field list (also backfilling the missing v50 fields)
- Update `docs/reference/EVENT-SCHEMA.md`'s exhaustiveness claim about what `RunnerResult` fields are persisted to `harness_events`

## Impact

- **Priority**: P3 — the instrument that certifies runner correctness is currently silent on cost, and downstream cost-trend analytics over `.ll/history.db` need this per-run record as input, but no active selection decision is blocked on it yet.
- **Effort**: Medium — only wall-clock is captured today. Touches 5 source files (`subprocess_utils.py`, `runner_spec.py`, `cli/harness.py` incl. 10 `_record_harness_event` call sites, `session_store/schema.py` + `writers.py`, `history_reader/harness.py`), one migration, 6 test files, and 6 docs. The parsing itself is small; the breadth is in threading and docs.
- **Risk**: Low — additive reporting; must not become a gate (see Design: "Efficiency must not silently become a gate"). One coordination risk: migration numbering against ENH-3476 (Decision 9).
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: capturing, naming, surfacing (`--output json`, text summary, N-sample per-sample entries), and persisting `input_tokens`/`output_tokens`/`cache_read_tokens`/`tool_calls` beside the existing `duration_ms`, attached to the ENH-3397 run model (attempt × task × repetition × subject). Subject-side cost only.
- **Out of scope**: turning efficiency into a pass/fail gate — a run that passes expensively still passes; any cross-run or cross-sample comparison semantics (aggregates, deltas, "cheaper than" verdicts) — this issue records per-run values only; judge-side (evaluator) cost; switching `_run_prompt()` to stream-json to obtain `tool_calls` on the PROMPT/DSL path; the downstream cost-trend analytics consumer over `.ll/history.db` (separate work).

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- manual review pass - 2026-09-14 - resolved 9 design decisions, superseded the on_usage wiring directive, added Acceptance Criteria, re-estimated effort
- `/ll:refine-issue` - 2026-09-14T22:51:27 - `73b0db27-1e1a-4004-aaed-c305e94ddb77.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:18:34 - `b80e42ca-40bb-4d8a-b6d8-3b9dab6f1bf1.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:51:04 - `df520d06-750a-40b3-acb9-fb846e40ee7a.jsonl`
- `/ll:refine-issue` - 2026-09-14T20:30:28 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
