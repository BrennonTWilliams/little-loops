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

`ll-harness` reports one of pass, fail, or abstain per run. Two runners that both satisfy the same semantic criterion are indistinguishable in the verdict, even when one spent several times the tool calls, tokens, and wall-clock of the other. Most of the raw quantities are already logged, but not surfaced as named dimensions of the verdict.

## Expected Behavior

The verdict carries a small, named, stable set of efficiency dimensions — tokens, tool calls, and wall-clock at minimum — reported alongside (not folded into) the pass/fail/abstain outcome, attached to the run model shipped in ENH-3397 (an attempt recorded against task × repetition × subject). A run that passes expensively still passes; efficiency is reporting, not a second gate. A downstream post-mortem matches a run against this taxonomy instead of free-associating about why it was slow.

## Design

- Most of the raw quantities are already logged; the work is mostly surfacing them as dimensions of a specific run's verdict, and deciding what a comparison across two runs is allowed to conclude.
- **Efficiency must not silently become a gate.** A run that passes expensively still passes; the dimension is reporting, not a second pass/fail hiding behind one.
- The dimensions attach to the run model shipped as ENH-3397 — an attempt recorded against a named cell (task × repetition × subject) is the unit these measurements belong to.
- The precedent is a tournament fitness function that is deliberately multi-dimensional, with three of its four named criteria (resource efficiency, advancement speed, composition) existing to catch candidates that win wastefully — on the stated grounds that a wasteful winner is the wrong parent for the next generation. Naming the failure modes in advance is also what makes a post-mortem legible: the analyst matches observations against a known taxonomy rather than free-associating.

## Why it matters

The instrument that certifies runner correctness is today silent on cost. Downstream cost-trend analytics over `.ll/history.db` need exactly this per-run record as input; without it, a selection decision can carry forward a candidate that satisfies the criterion at multiples of the cost of its alternative.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for wiring tokens/tool-calls onto `RunnerResult` and persisting them to `HarnessEvent`.

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

- `HarnessEvent`: already tracks `duration_ms: int | None` (wall-clock, since ENH-2741); needs new `tokens: int | None`, `tool_calls: int | None` fields (`scripts/little_loops/history_reader/harness.py:53`)
- `RunnerResult.tool_trace: list[dict] | None` — ordered tool-call trace, currently trace-mode-only and not persisted to `harness_events` (`scripts/little_loops/runner_spec.py:100`)
- `HarnessEvalOutcome`: `passed: bool`, `verdict: str | None`, ... — where the new efficiency dimensions attach alongside the pass/fail/abstain outcome (`scripts/little_loops/cli/harness.py:863`)

### Signatures

- `authoritative_attempt(db_path, cell_key, repetition)` / `authoritative_attempts(db_path, cell_key)` (`scripts/little_loops/history_reader/harness.py:170`, `:198`) — the existing cell-keyed (task × repetition × subject) lookup the efficiency dimensions attach to
- `_grade(runner_label, result: RunnerResult, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`scripts/little_loops/cli/harness.py:1224`) — where tokens/tool-calls would be read off `result` and folded into the outcome

### Call Path

`_grade()` (`harness.py:1224`) reads `RunnerResult`/`tool_trace` -> populates new efficiency fields on `HarnessEvalOutcome` -> persisted onto `HarnessEvent` (`history_reader/harness.py:53`) -> read back via `authoritative_attempt()`/`authoritative_attempts()` for cross-run comparison.

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

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `HarnessEvent`/`recent_harness_events`/`harness_eval_pass_rate` section hand-transcribes the full field list and is already stale (missing the v50 `timeout_s`/`host_cli`/`subject_model`/`input_hash`/`conditions_fp` columns, pre-existing drift independent of this issue); needs the new `tokens`/`tool_calls` fields appended
- `docs/reference/CLI.md` — the `--output json` payload field list and the N-sample redundancy per-sample entry field list, both under `### ll-harness`, need new rows if efficiency dimensions surface there
- `docs/reference/EVENT-SCHEMA.md` — makes an explicit, load-bearing exhaustiveness claim ("Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column") that becomes factually stale once tokens/tool_calls become newly-persisted `RunnerResult`-derived columns
- `docs/ARCHITECTURE.md` — the History DB producer→consumer schema-migration table is the append point for a new migration row; the v50/ENH-3435 row is confirmed already missing from this table (a pre-existing gap this issue's migration would land into, not caused by it)
- `docs/guides/EVALUATION_GUIDE.md` — the "Across runs" section illustratively lists persisted `harness_events` columns; the natural place to mention the new efficiency dimensions since it specifically explains what gets written per run

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

1. Token counts and tool-call counts are captured from a harness runner invocation — today neither reaches `RunnerResult` for any of `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt` (`runner_spec.py`); token capture exists only via `on_usage`/`on_usage_detailed` callbacks into `run_claude_command()`, which no harness runner passes.
2. Wall-clock, tokens, and tool-calls are named, stable fields on the outcome the run model attaches to — following the `ChannelRecord`/`HarnessEvalOutcome.channels` precedent (a field added first, persistence tracked as a distinct follow-up per the ENH-3462/ENH-3476 split) or threaded directly to `HarnessEvent` the way `duration_ms` already is.
3. A run that fails a semantic/exit-code check but has expensive efficiency numbers still fails for the same reason as today — `_grade()`'s exit-code path is untouched by the new fields.
4. A run that passes with expensive efficiency numbers still passes — no new branch in `_grade()`, `_band_samples()`, or `evaluate()` reads the new fields to decide `passed`/`verdict`.
5. `python -m pytest scripts/tests/test_history_reader_harness.py scripts/tests/test_session_store_schema.py scripts/tests/test_cli_harness.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Wire `on_usage`/`on_usage_detailed` token capture into `runner_spec.py`'s `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt`, following the mocking pattern in `test_issue_manager.py::TestRunClaudeCommand`/`TestRunWithContinuation` and patching `little_loops.subprocess_utils.run_claude_command` at its module-local import site
- Add direct test coverage for `_run_skill()`'s `trace_mode`/`stream_callback` branches (`runner_spec.py:196-248`) in `test_runner_spec.py`, currently untested
- Update `test_runner_spec.py::TestRunActionDispatch::test_skill_dispatch_matches_legacy_shape`/`::test_prompt_dispatch_matches_legacy_shape` (`:151-188`) if new trailing `RunnerResult` fields populate with non-`None` values on these dispatch paths, since both assert dataclass `==` equality
- Add the new `harness_events` migration to `docs/ARCHITECTURE.md`'s schema-migration table (also backfilling the missing v50/ENH-3435 row while there) and update `docs/reference/API.md`'s `HarnessEvent` field list (also backfilling the missing v50 fields)
- Update `docs/reference/EVENT-SCHEMA.md`'s exhaustiveness claim about what `RunnerResult` fields are persisted to `harness_events`

## Impact

- **Priority**: P3 — the instrument that certifies runner correctness is currently silent on cost, and downstream cost-trend analytics over `.ll/history.db` need this per-run record as input, but no active selection decision is blocked on it yet.
- **Effort**: Small-Medium — most raw quantities (tokens, tool calls, wall-clock) are already logged per this issue's Design section; the work is surfacing them as named, stable verdict dimensions and defining what a cross-run comparison is allowed to conclude.
- **Risk**: Low — additive reporting; must not become a gate (see Design: "Efficiency must not silently become a gate").
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: naming and stabilizing tokens/tool-calls/wall-clock as verdict dimensions, attached to the ENH-3397 run model (attempt × task × repetition × subject).
- **Out of scope**: turning efficiency into a pass/fail gate — a run that passes expensively still passes; defining the downstream cost-trend analytics consumer over `.ll/history.db` (separate work).

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-09-14T20:51:04 - `df520d06-750a-40b3-acb9-fb846e40ee7a.jsonl`
- `/ll:refine-issue` - 2026-09-14T20:30:28 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
